"""Build a staged PostgreSQL seed archive from validated generated JSON.

This is the raw -> generated -> PostgreSQL bridge. It never connects to the
database. Existing Vietnamese_Embedding vectors are reused only when the fact
text hash is unchanged; changed facts fail closed instead of using stale
vectors or spending API credit implicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPTS_ROOT.parent
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
for candidate in (SCRIPTS_ROOT, BACKEND_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.structured.manifest import (  # noqa: E402
    BundleIntegrityError,
    load_manifest,
    validate_generated_bundle,
)
from export_postgres_seed import (  # noqa: E402
    _build_snapshot_payload,
    _write_deterministic_archive,
)
from seed_postgres import (  # noqa: E402
    REFERENCE_TABLES,
    SeedArchive,
    SeedError,
    load_seed_archive,
)

APPROVED_BY = "hackathon-data-owner"
CAPACITY_RULE_ID = "CAPACITY-DEFAULT-PER-DOCTOR-SESSION"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _fold(value: Any) -> str:
    text = str(value or "").replace("Đ", "D").replace("đ", "d")
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(text.lower().split())


def _hash_id(value: str, size: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:size].upper()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeedError(f"Cannot load generated file {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SeedError(f"Generated file {path.name} must contain an object")
    return payload


def _rows_by_table(archive: SeedArchive) -> dict[str, list[dict[str, Any]]]:
    return {
        name: [dict(row) for row in table["rows"]]
        for name, table in archive.tables.items()
    }


def _table_payloads(
    archive: SeedArchive,
    rows: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for spec in REFERENCE_TABLES:
        template = archive.tables[spec.name]
        columns = [str(column) for column in template["columns"]]
        normalized: list[dict[str, Any]] = []
        for source in rows[spec.name]:
            missing = [column for column in columns if column not in source]
            extra = sorted(set(source) - set(columns))
            if missing or extra:
                raise SeedError(
                    f"Mapping for {spec.name} violates seed columns: "
                    f"missing={missing}, extra={extra}"
                )
            normalized.append({column: source[column] for column in columns})
        normalized.sort(
            key=lambda row: tuple(str(row[key]) for key in spec.primary_key)
        )
        payloads.append(
            {
                "name": spec.name,
                "primary_key": list(spec.primary_key),
                "columns": columns,
                "rows": normalized,
            }
        )
    return payloads


def _generated_parts(
    generated_dir: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    descriptors = manifest.get("files")
    if not isinstance(descriptors, list):
        raise SeedError("Generated manifest has no file descriptors")
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            raise SeedError("Generated manifest has an invalid descriptor")
        name = str(descriptor.get("file", ""))
        kind = str(descriptor.get("kind", ""))
        if not name or not kind:
            raise SeedError("Generated file descriptor is incomplete")
        by_kind.setdefault(kind, []).append(_load_json(generated_dir / name))
    required = {
        "sources_facts_templates",
        "historical_service_prices_2025",
        "bhyt_household_policies",
        "schedule_documents",
        "schedule_entries",
        "prototype_capacity_config",
    }
    missing = sorted(required - set(by_kind))
    if missing:
        raise SeedError(f"Generated bundle is missing lanes: {', '.join(missing)}")
    source_pack = by_kind["sources_facts_templates"]
    if len(source_pack) != 1:
        raise SeedError("Exactly one sources/facts/templates file is required")
    return {
        "source_pack": source_pack[0],
        "prices": [
            row
            for batch in by_kind["historical_service_prices_2025"]
            for row in batch.get("records", [])
        ],
        "bhyt": by_kind["bhyt_household_policies"][0],
        "schedule_documents": by_kind["schedule_documents"][0].get("records", []),
        "schedule_entries": by_kind["schedule_entries"][0].get("records", []),
        "capacity": by_kind["prototype_capacity_config"][0],
    }


def _map_sources(
    source_pack: Mapping[str, Any],
    baseline: Mapping[str, list[dict[str, Any]]],
    parts: Mapping[str, Any],
    approved_at: str,
) -> list[dict[str, Any]]:
    previous = {row["source_id"]: row for row in baseline["official_sources"]}
    current_ids = {
        *(
            row.get("source_id")
            for row in parts["prices"]
            if row.get("retrieval_eligible_for_current_price")
        ),
        *(
            row.get("source_id")
            for row in parts["bhyt"].get("policies", [])
            if row.get("is_current") and row.get("retrieval_eligible")
        ),
    }
    historical_ids = {
        row.get("source_id")
        for row in parts["prices"]
        if row.get("retrieval_eligible_for_historical_lookup")
    }
    structured_ids = {
        *(row.get("source_id") for row in parts["prices"]),
        *(
            row.get("source_id")
            for row in parts["bhyt"].get("policies", [])
            if row.get("is_current") and row.get("retrieval_eligible")
        ),
        *(row.get("parent_source_id") for row in parts["schedule_documents"]),
    }
    result = []
    for raw in source_pack.get("sources", []):
        source_id = str(raw["source_id"])
        old = previous.get(source_id, {})
        retrieval = bool(raw.get("retrieval_eligible"))
        structured = source_id in structured_ids or bool(
            old.get("structured_lookup_eligible")
        )
        approved = retrieval or structured
        result.append(
            {
                "approval_status": "approved_for_hackathon" if approved else "pending",
                "approved_at": approved_at if approved else None,
                "approved_by": APPROVED_BY if approved else None,
                "authority": str(raw.get("authority") or "unknown"),
                "canonical_url": raw.get("url"),
                "current_lookup_eligible": bool(
                    old.get("current_lookup_eligible") or source_id in current_ids
                ),
                "historical_lookup_eligible": bool(
                    old.get("historical_lookup_eligible") or source_id in historical_ids
                ),
                "notes": raw.get("notes"),
                "production_eligible": False,
                "published_at": raw.get("published_at"),
                "publisher": str(raw.get("publisher") or "Không rõ"),
                "rag_eligible": retrieval,
                "retrieval_eligible": retrieval,
                "retrieved_at": raw.get("retrieved_at"),
                "source_id": source_id,
                "structured_lookup_eligible": structured,
                "title": str(raw.get("title") or source_id),
                "valid_from": raw.get("valid_from"),
                "valid_to": raw.get("valid_to"),
                "verification_status": str(raw.get("verification_status") or "pending"),
            }
        )
    return result


def _map_facts_and_chunks(
    source_pack: Mapping[str, Any],
    baseline: Mapping[str, list[dict[str, Any]]],
    approved_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    vectors = {
        (str(row.get("fact_id")), str(row.get("content_hash"))): row
        for row in baseline["knowledge_chunks"]
        if row.get("embedding_json")
    }
    facts: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    missing_vectors: list[str] = []
    for raw in source_pack.get("facts", []):
        fact_id = str(raw["fact_id"])
        claim = " ".join(str(raw["claim_vi"]).split())
        content_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()
        facts.append(
            {
                "allowed_intents_json": _canonical_json(
                    raw.get("allowed_intents") or []
                ),
                "approval_status": "approved_for_hackathon",
                "claim_vi": claim,
                "fact_id": fact_id,
                "retrieval_eligible": True,
                "source_id": str(raw["source_id"]),
                "usage_note": raw.get("usage_note"),
                "valid_from": raw.get("valid_from"),
                "valid_to": raw.get("valid_to"),
                "verified_at": raw.get("verified_at"),
            }
        )
        old = vectors.get((fact_id, content_hash))
        if old is None:
            missing_vectors.append(fact_id)
            continue
        chunks.append(
            {
                "approval_status": "approved_for_hackathon",
                "chunk_id": f"CHUNK-{fact_id}-001",
                "content_hash": content_hash,
                "content_vi": claim,
                "created_at": approved_at,
                "embedded_at": old["embedded_at"],
                "embedding_dimension": old["embedding_dimension"],
                "embedding_json": old["embedding_json"],
                "embedding_model": old["embedding_model"],
                "fact_id": fact_id,
                "ordinal": old["ordinal"],
                "retrieval_eligible": True,
                "source_id": str(raw["source_id"]),
            }
        )
    if missing_vectors:
        raise SeedError(
            "Changed/new facts have no matching Vietnamese_Embedding vector: "
            f"{', '.join(sorted(missing_vectors))}. No candidate was written; "
            "embed only these reviewed facts, then retry."
        )
    return facts, chunks


def _map_templates(
    source_pack: Mapping[str, Any], approved_at: str
) -> list[dict[str, Any]]:
    templates = source_pack.get("fixed_response_templates")
    if not isinstance(templates, dict) or not templates:
        raise SeedError("Generated source pack has no fixed response templates")
    return [
        {
            "approval_status": "approved_for_hackathon",
            "approved_at": approved_at,
            "approved_by": APPROVED_BY,
            "is_active": True,
            "template_key": key,
            "text_vi": str(value),
            "version": 1,
        }
        for key, value in templates.items()
    ]


def _map_prices(
    raw_prices: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels = {
        str(row["source_id"]): str(row["dataset_label"])
        for row in baseline["service_catalog_records"]
    }
    records: list[dict[str, Any]] = []
    prices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_prices:
        record_id = str(raw["service_record_id"])
        if record_id in seen:
            raise SeedError(f"Duplicate generated service record: {record_id}")
        seen.add(record_id)
        source_id = str(raw["source_id"])
        label = labels.get(source_id, "BẢNG GIÁ DỊCH VỤ KỸ THUẬT")
        display = " ".join(str(raw.get("dich_vu_ky_thuat") or "").split())
        note = " ".join(str(raw.get("ghi_chu") or "").split())
        page = raw.get("page")
        records.append(
            {
                "approval_status": "approved_for_hackathon",
                "current_lookup_eligible": bool(
                    raw.get("retrieval_eligible_for_current_price")
                ),
                "dataset_label": label,
                "display_name_folded": _fold(display),
                "display_name_raw": display,
                "display_name_search": " ".join(
                    str(raw.get("display_name_search") or display).split()
                ),
                "equivalent_code": str(raw.get("ma_tuong_duong") or ""),
                "historical": not bool(raw.get("is_current")),
                "historical_lookup_eligible": bool(
                    raw.get("retrieval_eligible_for_historical_lookup")
                ),
                "historical_year": raw.get("historical_year"),
                "note_raw": note,
                "note_search": " ".join(str(raw.get("note_search") or note).split()),
                "production_eligible": False,
                "raw_json": _canonical_json(raw),
                "record_type": (
                    "group_header"
                    if raw.get("record_type") == "group_header"
                    else "service"
                ),
                "service_record_id": record_id,
                "source_file": raw.get("source_file_path"),
                "source_file_sha256": raw.get("source_file_sha256"),
                "source_id": source_id,
                "source_page": int(page) if str(page or "").isdigit() else None,
                "source_row_number": raw.get("source_row_number"),
                "source_section": raw.get("section"),
                "source_stt": str(raw.get("stt") or ""),
                "verification_status": raw.get("verification_status"),
            }
        )
        for price in raw.get("facility_prices", []):
            prices.append(
                {
                    "amount_vnd": int(price["amount_vnd"]),
                    "currency": str(price.get("currency") or "VND"),
                    "current_lookup_eligible": bool(
                        raw.get("retrieval_eligible_for_current_price")
                    ),
                    "dataset_label": label,
                    "facility_code": str(price["facility_code"]),
                    "historical_lookup_eligible": bool(
                        raw.get("retrieval_eligible_for_historical_lookup")
                    ),
                    "price_id": str(price["price_id"]),
                    "production_eligible": False,
                    "raw_value": str(price.get("amount_raw") or ""),
                    "service_record_id": record_id,
                    "superseded_at": raw.get("superseded_at"),
                }
            )
    return records, prices


def _map_bhyt(
    payload: Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_titles = {str(row["source_id"]): str(row["title"]) for row in sources}
    policies: list[dict[str, Any]] = []
    tiers: list[dict[str, Any]] = []
    for raw in payload.get("policies", []):
        policy_id = str(raw["policy_id"])
        snapshot = raw.get("raw_snapshot") or {}
        salary = raw.get("base_salary_vnd")
        if salary is None:
            salary = (snapshot.get("muc_luong_co_so_hien_tai") or {}).get("so_tien_vnd")
        conditions = snapshot.get("dieu_kien_tham_gia") or []
        policies.append(
            {
                "approval_status": "approved_for_hackathon",
                "base_salary_vnd": salary,
                "calculation_rule_raw": snapshot.get("quy_tac_tinh_phi"),
                "conditions_json": _canonical_json(conditions),
                "current_lookup_eligible": bool(
                    raw.get("is_current") and raw.get("retrieval_eligible")
                ),
                "dataset_role": raw.get("dataset_role"),
                "disabled_reason": raw.get("disabled_reason"),
                "historical": not bool(raw.get("is_current")),
                "policy_id": policy_id,
                "policy_scope": "household_contribution",
                "production_eligible": False,
                "raw_json": _canonical_json(raw),
                "raw_snapshot_json": (_canonical_json(snapshot) if snapshot else None),
                "source_authority": raw.get("source_authority"),
                "source_id": str(raw["source_id"]),
                "title": str(
                    snapshot.get("chu_de")
                    or source_titles.get(str(raw["source_id"]), policy_id)
                ),
                "valid_from": raw["valid_from"],
                "valid_to": raw.get("valid_to"),
            }
        )
        raw_tiers = (
            raw.get("contribution_tiers") or snapshot.get("bang_gia_chi_tiet") or []
        )
        for index, tier in enumerate(raw_tiers, 1):
            tiers.append(
                {
                    "annual_amount_vnd": tier.get(
                        "annual_amount_vnd", tier.get("muc_dong_nam_vnd")
                    ),
                    "monthly_amount_vnd": tier.get(
                        "monthly_amount_vnd", tier.get("muc_dong_thang_vnd")
                    ),
                    "policy_id": policy_id,
                    "rate_text": tier.get("rate_text", tier.get("ty_le_dong_bhyt")),
                    "raw_json": _canonical_json(tier),
                    "source_value_exact": True,
                    "tier_id": str(
                        tier.get("contribution_tier_id") or f"{policy_id}::{index}"
                    ),
                    "tier_label": str(
                        tier.get("tier_label")
                        or tier.get("thanh_vien_ho_gia_dinh")
                        or index
                    ),
                    "tier_order": index,
                }
            )
    return policies, tiers


def _map_schedule_documents(
    raw_documents: Sequence[Mapping[str, Any]], approved_at: str
) -> list[dict[str, Any]]:
    rows = []
    for raw in raw_documents:
        accepted = raw.get("validation_status") == "accepted"
        folder = raw.get("folder_week") or {}
        internal = raw.get("internal_week") or {}
        rows.append(
            {
                "approval_status": (
                    "approved_for_hackathon" if accepted else "review_required"
                ),
                "approved_at": approved_at if accepted else None,
                "approved_by": APPROVED_BY if accepted else None,
                "coverage_status": raw.get("coverage_status") or "unknown",
                "document_id": str(raw["document_id"]),
                "facility_code": raw.get("facility_code"),
                "folder_week_end": folder.get("week_end"),
                "folder_week_start": folder.get("week_start"),
                "internal_week_end": internal.get("week_end"),
                "internal_week_start": internal.get("week_start"),
                "needs_review": bool(raw.get("needs_review")),
                "raw_json": _canonical_json(raw),
                "raw_metadata_json": _canonical_json(raw.get("raw_metadata") or {}),
                "review_reason": raw.get("review_reason"),
                "runtime_eligible": accepted,
                "schedule_kind": raw.get("schedule_kind"),
                "source_id": str(raw["parent_source_id"]),
                "source_path": str(raw["source_path"]),
                "source_sha256": str(raw["source_sha256"]),
                "validation_status": str(
                    raw.get("validation_status") or "review_required"
                ),
            }
        )
    return rows


def _safe_booking_assignments(
    raw_entries: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[str, str, str]]:
    """Select one unambiguous roster entry per doctor/date/session prototype key."""

    safe: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for raw in sorted(raw_entries, key=lambda row: str(row["schedule_entry_id"])):
        assignee = " ".join(str(raw.get("assignee_text_raw") or "").split())
        normalized = _fold(assignee)
        if not (
            raw.get("assignee_type") == "named_doctor"
            and raw.get("duty_status") == "scheduled"
            and not raw.get("needs_review")
            and "\n" not in str(raw.get("assignee_text_raw") or "")
            and normalized
            and _looks_like_person_name(normalized)
        ):
            continue
        key = (normalized, str(raw["service_date"]), str(raw["session"]))
        safe.setdefault(key, raw)
    return {str(row["schedule_entry_id"]): key for key, row in safe.items()}


def _looks_like_person_name(normalized: str) -> bool:
    """Keep prototype booking sessions tied to plausible named clinicians only."""

    tokens = [token for token in normalized.replace(".", " ").split() if token]
    if len(tokens) < 2:
        return False
    non_name_markers = {
        "copd",
        "clb",
        "shclbbn",
        "sinh",
        "hoat",
        "chuyen",
        "de",
        "benh",
        "nhan",
        "phong",
        "khoa",
    }
    if any(token in non_name_markers for token in tokens):
        return False
    if any(any(character.isdigit() for character in token) for token in tokens):
        return False
    return True


def _map_schedule_and_booking(
    raw_entries: Sequence[Mapping[str, Any]],
    capacity: Mapping[str, Any],
    approved_at: str,
) -> dict[str, list[dict[str, Any]]]:
    limit = int(capacity.get("default_patients_per_named_doctor_per_session") or 0)
    if limit <= 0:
        raise SeedError("Prototype capacity must be a positive integer")
    selected_by_entry = _safe_booking_assignments(raw_entries)
    doctors_by_normalized: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    entry_doctors: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for raw in raw_entries:
        entry_id = str(raw["schedule_entry_id"])
        selected_key = selected_by_entry.get(entry_id)
        doctor_id = None
        if selected_key is not None:
            normalized, service_date, session_key = selected_key
            assignee = " ".join(str(raw["assignee_text_raw"]).split())
            doctor_id = f"DOCTOR-DEMO-{_hash_id(normalized, 12)}"
            doctors_by_normalized.setdefault(
                normalized,
                {
                    "approval_status": "approved_for_hackathon",
                    "approved_at": approved_at,
                    "approved_by": APPROVED_BY,
                    "display_name": assignee,
                    "doctor_id": doctor_id,
                    "normalized_name": normalized,
                },
            )
            entry_doctors.append(
                {
                    "doctor_id": doctor_id,
                    "doctor_text_raw": assignee,
                    "entry_id": entry_id,
                    "review_status": "approved_for_hackathon",
                    "session_key": session_key,
                }
            )
            identity = f"{doctor_id}|{service_date}|{session_key}"
            booking_id = f"BSESSION-{_hash_id(identity, 20)}"
            sessions.append(
                {
                    "booking_closes_at": None,
                    "booking_opens_at": None,
                    "booking_session_id": booking_id,
                    "capacity_limit": limit,
                    "capacity_rule_id": CAPACITY_RULE_ID,
                    "created_at": approved_at,
                    "doctor_id": doctor_id,
                    "facility_code": raw.get("facility_code"),
                    "prototype_only": True,
                    "room_label": raw.get("room_label"),
                    "service_date": service_date,
                    "session_key": session_key,
                    "status": "open",
                    "upstream_session_ref": None,
                }
            )
            links.append({"booking_session_id": booking_id, "entry_id": entry_id})

        assignee_raw = raw.get("assignee_text_raw")
        room = raw.get("room_label")
        entries.append(
            {
                "approval_status": "approved_for_hackathon",
                "assignee_text_folded": _fold(assignee_raw),
                "assignee_text_raw": assignee_raw,
                "assignee_text_search": " ".join(
                    str(raw.get("assignee_text_search") or assignee_raw or "").split()
                ),
                "assignee_type": str(raw["assignee_type"]),
                "doctor_candidate_id": raw.get("doctor_candidate_id"),
                "doctor_id": doctor_id,
                "document_id": str(raw["document_id"]),
                "duty_status": str(raw["duty_status"]),
                "facility_code": str(raw["facility_code"]),
                "is_bookable_slot": False,
                "needs_review": bool(raw.get("needs_review")),
                "production_eligible": False,
                "published_hours_raw": raw.get("published_hours_raw"),
                "raw_json": _canonical_json(raw),
                "review_reasons_json": _canonical_json(raw.get("review_reasons") or []),
                "room_label": room,
                "room_label_folded": _fold(room),
                "runtime_eligible": not bool(raw.get("needs_review")),
                "schedule_entry_id": entry_id,
                "schedule_kind": raw.get("schedule_kind"),
                "service_date": str(raw["service_date"]),
                "session": str(raw["session"]),
                "source_day_key": raw.get("source_day_key"),
                "source_id": str(raw["source_id"]),
                "unit_label": raw.get("unit_label"),
                "week_end": str(raw["week_end"]),
                "week_start": str(raw["week_start"]),
            }
        )

    doctors = list(doctors_by_normalized.values())
    canonical_doctor_names = {row["doctor_id"]: row["display_name"] for row in doctors}
    for row in entry_doctors:
        row["doctor_text_raw"] = canonical_doctor_names[row["doctor_id"]]
    aliases = [
        {
            "alias_normalized": row["normalized_name"],
            "alias_raw": row["display_name"],
            "approved_at": approved_at,
            "approved_by": APPROVED_BY,
            "doctor_id": row["doctor_id"],
        }
        for row in doctors
    ]
    candidates = [
        {
            "bookable": False,
            "display_name_candidate": str(raw["display_name_candidate"]),
            "doctor_candidate_id": str(raw["doctor_candidate_id"]),
            "doctor_id": str(raw.get("doctor_id") or raw["doctor_candidate_id"]),
            "hospital_approved": False,
            "normalized_match_key": str(raw["normalized_match_key"]),
            "production_eligible": False,
            "raw_aliases_json": _canonical_json(raw.get("raw_aliases") or []),
            "raw_json": _canonical_json(raw),
            "review_status": raw.get("review_status"),
            "source_schedule_entry_ids_json": _canonical_json(
                raw.get("source_schedule_entry_ids") or []
            ),
        }
        for raw in capacity.get("doctor_candidates", [])
    ]
    rules = [
        {
            "capacity_rule_id": CAPACITY_RULE_ID,
            "config_source": str(
                capacity.get("config_source") or "project_mvp_default"
            ),
            "doctor_id": None,
            "hospital_approved": False,
            "max_patients": limit,
            "priority": 0,
            "production_eligible": False,
            "raw_json": _canonical_json(capacity),
            "session_key": "*",
            "valid_from": None,
            "valid_to": None,
        }
    ]
    return {
        "schedule_entries": entries,
        "schedule_entry_doctors": entry_doctors,
        "doctors": doctors,
        "doctor_aliases": aliases,
        "booking_capacity_rules": rules,
        "booking_doctor_candidates": candidates,
        "booking_sessions": sessions,
        "booking_session_schedule_entries": links,
    }


def build_candidate_payload(
    *, baseline_archive: SeedArchive, generated_dir: Path
) -> dict[str, Any]:
    validation = validate_generated_bundle(generated_dir)
    manifest = load_manifest(generated_dir)
    if validation.bundle_version != baseline_archive.bundle_version:
        raise SeedError("Generated bundle and baseline archive versions differ")
    parts = _generated_parts(generated_dir, manifest)
    baseline = _rows_by_table(baseline_archive)
    approved_at = str(
        parts["source_pack"].get("normalized_at") or "2026-07-17T23:45:00+07:00"
    )

    sources = _map_sources(parts["source_pack"], baseline, parts, approved_at)
    facts, chunks = _map_facts_and_chunks(parts["source_pack"], baseline, approved_at)
    services, price_points = _map_prices(parts["prices"], baseline)
    policies, tiers = _map_bhyt(parts["bhyt"], sources)
    schedule = _map_schedule_and_booking(
        parts["schedule_entries"], parts["capacity"], approved_at
    )
    fact_ids = {row["fact_id"] for row in facts}
    support = [
        row for row in baseline["support_channels"] if row["source_fact_id"] in fact_ids
    ]
    if len(support) != len(baseline["support_channels"]):
        raise SeedError(
            "A support-channel source fact was removed. Review/update the explicit "
            "support-channel contract before building a new candidate."
        )
    rows = {
        "bundle_meta": baseline["bundle_meta"],
        "official_sources": sources,
        "official_facts": facts,
        "fixed_response_templates": _map_templates(parts["source_pack"], approved_at),
        "knowledge_chunks": chunks,
        "service_catalog_records": services,
        "service_price_snapshots": price_points,
        "bhyt_household_policies": policies,
        "bhyt_contribution_tiers": tiers,
        "schedule_documents": _map_schedule_documents(
            parts["schedule_documents"], approved_at
        ),
        **schedule,
        "support_channels": support,
    }
    tables = _table_payloads(baseline_archive, rows)
    return _build_snapshot_payload(
        baseline_archive,
        tables,
        generated_manifest=manifest,
        generated_manifest_sha256=validation.manifest_sha256,
        generated_files_checked=validation.files_checked,
        generated_raw_inputs_checked=validation.raw_inputs_checked,
        allow_manifest_rebind=True,
    )


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BACKEND_ROOT / "data/hera_postgres_seed.json.gz",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data/generated",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(REPOSITORY_ROOT / "artifacts/hera_postgres_seed.candidate.json.gz"),
    )
    parser.add_argument(
        "--confirm-build",
        default="",
        help="Required phrase: BUILD_REVIEWED_DATA_CANDIDATE",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    if args.confirm_build != "BUILD_REVIEWED_DATA_CANDIDATE":
        print(
            "build_seed_from_generated: review generated validation first, "
            "then pass --confirm-build BUILD_REVIEWED_DATA_CANDIDATE",
            file=sys.stderr,
        )
        return 2
    output = args.output.resolve()
    baseline_path = args.baseline.resolve()
    if output == baseline_path:
        print(
            "build_seed_from_generated: output must be a staged candidate, "
            "not the checked-in baseline archive",
            file=sys.stderr,
        )
        return 2
    try:
        baseline = load_seed_archive(baseline_path)
        payload = build_candidate_payload(
            baseline_archive=baseline,
            generated_dir=args.generated_dir.resolve(),
        )
        digest = _write_deterministic_archive(output, payload)
    except (BundleIntegrityError, OSError, SeedError, ValueError) as exc:
        print(f"build_seed_from_generated: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "candidate_built",
                "output": str(output),
                "archive_sha256": digest,
                "manifest_sha256": payload["manifest_sha256"],
                "table_counts": payload["source_table_counts"],
                "next_step": (
                    "Seed only a fresh development database, then run "
                    "integration tests before export/promotion."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
