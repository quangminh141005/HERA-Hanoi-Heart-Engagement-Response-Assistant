"""initial schema — HERA (Bệnh viện Tim Hà Nội)

Tạo toàn bộ schema ban đầu: extension pgvector/pgcrypto/pg_trgm,
30 bảng (ERP + RAG + hội thoại), index, và seed dữ liệu tham chiếu.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Toàn bộ DDL. Chạy bằng exec_driver_sql (SQL thô) để:
#   - tránh SQLAlchemy text() hiểu nhầm ':' (trong TIME) là bind param
#   - psycopg3 không tham số -> simple query protocol -> chạy nhiều lệnh 1 lần
#
# ⚠️ Đổi vector(1024) nếu đổi model embedding:
#     bge-m3=1024 · vietnamese-bi-encoder(bkai)=768 · OpenAI 3-small=1536
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
-- ===== EXTENSIONS =====
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ===== A. DANH MỤC / THAM CHIẾU =====
CREATE TABLE departments (
    department_id   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    location        TEXT,
    hotline         TEXT
);

CREATE TABLE staff_roles (
    role_id          TEXT PRIMARY KEY,
    role_name        TEXT NOT NULL,
    department_id    TEXT REFERENCES departments(department_id),
    responsibilities JSONB DEFAULT '[]'
);

CREATE TABLE service_prices (
    service_code        TEXT PRIMARY KEY,
    service_name        TEXT NOT NULL,
    category            TEXT,
    price               BIGINT NOT NULL CHECK (price >= 0),
    insurance_supported BOOLEAN DEFAULT FALSE,
    support_rate        NUMERIC(3,2) DEFAULT 0 CHECK (support_rate BETWEEN 0 AND 1),
    applicable_to       JSONB DEFAULT '[]',
    effective_date      DATE,
    expiry_date         DATE,
    source_document     TEXT,
    is_demo             BOOLEAN DEFAULT FALSE
);

CREATE TABLE medicines (
    medicine_code      TEXT PRIMARY KEY,
    medicine_name      TEXT NOT NULL,
    active_ingredient  TEXT,
    unit               TEXT DEFAULT 'viên',
    packaging          TEXT,
    price_per_unit     BIGINT NOT NULL CHECK (price_per_unit >= 0),
    insurance_coverage BOOLEAN DEFAULT FALSE,
    stock_quantity     INTEGER DEFAULT 0 CHECK (stock_quantity >= 0),
    min_stock_warning  INTEGER DEFAULT 0,
    expiry_date        DATE,
    manufacturer       TEXT,
    source_document    TEXT,
    is_demo            BOOLEAN DEFAULT FALSE,
    updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE insurance_policies (
    policy_id           TEXT PRIMARY KEY,
    policy_name         TEXT NOT NULL,
    patient_type        TEXT NOT NULL CHECK (patient_type IN ('Đúng tuyến','Trái tuyến','Không có')),
    coverage_rate       NUMERIC(3,2) NOT NULL CHECK (coverage_rate BETWEEN 0 AND 1),
    max_support         BIGINT,
    applicable_services JSONB DEFAULT '[]',
    excluded_services   JSONB DEFAULT '[]',
    conditions          TEXT,
    effective_date      DATE,
    source_document     TEXT
);

CREATE TABLE procedures (
    procedure_id    TEXT PRIMARY KEY,
    procedure_name  TEXT NOT NULL,
    steps           JSONB NOT NULL DEFAULT '[]',
    source_document TEXT,
    version         TEXT,
    effective_date  DATE
);

-- ===== B. TÀI KHOẢN =====
CREATE TABLE users (
    user_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('patient','doctor','nurse','manager','admin')),
    linked_id     TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT now(),
    last_login    TIMESTAMPTZ
);

-- ===== C. CON NGƯỜI =====
CREATE TABLE patients (
    patient_id   TEXT PRIMARY KEY,
    full_name    TEXT NOT NULL,
    dob          DATE,
    gender       TEXT CHECK (gender IN ('Male','Female','Other')),
    id_card_enc  BYTEA,
    address      TEXT,
    phone        TEXT,
    email        TEXT,
    insurance_type          TEXT DEFAULT 'Không có'
                            CHECK (insurance_type IN ('Đúng tuyến','Trái tuyến','Không có')),
    insurance_card_number   TEXT,
    insurance_expiry_date   DATE,
    insurance_issuer        TEXT,
    insurance_eligible_from DATE,
    guardian_name     TEXT,
    guardian_relation TEXT,
    guardian_phone    TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE family_relations (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id  TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    relative_id TEXT REFERENCES patients(patient_id),
    relation    TEXT,
    note        TEXT
);

CREATE TABLE doctors (
    doctor_id        TEXT PRIMARY KEY,
    full_name        TEXT NOT NULL,
    gender           TEXT CHECK (gender IN ('Male','Female','Other')),
    department_id    TEXT REFERENCES departments(department_id),
    academic_title   TEXT,
    specializations  JSONB DEFAULT '[]',
    phone            TEXT,
    email            TEXT,
    examination_fee  BIGINT DEFAULT 0,
    consultation_fee BIGINT DEFAULT 0,
    is_demo          BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE staff (
    staff_id      TEXT PRIMARY KEY,
    full_name     TEXT NOT NULL,
    role_id       TEXT REFERENCES staff_roles(role_id),
    department_id TEXT REFERENCES departments(department_id),
    phone         TEXT,
    email         TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE medical_history (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id     TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    diagnosis      TEXT NOT NULL,
    diagnosed_date DATE,
    doctor_id      TEXT REFERENCES doctors(doctor_id),
    department_id  TEXT REFERENCES departments(department_id)
);

CREATE TABLE doctor_schedules (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doctor_id    TEXT NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    day_of_week  SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    shift        TEXT CHECK (shift IN ('morning','afternoon')),
    start_time   TIME,
    end_time     TIME,
    room         TEXT,
    is_available BOOLEAN DEFAULT TRUE
);

-- ===== D. ĐẶT LỊCH =====
CREATE TABLE appointments (
    appointment_id   TEXT PRIMARY KEY,
    patient_id       TEXT NOT NULL REFERENCES patients(patient_id),
    doctor_id        TEXT NOT NULL REFERENCES doctors(doctor_id),
    booking_date     DATE NOT NULL,
    booking_time     TIME NOT NULL,
    status           TEXT DEFAULT 'pending'
                     CHECK (status IN ('pending','confirmed','completed','cancelled')),
    symptom_severity SMALLINT CHECK (symptom_severity BETWEEN 1 AND 5),
    symptoms         TEXT,
    channel          TEXT DEFAULT 'website'
                     CHECK (channel IN ('website','zalo','hotline','walkin')),
    base_fee         BIGINT DEFAULT 50000,
    doctor_fee       BIGINT DEFAULT 0,
    total_prepay     BIGINT DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (doctor_id, booking_date, booking_time)
);

CREATE TABLE vital_signs (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id     TEXT NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    appointment_id TEXT REFERENCES appointments(appointment_id),
    height_cm      NUMERIC(5,1),
    weight_kg      NUMERIC(5,1),
    bmi            NUMERIC(4,1),
    blood_pressure TEXT,
    heart_rate     INTEGER,
    temperature    NUMERIC(4,1),
    recorded_by    TEXT REFERENCES staff(staff_id),
    recorded_at    TIMESTAMPTZ DEFAULT now()
);

-- ===== E. LÂM SÀNG =====
CREATE TABLE cls_orders (
    cls_id          TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    appointment_id  TEXT REFERENCES appointments(appointment_id),
    nurse_id        TEXT REFERENCES staff(staff_id),
    assessment_note TEXT,
    recorded_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE cls_order_items (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cls_id       TEXT NOT NULL REFERENCES cls_orders(cls_id) ON DELETE CASCADE,
    service_code TEXT REFERENCES service_prices(service_code),
    service_name TEXT,
    status       TEXT DEFAULT 'pending' CHECK (status IN ('pending','completed','cancelled')),
    result       TEXT,
    normal_range TEXT,
    abnormal     BOOLEAN DEFAULT FALSE
);

CREATE TABLE technical_exams (
    exam_id         TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    doctor_id       TEXT NOT NULL REFERENCES doctors(doctor_id),
    appointment_id  TEXT REFERENCES appointments(appointment_id),
    final_diagnosis TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE technical_exam_requests (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id      TEXT NOT NULL REFERENCES technical_exams(exam_id) ON DELETE CASCADE,
    service_code TEXT REFERENCES service_prices(service_code),
    service_name TEXT,
    reason       TEXT,
    status       TEXT DEFAULT 'pending' CHECK (status IN ('pending','completed','cancelled'))
);

CREATE TABLE technical_exam_results (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exam_id      TEXT NOT NULL REFERENCES technical_exams(exam_id) ON DELETE CASCADE,
    service_code TEXT REFERENCES service_prices(service_code),
    result       TEXT,
    image_url    TEXT,
    completed_at TIMESTAMPTZ
);

CREATE TABLE prescriptions (
    prescription_id TEXT PRIMARY KEY,
    exam_id         TEXT REFERENCES technical_exams(exam_id),
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    doctor_id       TEXT REFERENCES doctors(doctor_id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE prescription_items (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prescription_id TEXT NOT NULL REFERENCES prescriptions(prescription_id) ON DELETE CASCADE,
    medicine_code   TEXT REFERENCES medicines(medicine_code),
    dosage          TEXT,
    duration        TEXT,
    quantity        INTEGER CHECK (quantity > 0)
);

-- ===== F. HÓA ĐƠN =====
CREATE TABLE invoices (
    invoice_id      TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    appointment_id  TEXT REFERENCES appointments(appointment_id),
    subtotal        BIGINT NOT NULL DEFAULT 0,
    policy_id       TEXT REFERENCES insurance_policies(policy_id),
    coverage_rate   NUMERIC(3,2) DEFAULT 0,
    covered_amount  BIGINT DEFAULT 0,
    patient_portion BIGINT DEFAULT 0,
    total_payment   BIGINT DEFAULT 0,
    payment_status  TEXT DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid','pending','paid')),
    paid_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE invoice_items (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id  TEXT NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    item_type   TEXT CHECK (item_type IN ('exam_fee','doctor_fee','cls_service','technical','medicine')),
    description TEXT,
    ref_code    TEXT,
    amount      BIGINT NOT NULL DEFAULT 0
);

-- ===== G. RAG =====
CREATE TABLE hospital_knowledge (
    doc_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type     TEXT NOT NULL CHECK (source_type IN
                    ('procedure','pricing','department','doctor','faq',
                     'hours','insurance','emergency','web','other')),
    title           TEXT,
    content         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    source_document TEXT,
    source_url      TEXT,
    lang            TEXT DEFAULT 'vi',
    embedding       vector(1024),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE medical_reference (
    ref_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question         TEXT,
    answer           TEXT,
    topic            TEXT,
    source_dataset   TEXT,
    is_authoritative BOOLEAN DEFAULT FALSE,
    embedding        vector(1024),
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- ===== H. HỘI THOẠI =====
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    patient_id      TEXT REFERENCES patients(patient_id),
    channel         TEXT DEFAULT 'web' CHECK (channel IN ('web','zalo','hotline','app')),
    started_at      TIMESTAMPTZ DEFAULT now(),
    ended_at        TIMESTAMPTZ
);

CREATE TABLE chat_messages (
    message_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    intent          TEXT,
    is_emergency    BOOLEAN DEFAULT FALSE,
    is_grounded     BOOLEAN,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE message_citations (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
    doc_id     BIGINT REFERENCES hospital_knowledge(doc_id),
    snippet    TEXT,
    score      NUMERIC
);

CREATE TABLE emergency_alerts (
    alert_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id   TEXT REFERENCES conversations(conversation_id),
    patient_id        TEXT REFERENCES patients(patient_id),
    detected_symptoms TEXT,
    severity          SMALLINT,
    action_taken      TEXT,
    triggered_at      TIMESTAMPTZ DEFAULT now()
);

-- ===== I. INDEXES =====
CREATE INDEX idx_appointments_patient   ON appointments(patient_id);
CREATE INDEX idx_appointments_doctor    ON appointments(doctor_id, booking_date);
CREATE INDEX idx_appointments_priority  ON appointments(status, symptom_severity DESC, created_at);
CREATE INDEX idx_medhistory_patient     ON medical_history(patient_id);
CREATE INDEX idx_vitals_patient         ON vital_signs(patient_id, recorded_at DESC);
CREATE INDEX idx_cls_patient            ON cls_orders(patient_id);
CREATE INDEX idx_exam_patient           ON technical_exams(patient_id);
CREATE INDEX idx_presc_patient          ON prescriptions(patient_id);
CREATE INDEX idx_invoice_patient        ON invoices(patient_id);
CREATE INDEX idx_msg_conversation       ON chat_messages(conversation_id, created_at);
CREATE INDEX idx_doctor_dept            ON doctors(department_id);
CREATE INDEX idx_schedule_doctor        ON doctor_schedules(doctor_id, day_of_week);
CREATE INDEX idx_hospital_kb_embed ON hospital_knowledge USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_medref_embed      ON medical_reference  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_service_name_trgm  ON service_prices USING gin (service_name gin_trgm_ops);
CREATE INDEX idx_medicine_name_trgm ON medicines      USING gin (medicine_name gin_trgm_ops);
CREATE INDEX idx_doctor_name_trgm   ON doctors        USING gin (full_name    gin_trgm_ops);


"""


# Xóa toàn bộ (CASCADE nên không cần đúng thứ tự). Giữ lại extension & alembic_version.
DROP_SQL = """
DROP TABLE IF EXISTS message_citations CASCADE;
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS emergency_alerts CASCADE;
DROP TABLE IF EXISTS medical_reference CASCADE;
DROP TABLE IF EXISTS hospital_knowledge CASCADE;
DROP TABLE IF EXISTS invoice_items CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS prescription_items CASCADE;
DROP TABLE IF EXISTS prescriptions CASCADE;
DROP TABLE IF EXISTS technical_exam_results CASCADE;
DROP TABLE IF EXISTS technical_exam_requests CASCADE;
DROP TABLE IF EXISTS technical_exams CASCADE;
DROP TABLE IF EXISTS cls_order_items CASCADE;
DROP TABLE IF EXISTS cls_orders CASCADE;
DROP TABLE IF EXISTS vital_signs CASCADE;
DROP TABLE IF EXISTS appointments CASCADE;
DROP TABLE IF EXISTS doctor_schedules CASCADE;
DROP TABLE IF EXISTS medical_history CASCADE;
DROP TABLE IF EXISTS staff CASCADE;
DROP TABLE IF EXISTS doctors CASCADE;
DROP TABLE IF EXISTS family_relations CASCADE;
DROP TABLE IF EXISTS patients CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS procedures CASCADE;
DROP TABLE IF EXISTS insurance_policies CASCADE;
DROP TABLE IF EXISTS medicines CASCADE;
DROP TABLE IF EXISTS service_prices CASCADE;
DROP TABLE IF EXISTS staff_roles CASCADE;
DROP TABLE IF EXISTS departments CASCADE;
"""

import re

def _run_sql(sql: str) -> None:
    bind = op.get_bind()
    cleaned = re.sub(r"--[^\n]*", "", sql)
    for stmt in cleaned.split(";"):
        stmt = stmt.strip()
        if stmt:
            bind.exec_driver_sql(stmt)

def upgrade() -> None:
    _run_sql(SCHEMA_SQL)

def downgrade() -> None:
    _run_sql(DROP_SQL)