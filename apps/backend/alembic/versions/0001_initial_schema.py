"""Create the non-clinical HERA assistant schema.

The schema stores approved public knowledge, exact structured lookups,
prototype booking capacity and redacted telemetry. It deliberately excludes
patients, medical records, prescriptions, invoices and other HIS/ERP data.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-18
"""

from __future__ import annotations

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# One SQL command per semicolon keeps psycopg and Alembic offline mode happy.
# vector(1024) is the fixed contract of Vietnamese_Embedding.
SCHEMA_SQL = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE bundle_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE official_sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    canonical_url TEXT,
    authority TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    retrieved_at TIMESTAMPTZ,
    valid_from DATE,
    valid_to DATE,
    verification_status TEXT NOT NULL,
    retrieval_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    rag_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    structured_lookup_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    current_lookup_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    historical_lookup_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (approval_status IN (
            'pending', 'approved_for_hackathon', 'approved_for_production',
            'rejected', 'expired', 'review_required'
        )),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    notes TEXT,
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE TABLE official_facts (
    fact_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES official_sources(source_id),
    claim_vi TEXT NOT NULL,
    allowed_intents_json JSONB NOT NULL,
    verified_at TIMESTAMPTZ,
    valid_from DATE,
    valid_to DATE,
    approval_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (approval_status IN (
            'pending', 'approved_for_hackathon', 'approved_for_production',
            'rejected', 'expired', 'review_required'
        )),
    retrieval_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    usage_note TEXT,
    CHECK (jsonb_typeof(allowed_intents_json) = 'array'),
    CHECK (jsonb_array_length(allowed_intents_json) > 0),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE TABLE fixed_response_templates (
    template_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    text_vi TEXT NOT NULL,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    PRIMARY KEY (template_key, version),
    CHECK (
        is_active = FALSE OR (
            approval_status IN ('approved_for_hackathon', 'approved_for_production')
            AND approved_by IS NOT NULL
        )
    )
);

CREATE TABLE knowledge_chunks (
    chunk_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES official_sources(source_id),
    fact_id TEXT REFERENCES official_facts(fact_id),
    ordinal INTEGER NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
    content_vi TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(content_vi, ''))
    ) STORED,
    embedding VECTOR(1024),
    embedding_model TEXT,
    embedding_dimension INTEGER
        CHECK (embedding_dimension IS NULL OR embedding_dimension = 1024),
    valid_from DATE,
    valid_to DATE,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    retrieval_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedded_at TIMESTAMPTZ,
    UNIQUE (source_id, content_hash),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CHECK (
        (embedding IS NULL AND embedding_dimension IS NULL)
        OR (embedding IS NOT NULL AND embedding_dimension = 1024)
    )
);

CREATE TABLE service_catalog_records (
    service_record_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES official_sources(source_id),
    source_file TEXT,
    source_file_sha256 CHAR(64),
    source_row_number INTEGER,
    source_page INTEGER,
    source_section TEXT,
    source_stt TEXT,
    equivalent_code TEXT,
    display_name_raw TEXT NOT NULL,
    display_name_search TEXT NOT NULL,
    display_name_folded TEXT NOT NULL,
    note_raw TEXT,
    note_search TEXT,
    record_type TEXT NOT NULL CHECK (record_type IN ('service', 'group_header')),
    dataset_label TEXT NOT NULL,
    historical_year INTEGER,
    historical BOOLEAN NOT NULL DEFAULT TRUE,
    current_lookup_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    historical_lookup_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    verification_status TEXT,
    raw_json JSONB NOT NULL,
    UNIQUE (source_id, source_section, source_stt)
);

CREATE TABLE service_price_snapshots (
    price_id TEXT PRIMARY KEY,
    service_record_id TEXT NOT NULL
        REFERENCES service_catalog_records(service_record_id) ON DELETE CASCADE,
    facility_code TEXT NOT NULL CHECK (facility_code IN ('CS1', 'CS2')),
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    raw_value TEXT,
    currency CHAR(3) NOT NULL DEFAULT 'VND' CHECK (currency = 'VND'),
    dataset_label TEXT NOT NULL,
    superseded_at DATE,
    current_lookup_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    historical_lookup_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (service_record_id, facility_code, dataset_label)
);

CREATE TABLE bhyt_household_policies (
    policy_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES official_sources(source_id),
    title TEXT NOT NULL,
    policy_scope TEXT NOT NULL DEFAULT 'household_contribution'
        CHECK (policy_scope = 'household_contribution'),
    base_salary_vnd BIGINT CHECK (base_salary_vnd IS NULL OR base_salary_vnd > 0),
    dataset_role TEXT,
    source_authority TEXT,
    valid_from DATE NOT NULL,
    valid_to DATE,
    historical BOOLEAN NOT NULL DEFAULT FALSE,
    current_lookup_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    disabled_reason TEXT,
    calculation_rule_raw TEXT,
    conditions_json JSONB NOT NULL DEFAULT CAST('[]' AS JSONB),
    raw_snapshot_json JSONB,
    raw_json JSONB NOT NULL,
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE bhyt_contribution_tiers (
    tier_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL
        REFERENCES bhyt_household_policies(policy_id) ON DELETE CASCADE,
    tier_order INTEGER NOT NULL CHECK (tier_order BETWEEN 1 AND 5),
    tier_label TEXT NOT NULL,
    rate_text TEXT,
    monthly_amount_vnd BIGINT
        CHECK (monthly_amount_vnd IS NULL OR monthly_amount_vnd > 0),
    annual_amount_vnd BIGINT
        CHECK (annual_amount_vnd IS NULL OR annual_amount_vnd > 0),
    source_value_exact BOOLEAN NOT NULL DEFAULT TRUE,
    raw_json JSONB NOT NULL,
    UNIQUE (policy_id, tier_order)
);

CREATE TABLE schedule_documents (
    document_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES official_sources(source_id),
    source_path TEXT NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    facility_code TEXT,
    schedule_kind TEXT,
    folder_week_start DATE,
    folder_week_end DATE,
    internal_week_start DATE,
    internal_week_end DATE,
    validation_status TEXT NOT NULL
        CHECK (validation_status IN ('accepted', 'review_required', 'rejected')),
    coverage_status TEXT NOT NULL
        CHECK (coverage_status IN ('full_range', 'partial_range', 'unknown')),
    review_reason TEXT,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    runtime_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    raw_metadata_json JSONB,
    raw_json JSONB NOT NULL,
    CHECK (
        folder_week_end IS NULL OR folder_week_start IS NULL
        OR folder_week_end >= folder_week_start
    ),
    CHECK (
        internal_week_end IS NULL OR internal_week_start IS NULL
        OR internal_week_end >= internal_week_start
    ),
    CHECK (
        runtime_eligible = FALSE OR (
            validation_status = 'accepted'
            AND approval_status IN ('approved_for_hackathon', 'approved_for_production')
            AND approved_by IS NOT NULL
        )
    )
);

CREATE TABLE doctors (
    doctor_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT,
    approved_at TIMESTAMPTZ
);

CREATE TABLE doctor_aliases (
    alias_normalized TEXT PRIMARY KEY,
    alias_raw TEXT NOT NULL,
    doctor_id TEXT NOT NULL REFERENCES doctors(doctor_id),
    approved_by TEXT,
    approved_at TIMESTAMPTZ
);

CREATE TABLE schedule_entries (
    schedule_entry_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL
        REFERENCES schedule_documents(document_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES official_sources(source_id),
    service_date DATE NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    facility_code TEXT NOT NULL,
    schedule_kind TEXT,
    unit_label TEXT,
    room_label TEXT,
    published_hours_raw TEXT,
    source_day_key TEXT,
    duty_status TEXT NOT NULL
        CHECK (duty_status IN ('scheduled', 'closed', 'not_published')),
    assignee_type TEXT NOT NULL
        CHECK (assignee_type IN ('named_doctor', 'generic_assignment', 'none')),
    session TEXT NOT NULL
        CHECK (session IN ('morning', 'published_window', 'closed', 'unknown')),
    assignee_text_raw TEXT,
    assignee_text_search TEXT,
    assignee_text_folded TEXT,
    room_label_folded TEXT,
    doctor_id TEXT REFERENCES doctors(doctor_id),
    doctor_candidate_id TEXT,
    is_bookable_slot BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (is_bookable_slot = FALSE),
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    runtime_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    review_reasons_json JSONB NOT NULL DEFAULT CAST('[]' AS JSONB),
    raw_json JSONB NOT NULL,
    CHECK (week_end >= week_start),
    CHECK (service_date BETWEEN week_start AND week_end)
);

CREATE TABLE schedule_entry_doctors (
    entry_id TEXT NOT NULL
        REFERENCES schedule_entries(schedule_entry_id) ON DELETE CASCADE,
    doctor_id TEXT NOT NULL REFERENCES doctors(doctor_id),
    session_key TEXT NOT NULL,
    doctor_text_raw TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending',
    PRIMARY KEY (entry_id, doctor_id, session_key)
);

CREATE TABLE booking_capacity_rules (
    capacity_rule_id TEXT PRIMARY KEY,
    doctor_id TEXT REFERENCES doctors(doctor_id),
    session_key TEXT NOT NULL DEFAULT '*',
    max_patients INTEGER NOT NULL CHECK (max_patients > 0),
    priority INTEGER NOT NULL DEFAULT 0,
    valid_from DATE,
    valid_to DATE,
    config_source TEXT NOT NULL,
    hospital_approved BOOLEAN NOT NULL DEFAULT FALSE,
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    raw_json JSONB NOT NULL,
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

-- Candidate doctor IDs are intentionally not foreign keys. They are review
-- suggestions and are not canonical doctors until a data owner approves them.
CREATE TABLE booking_doctor_candidates (
    doctor_candidate_id TEXT PRIMARY KEY,
    doctor_id TEXT NOT NULL,
    display_name_candidate TEXT NOT NULL,
    normalized_match_key TEXT NOT NULL,
    review_status TEXT,
    bookable BOOLEAN NOT NULL DEFAULT FALSE,
    hospital_approved BOOLEAN NOT NULL DEFAULT FALSE,
    production_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    raw_aliases_json JSONB NOT NULL DEFAULT CAST('[]' AS JSONB),
    source_schedule_entry_ids_json JSONB NOT NULL DEFAULT CAST('[]' AS JSONB),
    raw_json JSONB NOT NULL
);

CREATE TABLE booking_sessions (
    booking_session_id TEXT PRIMARY KEY,
    doctor_id TEXT NOT NULL REFERENCES doctors(doctor_id),
    service_date DATE NOT NULL,
    session_key TEXT NOT NULL,
    facility_code TEXT,
    room_label TEXT,
    capacity_limit INTEGER NOT NULL CHECK (capacity_limit > 0),
    capacity_rule_id TEXT NOT NULL
        REFERENCES booking_capacity_rules(capacity_rule_id),
    booking_opens_at TIMESTAMPTZ,
    booking_closes_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('draft', 'open', 'closed', 'cancelled')),
    upstream_session_ref TEXT,
    prototype_only BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doctor_id, service_date, session_key),
    CHECK (
        booking_closes_at IS NULL OR booking_opens_at IS NULL
        OR booking_closes_at >= booking_opens_at
    )
);

CREATE TABLE booking_session_schedule_entries (
    booking_session_id TEXT NOT NULL
        REFERENCES booking_sessions(booking_session_id) ON DELETE CASCADE,
    entry_id TEXT NOT NULL
        REFERENCES schedule_entries(schedule_entry_id) ON DELETE RESTRICT,
    PRIMARY KEY (booking_session_id, entry_id)
);

CREATE TABLE booking_holds (
    hold_id TEXT PRIMARY KEY,
    booking_session_id TEXT NOT NULL
        REFERENCES booking_sessions(booking_session_id) ON DELETE CASCADE,
    anonymous_token_hash TEXT NOT NULL UNIQUE,
    owner_session_hash TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    patient_identity_hash TEXT NOT NULL,
    patient_name_hash TEXT NOT NULL,
    patient_name_masked TEXT NOT NULL,
    patient_phone_hash TEXT NOT NULL,
    patient_phone_masked TEXT NOT NULL,
    patient_cccd_hash TEXT,
    patient_cccd_masked TEXT,
    patient_bhyt_hash TEXT,
    patient_bhyt_masked TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('held', 'confirmed', 'released', 'expired', 'cancelled')),
    expires_at TIMESTAMPTZ NOT NULL,
    upstream_booking_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    UNIQUE (booking_session_id, idempotency_key_hash)
);

CREATE TABLE support_channels (
    channel_id TEXT PRIMARY KEY,
    channel_type TEXT NOT NULL CHECK (channel_type IN ('phone', 'url')),
    label_vi TEXT NOT NULL,
    target_value TEXT NOT NULL,
    source_fact_id TEXT NOT NULL REFERENCES official_facts(fact_id),
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by TEXT,
    approved_at TIMESTAMPTZ
);

CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    conversation_hash TEXT NOT NULL,
    consent_to_store BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);

CREATE TABLE chat_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content_redacted TEXT NOT NULL,
    response_type TEXT,
    data_classification TEXT,
    grounded BOOLEAN,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE message_citations (
    message_id TEXT NOT NULL
        REFERENCES chat_messages(message_id) ON DELETE CASCADE,
    citation_order INTEGER NOT NULL CHECK (citation_order >= 0),
    source_id TEXT NOT NULL REFERENCES official_sources(source_id),
    fact_id TEXT REFERENCES official_facts(fact_id),
    excerpt_vi TEXT,
    PRIMARY KEY (message_id, citation_order)
);

CREATE TABLE structured_record_refs (
    message_id TEXT NOT NULL
        REFERENCES chat_messages(message_id) ON DELETE CASCADE,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    data_classification TEXT NOT NULL,
    PRIMARY KEY (message_id, record_type, record_id)
);

CREATE TABLE handoff_events (
    handoff_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(conversation_id),
    reason_code TEXT NOT NULL,
    channel_id TEXT REFERENCES support_channels(channel_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
    feedback_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    helpful BOOLEAN NOT NULL,
    reason_code TEXT,
    comment_redacted TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    audit_id BIGSERIAL PRIMARY KEY,
    request_id TEXT,
    actor_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    object_type TEXT,
    object_id TEXT,
    metadata_json JSONB NOT NULL DEFAULT CAST('{}' AS JSONB),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX service_name_trgm_idx
    ON service_catalog_records USING GIN (display_name_search gin_trgm_ops);
CREATE INDEX service_name_folded_trgm_idx
    ON service_catalog_records USING GIN (display_name_folded gin_trgm_ops);
CREATE INDEX service_code_idx ON service_catalog_records (equivalent_code);
CREATE INDEX service_price_facility_idx
    ON service_price_snapshots (facility_code, amount_vnd);
CREATE INDEX bhyt_policy_dates_idx
    ON bhyt_household_policies (valid_from, valid_to);
CREATE INDEX schedule_document_week_idx
    ON schedule_documents (folder_week_start, facility_code);
CREATE INDEX schedule_lookup_idx
    ON schedule_entries (service_date, facility_code, duty_status);
CREATE INDEX schedule_week_idx
    ON schedule_entries (week_start, facility_code, service_date);
CREATE INDEX schedule_provider_trgm_idx
    ON schedule_entries USING GIN (assignee_text_search gin_trgm_ops);
CREATE INDEX schedule_provider_folded_trgm_idx
    ON schedule_entries USING GIN (assignee_text_folded gin_trgm_ops);
CREATE INDEX facts_runtime_idx
    ON official_facts (approval_status, retrieval_eligible);
CREATE INDEX chunks_search_idx ON knowledge_chunks USING GIN (search_vector);
CREATE INDEX chunks_embedding_idx
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX booking_active_holds_idx
    ON booking_holds (booking_session_id, status, expires_at);
CREATE INDEX booking_owner_holds_idx
    ON booking_holds (owner_session_hash, status, expires_at);
CREATE INDEX chat_conversation_idx
    ON chat_messages (conversation_id, created_at);
CREATE INDEX audit_request_idx ON audit_events (request_id, created_at);
"""


DROP_SQL = r"""
DROP TABLE IF EXISTS audit_events CASCADE;
DROP TABLE IF EXISTS feedback CASCADE;
DROP TABLE IF EXISTS handoff_events CASCADE;
DROP TABLE IF EXISTS structured_record_refs CASCADE;
DROP TABLE IF EXISTS message_citations CASCADE;
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS support_channels CASCADE;
DROP TABLE IF EXISTS booking_holds CASCADE;
DROP TABLE IF EXISTS booking_session_schedule_entries CASCADE;
DROP TABLE IF EXISTS booking_sessions CASCADE;
DROP TABLE IF EXISTS booking_doctor_candidates CASCADE;
DROP TABLE IF EXISTS booking_capacity_rules CASCADE;
DROP TABLE IF EXISTS schedule_entry_doctors CASCADE;
DROP TABLE IF EXISTS schedule_entries CASCADE;
DROP TABLE IF EXISTS doctor_aliases CASCADE;
DROP TABLE IF EXISTS doctors CASCADE;
DROP TABLE IF EXISTS schedule_documents CASCADE;
DROP TABLE IF EXISTS bhyt_contribution_tiers CASCADE;
DROP TABLE IF EXISTS bhyt_household_policies CASCADE;
DROP TABLE IF EXISTS service_price_snapshots CASCADE;
DROP TABLE IF EXISTS service_catalog_records CASCADE;
DROP TABLE IF EXISTS knowledge_chunks CASCADE;
DROP TABLE IF EXISTS fixed_response_templates CASCADE;
DROP TABLE IF EXISTS official_facts CASCADE;
DROP TABLE IF EXISTS official_sources CASCADE;
DROP TABLE IF EXISTS bundle_meta CASCADE;
"""


def _statements(sql: str) -> tuple[str, ...]:
    """Split our deliberately simple DDL into individual SQL commands."""

    return tuple(statement.strip() for statement in sql.split(";") if statement.strip())


def upgrade() -> None:
    for statement in _statements(SCHEMA_SQL):
        op.execute(statement)


def downgrade() -> None:
    for statement in _statements(DROP_SQL):
        op.execute(statement)
