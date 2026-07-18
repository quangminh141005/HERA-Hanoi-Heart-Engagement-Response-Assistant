"""Validate and seed the migrated PostgreSQL database from a portable archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALEMBIC_REVISION = "0001_initial_schema"
ARCHIVE_FORMAT = "hera-postgres-seed-v1"


@dataclass(frozen=True)
class TableSpec:
    name: str
    primary_key: tuple[str, ...]


REFERENCE_TABLES = (
    TableSpec("bundle_meta", ("key",)),
    TableSpec("official_sources", ("source_id",)),
    TableSpec("official_facts", ("fact_id",)),
    TableSpec("fixed_response_templates", ("template_key", "version")),
    TableSpec("knowledge_chunks", ("chunk_id",)),
    TableSpec("service_catalog_records", ("service_record_id",)),
    TableSpec("service_price_snapshots", ("price_id",)),
    TableSpec("bhyt_household_policies", ("policy_id",)),
    TableSpec("bhyt_contribution_tiers", ("tier_id",)),
    TableSpec("schedule_documents", ("document_id",)),
    TableSpec("doctors", ("doctor_id",)),
    TableSpec("doctor_aliases", ("alias_normalized",)),
    TableSpec("schedule_entries", ("schedule_entry_id",)),
    TableSpec("schedule_entry_doctors", ("entry_id", "doctor_id", "session_key")),
    TableSpec("booking_capacity_rules", ("capacity_rule_id",)),
    TableSpec("booking_doctor_candidates", ("doctor_candidate_id",)),
    TableSpec("booking_sessions", ("booking_session_id",)),
    TableSpec(
        "booking_session_schedule_entries",
        ("booking_session_id", "entry_id"),
    ),
    TableSpec("support_channels", ("channel_id",)),
)

RUNTIME_TABLES = (
    "conversations",
    "chat_messages",
    "message_citations",
    "structured_record_refs",
    "booking_holds",
    "handoff_events",
    "feedback",
    "audit_events",
)

SEED_META_KEYS = {
    "postgres_seed_archive_sha256",
    "postgres_seed_manifest_sha256",
    "postgres_seed_revision",
    "postgres_seeded_at",
    "runtime_database",
}

JSON_COLUMNS = {
    "allowed_intents_json",
    "raw_json",
    "conditions_json",
    "raw_snapshot_json",
    "raw_metadata_json",
    "review_reasons_json",
    "raw_aliases_json",
    "source_schedule_entry_ids_json",
    "metadata_json",
}

BOOLEAN_COLUMNS = {
    "retrieval_eligible",
    "rag_eligible",
    "structured_lookup_eligible",
    "current_lookup_eligible",
    "historical_lookup_eligible",
    "production_eligible",
    "is_active",
    "historical",
    "source_value_exact",
    "needs_review",
    "runtime_eligible",
    "is_bookable_slot",
    "hospital_approved",
    "bookable",
    "prototype_only",
}


@dataclass(frozen=True)
class SeedArchive:
    path: Path
    archive_sha256: str
    bundle_version: str
    manifest_sha256: str
    tables: Mapping[str, Mapping[str, Any]]
    table_counts: Mapping[str, int]


class SeedError(RuntimeError):
    """Raised when the archive, migration, or target data is not safe to use."""


def _quote_identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise SeedError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expected_archive_hash(path: Path) -> str:
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    if not checksum_path.is_file():
        raise SeedError(f"Seed checksum file does not exist: {checksum_path}")
    parts = checksum_path.read_text(encoding="ascii").strip().split()
    if len(parts) != 2 or parts[1] != path.name:
        raise SeedError("Seed checksum file has an invalid format or filename")
    expected = parts[0].lower()
    if len(expected) != 64:
        raise SeedError("Seed checksum is not a SHA-256 value")
    try:
        int(expected, 16)
    except ValueError as exc:
        raise SeedError("Seed checksum is not hexadecimal") from exc
    return expected


def _manifest_sha256_from_integrity(
    raw_json: str,
    *,
    expected_bundle_version: str,
) -> str:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SeedError("bundle_meta.integrity_json is not valid JSON") from exc
    if str(payload.get("bundle_version", "")) != expected_bundle_version:
        raise SeedError("bundle_meta integrity/version mismatch")
    if payload.get("exact_file_set") is not True:
        raise SeedError("bundle_meta.integrity_json exact_file_set is not true")
    manifest = str(payload.get("manifest_sha256", "")).lower()
    if len(manifest) != 64:
        raise SeedError("bundle_meta.integrity_json has no valid manifest SHA-256")
    try:
        int(manifest, 16)
    except ValueError as exc:
        raise SeedError("bundle manifest SHA-256 is not hexadecimal") from exc
    return manifest


def load_seed_archive(path: Path) -> SeedArchive:
    """Load a checksum-pinned archive and validate its exact table contract."""

    if not path.is_file():
        raise SeedError(f"PostgreSQL seed archive does not exist: {path}")
    expected_hash = _expected_archive_hash(path)
    actual_hash = _sha256_file(path)
    if actual_hash != expected_hash:
        raise SeedError(
            f"PostgreSQL seed archive hash mismatch: {actual_hash} != {expected_hash}"
        )
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SeedError("PostgreSQL seed archive is not valid gzip JSON") from exc
    if payload.get("format") != ARCHIVE_FORMAT:
        raise SeedError(f"Unsupported seed format: {payload.get('format')!r}")
    if payload.get("alembic_revision") != ALEMBIC_REVISION:
        raise SeedError("Seed archive Alembic revision does not match the application")

    bundle_version = str(payload.get("bundle_version", ""))
    manifest_sha256 = str(payload.get("manifest_sha256", "")).lower()
    raw_tables = payload.get("tables")
    if (
        not bundle_version
        or len(manifest_sha256) != 64
        or not isinstance(raw_tables, list)
    ):
        raise SeedError("Seed archive metadata is incomplete")
    table_map: dict[str, Mapping[str, Any]] = {}
    specs = {spec.name: spec for spec in REFERENCE_TABLES}
    for table in raw_tables:
        if not isinstance(table, dict):
            raise SeedError("Seed archive contains an invalid table payload")
        name = str(table.get("name", ""))
        if name not in specs or name in table_map:
            raise SeedError(
                f"Seed archive contains unexpected/duplicate table {name!r}"
            )
        if tuple(table.get("primary_key", [])) != specs[name].primary_key:
            raise SeedError(f"Seed archive primary key mismatch for {name}")
        if not isinstance(table.get("columns"), list) or not isinstance(
            table.get("rows"), list
        ):
            raise SeedError(f"Seed archive rows/columns are invalid for {name}")
        table_map[name] = table
    missing = sorted(set(specs) - set(table_map))
    if missing:
        raise SeedError(f"Seed archive is missing tables: {', '.join(missing)}")

    counts = {name: len(table["rows"]) for name, table in table_map.items()}
    metadata_rows = table_map["bundle_meta"]["rows"]
    metadata = {
        str(row["key"]): str(row["value"])
        for row in metadata_rows
        if isinstance(row, dict) and "key" in row and "value" in row
    }
    if metadata.get("bundle_version") != bundle_version:
        raise SeedError("Seed archive and bundle_meta bundle_version differ")
    integrity_manifest = _manifest_sha256_from_integrity(
        metadata.get("integrity_json", ""),
        expected_bundle_version=bundle_version,
    )
    if integrity_manifest != manifest_sha256:
        raise SeedError("Seed archive and bundle integrity manifest hashes differ")

    expected_counts = payload.get("source_table_counts", {})
    for name, count in counts.items():
        if name in expected_counts and int(expected_counts[name]) != count:
            raise SeedError(
                f"Seed table count mismatch for {name}: {count} != {expected_counts[name]}"
            )
    return SeedArchive(
        path=path.resolve(),
        archive_sha256=actual_hash,
        bundle_version=bundle_version,
        manifest_sha256=manifest_sha256,
        tables=table_map,
        table_counts=counts,
    )


def _target_columns(connection: Any, table: str) -> tuple[str, ...]:
    from sqlalchemy import text

    rows = connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND is_generated = 'NEVER'
            ORDER BY ordinal_position
            """
        ),
        {"table_name": table},
    )
    return tuple(str(row[0]) for row in rows)


def _normalize_json(value: Any, *, table: str, column: str) -> str | None:
    if value is None:
        return None
    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise SeedError(f"Invalid JSON in {table}.{column}") from exc
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _normalize_embedding(value: Any, *, model: Any, dimension: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        vector = json.loads(value) if isinstance(value, str) else list(value)
        normalized = [float(component) for component in vector]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SeedError("knowledge_chunks embedding is not a numeric array") from exc
    if len(normalized) != 1024 or int(dimension or 0) != 1024:
        raise SeedError("Vietnamese_Embedding vectors must have dimension 1024")
    if str(model) != "Vietnamese_Embedding":
        raise SeedError("Only Vietnamese_Embedding vectors may be seeded")
    return json.dumps(normalized, separators=(",", ":"))


def _archive_table_rows(
    archive: SeedArchive,
    *,
    spec: TableSpec,
    target_columns: Sequence[str],
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    table = archive.tables[spec.name]
    source_columns = set(table["columns"])
    aliases: dict[str, str] = {}
    if spec.name == "knowledge_chunks":
        if "embedding_json" in source_columns:
            aliases["embedding"] = "embedding_json"
        if "allowed_for_retrieval" in source_columns:
            aliases["retrieval_eligible"] = "allowed_for_retrieval"
    columns = tuple(
        column
        for column in target_columns
        if column in source_columns or aliases.get(column) in source_columns
    )
    missing_keys = [item for item in spec.primary_key if item not in columns]
    if missing_keys:
        raise SeedError(f"Cannot seed {spec.name}; missing keys {missing_keys}")
    rows: list[dict[str, Any]] = []
    for raw in table["rows"]:
        record: dict[str, Any] = {}
        for column in columns:
            value = raw.get(aliases.get(column, column))
            if column in JSON_COLUMNS:
                value = _normalize_json(value, table=spec.name, column=column)
            elif column in BOOLEAN_COLUMNS and value is not None:
                value = bool(value)
            elif column == "embedding":
                value = _normalize_embedding(
                    value,
                    model=raw.get("embedding_model"),
                    dimension=raw.get("embedding_dimension"),
                )
            record[column] = value
        rows.append(record)
    return columns, rows


def _insert_statement(spec: TableSpec, columns: Sequence[str]) -> str:
    quoted = ", ".join(_quote_identifier(item) for item in columns)
    values = []
    for column in columns:
        parameter = f":{column}"
        if column in JSON_COLUMNS:
            parameter = f"CAST({parameter} AS JSONB)"
        elif column == "embedding":
            parameter = f"CAST({parameter} AS vector)"
        values.append(parameter)
    keys = ", ".join(_quote_identifier(item) for item in spec.primary_key)
    mutable = [item for item in columns if item not in spec.primary_key]
    action = "DO NOTHING"
    if mutable:
        assignments = ", ".join(
            f"{_quote_identifier(item)} = EXCLUDED.{_quote_identifier(item)}"
            for item in mutable
        )
        action = f"DO UPDATE SET {assignments}"
    return (
        f"INSERT INTO {_quote_identifier(spec.name)} ({quoted}) "
        f"VALUES ({', '.join(values)}) ON CONFLICT ({keys}) {action}"
    )


def _batched(
    rows: Sequence[dict[str, Any]], size: int
) -> Iterable[Sequence[dict[str, Any]]]:
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def _read_target_meta(connection: Any, key: str) -> str | None:
    from sqlalchemy import text

    row = connection.execute(
        text("SELECT value FROM bundle_meta WHERE key = :key"), {"key": key}
    ).fetchone()
    return str(row[0]) if row else None


def _assert_migration_revision(connection: Any) -> None:
    from sqlalchemy import text

    try:
        revisions = {
            str(row[0])
            for row in connection.execute(
                text("SELECT version_num FROM alembic_version")
            )
        }
    except Exception as exc:
        raise SeedError("PostgreSQL has not been migrated with Alembic") from exc
    if revisions != {ALEMBIC_REVISION}:
        raise SeedError(
            f"PostgreSQL revision mismatch: expected {ALEMBIC_REVISION}, got {sorted(revisions)}"
        )


def _runtime_table_counts(connection: Any) -> dict[str, int]:
    """Return runtime row counts before a reference-data replacement.

    Reference rows are foreign-key targets for citations and booking holds. A
    blanket ``TRUNCATE ... CASCADE`` would therefore delete user/runtime data.
    Replacement is deliberately allowed only on a clean development database.
    """

    from sqlalchemy import text

    return {
        table: int(
            connection.execute(
                text(f"SELECT COUNT(*) FROM {_quote_identifier(table)}")
            ).scalar_one()
        )
        for table in RUNTIME_TABLES
    }


def _replace_reference_data(connection: Any) -> None:
    from sqlalchemy import text

    runtime_counts = _runtime_table_counts(connection)
    non_empty = {name: count for name, count in runtime_counts.items() if count}
    if non_empty:
        details = ", ".join(f"{name}={count}" for name, count in non_empty.items())
        raise SeedError(
            "Refusing to replace reference data because runtime data exists "
            f"({details}). Use a fresh development database or back up and "
            "migrate runtime records explicitly."
        )
    names = [spec.name for spec in REFERENCE_TABLES]
    targets = ", ".join(_quote_identifier(item) for item in reversed(names))
    connection.execute(text(f"TRUNCATE TABLE {targets} RESTART IDENTITY CASCADE"))


def _write_seed_metadata(connection: Any, archive: SeedArchive) -> None:
    from sqlalchemy import text

    statement = text(
        """
        INSERT INTO bundle_meta(key, value) VALUES (:key, :value)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """
    )
    values = {
        "postgres_seed_archive_sha256": archive.archive_sha256,
        "postgres_seed_manifest_sha256": archive.manifest_sha256,
        "postgres_seed_revision": ALEMBIC_REVISION,
        "runtime_database": "postgresql",
    }
    connection.execute(
        statement,
        [{"key": key, "value": value} for key, value in values.items()],
    )
    connection.execute(
        text(
            """
            INSERT INTO bundle_meta(key, value)
            VALUES ('postgres_seeded_at', CURRENT_TIMESTAMP::text)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        )
    )


def seed_postgres(
    *,
    archive: SeedArchive,
    database_url: str,
    replace_reference_data: bool = False,
    batch_size: int = 500,
) -> Mapping[str, int]:
    if not database_url:
        raise SeedError("DATABASE_URL or --database-url is required")
    if batch_size < 1:
        raise SeedError("batch_size must be positive")
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    imported: dict[str, int] = {}
    try:
        with engine.begin() as target:
            target.execute(text("SELECT pg_advisory_xact_lock(484552410001)"))
            _assert_migration_revision(target)
            existing_bundle = _read_target_meta(target, "bundle_version")
            existing_manifest = _read_target_meta(
                target, "postgres_seed_manifest_sha256"
            )
            if existing_bundle and existing_bundle != archive.bundle_version:
                if not replace_reference_data:
                    raise SeedError(
                        "PostgreSQL has a different bundle; pass --replace-reference-data"
                    )
            if existing_manifest and existing_manifest != archive.manifest_sha256:
                if not replace_reference_data:
                    raise SeedError(
                        "PostgreSQL has a different manifest; pass --replace-reference-data"
                    )
            if replace_reference_data:
                _replace_reference_data(target)

            for spec in REFERENCE_TABLES:
                target_columns = _target_columns(target, spec.name)
                if not target_columns:
                    raise SeedError(
                        f"Migration is missing PostgreSQL table {spec.name}"
                    )
                columns, rows = _archive_table_rows(
                    archive,
                    spec=spec,
                    target_columns=target_columns,
                )
                if rows:
                    statement = text(_insert_statement(spec, columns))
                    for batch in _batched(rows, batch_size):
                        target.execute(statement, list(batch))
                imported[spec.name] = len(rows)
            for table, expected in imported.items():
                if table == "bundle_meta":
                    target_keys = {
                        str(row[0])
                        for row in target.execute(text("SELECT key FROM bundle_meta"))
                    }
                    archive_keys = {
                        str(row["key"]) for row in archive.tables["bundle_meta"]["rows"]
                    }
                    missing_keys = archive_keys - target_keys
                    unexpected_keys = target_keys - archive_keys - SEED_META_KEYS
                    if missing_keys or unexpected_keys:
                        raise SeedError(
                            "Post-seed bundle_meta key mismatch: "
                            f"missing={sorted(missing_keys)}, "
                            f"unexpected={sorted(unexpected_keys)}"
                        )
                    continue
                actual = int(
                    target.execute(
                        text(f"SELECT COUNT(*) FROM {_quote_identifier(table)}")
                    ).scalar_one()
                )
                if actual != expected:
                    raise SeedError(
                        f"Post-seed count mismatch for {table}: {actual} != {expected}"
                    )
            _write_seed_metadata(target, archive)
    finally:
        engine.dispose()
    return imported


def _default_archive_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "hera_postgres_seed.json.gz"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-archive", type=Path, default=_default_archive_path())
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy PostgreSQL URL; prefer DATABASE_URL to keep it out of history",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-reference-data", action="store_true")
    parser.add_argument("--expected-bundle-version", default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    return parser


def _summary(
    archive: SeedArchive,
    imported: Mapping[str, int] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "validated" if imported is None else "seeded",
        "archive_format": ARCHIVE_FORMAT,
        "archive_sha256": archive.archive_sha256,
        "bundle_version": archive.bundle_version,
        "manifest_sha256": archive.manifest_sha256,
        "source_table_counts": dict(sorted(archive.table_counts.items())),
    }
    if imported is not None:
        result["imported_table_counts"] = dict(imported)
        result["alembic_revision"] = ALEMBIC_REVISION
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        archive = load_seed_archive(args.seed_archive)
        if (
            args.expected_bundle_version
            and archive.bundle_version != args.expected_bundle_version
        ):
            raise SeedError(
                f"Unexpected bundle_version: expected {args.expected_bundle_version}, "
                f"got {archive.bundle_version}"
            )
        imported = None
        if not args.dry_run:
            imported = seed_postgres(
                archive=archive,
                database_url=args.database_url or os.environ.get("DATABASE_URL", ""),
                replace_reference_data=args.replace_reference_data,
                batch_size=args.batch_size,
            )
        print(json.dumps(_summary(archive, imported), ensure_ascii=False, indent=2))
        return 0
    except SeedError as exc:
        print(f"seed_postgres: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
