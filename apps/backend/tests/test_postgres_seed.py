from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import seed_postgres

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SEED_ARCHIVE = BACKEND_ROOT / "data" / "hera_postgres_seed.json.gz"
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "0001_initial_schema.py"


def test_postgres_migration_is_non_clinical_and_uses_1024_vectors() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    for required_table in (
        "official_sources",
        "official_facts",
        "knowledge_chunks",
        "service_catalog_records",
        "bhyt_household_policies",
        "schedule_entries",
        "booking_sessions",
        "booking_holds",
        "feedback",
        "audit_events",
    ):
        assert f"CREATE TABLE {required_table}" in migration
    assert "VECTOR(1024)" in migration
    assert "Vietnamese_Embedding" in migration

    for forbidden_table in (
        "patients",
        "medicines",
        "medical_history",
        "prescriptions",
        "invoices",
    ):
        assert f"CREATE TABLE {forbidden_table}" not in migration


def test_real_postgres_archive_passes_seed_preflight() -> None:
    archive = seed_postgres.load_seed_archive(SEED_ARCHIVE)

    assert archive.bundle_version == "2.0.0"
    assert len(archive.archive_sha256) == 64
    assert len(archive.manifest_sha256) == 64
    assert archive.table_counts["service_catalog_records"] == 2_946
    assert archive.table_counts["service_price_snapshots"] == 4_051
    assert archive.table_counts["schedule_entries"] == 1_382
    assert archive.table_counts["booking_sessions"] == 771


def test_seed_rejects_integrity_metadata_for_another_bundle() -> None:
    integrity = json.dumps(
        {
            "bundle_version": "different-version",
            "manifest_sha256": "a" * 64,
            "exact_file_set": True,
        }
    )

    with pytest.raises(seed_postgres.SeedError, match="integrity/version mismatch"):
        seed_postgres._manifest_sha256_from_integrity(
            integrity,
            expected_bundle_version="2.0.0",
        )


def test_knowledge_embedding_maps_to_pgvector_contract() -> None:
    archive = seed_postgres.load_seed_archive(SEED_ARCHIVE)
    spec = next(
        table
        for table in seed_postgres.REFERENCE_TABLES
        if table.name == "knowledge_chunks"
    )
    target_columns = (
        "chunk_id",
        "source_id",
        "fact_id",
        "ordinal",
        "content_vi",
        "content_hash",
        "embedding",
        "embedding_model",
        "embedding_dimension",
        "approval_status",
        "retrieval_eligible",
        "created_at",
        "embedded_at",
    )

    columns, rows = seed_postgres._archive_table_rows(
        archive,
        spec=spec,
        target_columns=target_columns,
    )

    assert "embedding" in columns
    assert len(rows) == 34
    assert rows[0]["embedding_model"] == "Vietnamese_Embedding"
    assert rows[0]["embedding_dimension"] == 1024
    assert len(json.loads(rows[0]["embedding"])) == 1024


def test_archive_checksum_is_required_and_detects_tampering() -> None:
    scratch = BACKEND_ROOT.parent.parent / ".tmp" / f"seed-check-{uuid4().hex}"
    scratch.mkdir(parents=True)
    archive = scratch / SEED_ARCHIVE.name
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    try:
        archive.write_bytes(SEED_ARCHIVE.read_bytes() + b"tampered")
        checksum.write_text(
            (SEED_ARCHIVE.with_suffix(SEED_ARCHIVE.suffix + ".sha256")).read_text(
                encoding="ascii"
            ),
            encoding="ascii",
        )

        with pytest.raises(seed_postgres.SeedError, match="filename|hash mismatch"):
            seed_postgres.load_seed_archive(archive)
    finally:
        checksum.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        scratch.rmdir()


def test_insert_statement_is_idempotent_and_casts_typed_values() -> None:
    spec = next(
        table
        for table in seed_postgres.REFERENCE_TABLES
        if table.name == "knowledge_chunks"
    )
    statement = seed_postgres._insert_statement(
        spec,
        ("chunk_id", "content_vi", "embedding"),
    )

    assert "ON CONFLICT" in statement
    assert "DO UPDATE" in statement
    assert "CAST(:embedding AS vector)" in statement
