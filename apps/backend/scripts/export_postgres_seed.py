"""Export canonical PostgreSQL reference data as a deterministic seed archive.

This is the reverse of ``seed_postgres.py``. Runtime/user tables are never
exported. The existing checksum-pinned archive is used as the exact schema
template, so an Alembic revision or column-contract change fails closed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

SCRIPTS_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPTS_ROOT.parent
for candidate in (SCRIPTS_ROOT, BACKEND_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.structured.manifest import (  # noqa: E402
    BundleIntegrityError,
    validate_generated_bundle,
)
from seed_postgres import (  # noqa: E402
    ALEMBIC_REVISION,
    ARCHIVE_FORMAT,
    REFERENCE_TABLES,
    SEED_META_KEYS,
    SeedError,
    _assert_migration_revision,
    _quote_identifier,
    _target_columns,
    load_seed_archive,
)

SNAPSHOT_MANIFEST_FORMAT = "hera-postgres-reference-snapshot-v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    raise SeedError(f"Unsupported PostgreSQL value in reference snapshot: {type(value)!r}")


def _select_expression(table: str, source_column: str) -> tuple[str, str]:
    target_column = source_column
    expression = _quote_identifier(source_column)
    if table == "knowledge_chunks" and source_column == "embedding_json":
        target_column = "embedding"
        expression = '"embedding"::text'
    elif table == "knowledge_chunks" and source_column == "allowed_for_retrieval":
        target_column = "retrieval_eligible"
        expression = '"retrieval_eligible"'
    return target_column, f"{expression} AS {_quote_identifier(source_column)}"


def _read_table(connection: Any, table: Mapping[str, Any]) -> list[dict[str, Any]]:
    name = str(table["name"])
    columns = [str(item) for item in table["columns"]]
    primary_key = [str(item) for item in table["primary_key"]]
    target_columns = set(_target_columns(connection, name))
    expressions: list[str] = []
    source_to_target: dict[str, str] = {}
    for source_column in columns:
        target_column, expression = _select_expression(name, source_column)
        if target_column not in target_columns:
            raise SeedError(
                f"PostgreSQL table {name} is missing template column {target_column}"
            )
        source_to_target[source_column] = target_column
        expressions.append(expression)
    order_columns = [source_to_target[item] for item in primary_key]
    query = (
        f"SELECT {', '.join(expressions)} FROM {_quote_identifier(name)} "
        f"ORDER BY {', '.join(_quote_identifier(item) for item in order_columns)}"
    )
    rows = []
    for raw in connection.execute(text(query)).mappings():
        record = {column: _jsonable(raw[column]) for column in columns}
        embedding = record.get("embedding_json")
        if isinstance(embedding, str) and embedding:
            try:
                record["embedding_json"] = [float(item) for item in json.loads(embedding)]
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise SeedError("PostgreSQL knowledge embedding is invalid") from exc
        rows.append(record)
    return rows


def _read_reference_tables(connection: Any, template: Any) -> list[dict[str, Any]]:
    template_tables = template.tables
    payloads: list[dict[str, Any]] = []
    for spec in REFERENCE_TABLES:
        table = template_tables[spec.name]
        if spec.name == "bundle_meta":
            rows = [
                {"key": str(row[0]), "value": str(row[1])}
                for row in connection.execute(
                    text("SELECT key, value FROM bundle_meta ORDER BY key")
                )
                if str(row[0]) not in SEED_META_KEYS
            ]
        else:
            rows = _read_table(connection, table)
        payloads.append(
            {
                "name": spec.name,
                "primary_key": list(spec.primary_key),
                "columns": [str(item) for item in table["columns"]],
                "rows": rows,
            }
        )
    return payloads


def _table_map(tables: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(table["name"]): table for table in tables}


def _meta_map(bundle_meta: dict[str, Any]) -> dict[str, str]:
    return {
        str(row["key"]): str(row["value"])
        for row in bundle_meta["rows"]
        if isinstance(row, dict) and "key" in row and "value" in row
    }


def _replace_meta(bundle_meta: dict[str, Any], updates: Mapping[str, str]) -> None:
    values = _meta_map(bundle_meta)
    values.update(updates)
    for key in SEED_META_KEYS:
        values.pop(key, None)
    bundle_meta["rows"] = [
        {"key": key, "value": values[key]} for key in sorted(values)
    ]


def _schedule_summary(tables: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    documents = tables["schedule_documents"]["rows"]
    entries = tables["schedule_entries"]["rows"]
    entries_by_document = Counter(str(row.get("document_id")) for row in entries)
    entry_rows_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entries:
        entry_rows_by_document[str(row.get("document_id"))].append(row)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        start = str(document.get("folder_week_start") or "")
        end = str(document.get("folder_week_end") or "")
        if not start or not end:
            raise SeedError("Every schedule document must declare its folder week")
        grouped[(start, end)].append(document)

    summaries = []
    for (start, end), week_documents in sorted(grouped.items()):
        week_entries = [
            row
            for document in week_documents
            for row in entry_rows_by_document[str(document["document_id"])]
        ]
        summaries.append(
            {
                "week_start": start,
                "week_end": end,
                "documents_discovered": len(week_documents),
                "documents_validation_accepted": sum(
                    row.get("validation_status") == "accepted"
                    for row in week_documents
                ),
                "documents_review_required": sum(
                    row.get("validation_status") == "review_required"
                    for row in week_documents
                ),
                "entries_published_to_review_dataset": sum(
                    entries_by_document[str(row["document_id"])]
                    for row in week_documents
                ),
                "named_assignments": sum(
                    row.get("assignee_type") == "named_doctor" for row in week_entries
                ),
                "generic_assignments": sum(
                    row.get("assignee_type") == "generic" for row in week_entries
                ),
                "closed_entries": sum(
                    row.get("duty_status") == "closed" for row in week_entries
                ),
                "runtime_eligible_entries": sum(
                    row.get("runtime_eligible") is True for row in week_entries
                ),
            }
        )
    return summaries


def _manifest_counts(tables: Mapping[str, dict[str, Any]]) -> dict[str, int]:
    documents = tables["schedule_documents"]["rows"]
    chunks = tables["knowledge_chunks"]["rows"]
    return {
        "sources": len(tables["official_sources"]["rows"]),
        "seed_facts": len(chunks),
        "historical_price_rows": len(tables["service_catalog_records"]["rows"]),
        "nested_facility_prices": len(tables["service_price_snapshots"]["rows"]),
        "bhyt_policies": len(tables["bhyt_household_policies"]["rows"]),
        "bhyt_tiers": len(tables["bhyt_contribution_tiers"]["rows"]),
        "schedule_documents": len(documents),
        "schedule_documents_accepted": sum(
            row.get("validation_status") == "accepted" for row in documents
        ),
        "schedule_documents_review_required": sum(
            row.get("validation_status") == "review_required" for row in documents
        ),
        "schedule_entries": len(tables["schedule_entries"]["rows"]),
        "doctor_candidates": len(tables["booking_doctor_candidates"]["rows"]),
        "support_channels": len(tables["support_channels"]["rows"]),
        "prototype_doctors": len(tables["doctors"]["rows"]),
        "booking_sessions": len(tables["booking_sessions"]["rows"]),
    }


def _build_snapshot_payload(
    template: Any,
    tables: list[dict[str, Any]],
    *,
    generated_manifest: Mapping[str, Any],
    generated_manifest_sha256: str,
    generated_files_checked: int,
    generated_raw_inputs_checked: int,
    allow_manifest_rebind: bool,
) -> dict[str, Any]:
    mapped = _table_map(tables)
    bundle_meta = mapped["bundle_meta"]
    metadata = _meta_map(bundle_meta)
    bundle_version = metadata.get("bundle_version") or template.bundle_version
    if bundle_version != template.bundle_version:
        raise SeedError("PostgreSQL and template bundle versions differ")
    try:
        previous_manifest = json.loads(metadata.get("manifest_json", "{}"))
        previous_integrity = json.loads(metadata.get("integrity_json", "{}"))
    except json.JSONDecodeError as exc:
        raise SeedError("PostgreSQL bundle metadata JSON is invalid") from exc
    if previous_manifest.get("bundle_version") != bundle_version:
        raise SeedError("PostgreSQL manifest/bundle version mismatch")
    if (
        previous_integrity.get("manifest_sha256") != generated_manifest_sha256
        and not allow_manifest_rebind
    ):
        raise SeedError(
            "PostgreSQL was not seeded from this generated manifest; first update "
            "and review canonical rows, then use the explicit rebind workflow"
        )

    counts = _manifest_counts(mapped)
    expected_counts = generated_manifest.get("counts")
    if not isinstance(expected_counts, dict):
        raise SeedError("Generated manifest has no count contract")
    for key, actual in counts.items():
        expected = expected_counts.get(key)
        if expected is not None and expected != actual:
            raise SeedError(
                f"PostgreSQL reference count differs from manifest for {key}: "
                f"{actual} != {expected}"
            )
    actual_weeks = _schedule_summary(mapped)
    expected_weeks = generated_manifest.get("schedule_week_summaries")
    if not isinstance(expected_weeks, list):
        raise SeedError("Generated manifest has no schedule-week contract")
    week_keys = (
        "week_start",
        "week_end",
        "documents_validation_accepted",
        "documents_review_required",
        "entries_published_to_review_dataset",
    )
    actual_week_contract = [
        {key: item.get(key) for key in week_keys} for item in actual_weeks
    ]
    expected_week_contract = [
        {key: item.get(key) for key in week_keys}
        for item in expected_weeks
        if isinstance(item, dict)
    ]
    if actual_week_contract != expected_week_contract:
        raise SeedError(
            "PostgreSQL schedule weeks differ from the generated manifest; "
            "canonical rows must be updated/reviewed before export"
        )
    table_evidence = []
    for table in tables:
        evidence_rows = table["rows"]
        if table["name"] == "bundle_meta":
            evidence_rows = [
                row
                for row in evidence_rows
                if row["key"]
                not in {
                    "integrity_json",
                    "manifest_json",
                    "postgres_snapshot_json",
                }
            ]
        table_evidence.append(
            {
                "name": table["name"],
                "rows": len(evidence_rows),
                "sha256": hashlib.sha256(
                    _canonical_json(evidence_rows).encode("utf-8")
                ).hexdigest(),
            }
        )

    snapshot_manifest = {
        "format": SNAPSHOT_MANIFEST_FORMAT,
        "bundle_version": bundle_version,
        "alembic_revision": ALEMBIC_REVISION,
        "source_generated_manifest_sha256": generated_manifest_sha256,
        "tables": table_evidence,
    }
    snapshot_json = _canonical_json(snapshot_manifest)
    snapshot_sha256 = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    snapshot_manifest["snapshot_sha256"] = snapshot_sha256
    embedded = sum(
        bool(row.get("embedding_json")) for row in mapped["knowledge_chunks"]["rows"]
    )
    _replace_meta(
        bundle_meta,
        {
            "bundle_version": bundle_version,
            "counts_json": _canonical_json(counts),
            "embedded_chunk_count": str(embedded),
            "generated_dir": "data/generated",
            "integrity_json": _canonical_json(
                {
                    "bundle_version": bundle_version,
                    "manifest_sha256": generated_manifest_sha256,
                    "files_checked": generated_files_checked,
                    "raw_inputs_checked": generated_raw_inputs_checked,
                    "exact_file_set": True,
                }
            ),
            "manifest_json": _canonical_json(generated_manifest),
            "postgres_snapshot_json": _canonical_json(snapshot_manifest),
        },
    )
    source_counts = {
        str(table["name"]): len(table["rows"]) for table in tables
    }
    return {
        "format": ARCHIVE_FORMAT,
        "alembic_revision": ALEMBIC_REVISION,
        "bundle_version": bundle_version,
        "manifest_sha256": generated_manifest_sha256,
        "source_table_counts": source_counts,
        "tables": tables,
    }


def _write_deterministic_archive(output: Path, payload: Mapping[str, Any]) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (_canonical_json(payload) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as raw_stream:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw_stream,
                mtime=0,
            ) as compressed:
                compressed.write(raw)
            raw_stream.flush()
            os.fsync(raw_stream.fileno())
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        sidecar = output.with_suffix(output.suffix + ".sha256")
        sidecar_temporary = temporary.with_suffix(".sha256.tmp")
        sidecar_temporary.write_text(
            f"{digest}  {output.name}\n", encoding="ascii", newline="\n"
        )
        temporary.replace(output)
        sidecar_temporary.replace(sidecar)
        for path in (output, sidecar):
            try:
                path.chmod(0o644)
            except OSError:
                pass
        return digest
    finally:
        temporary.unlink(missing_ok=True)
        temporary.with_suffix(".sha256.tmp").unlink(missing_ok=True)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    default_archive = Path(__file__).resolve().parents[1] / "data/hera_postgres_seed.json.gz"
    default_generated = Path(__file__).resolve().parents[3] / "data/generated"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=default_archive)
    parser.add_argument("--output", type=Path, default=default_archive)
    parser.add_argument("--generated-dir", type=Path, default=default_generated)
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy PostgreSQL URL; prefer DATABASE_URL to keep it out of history",
    )
    parser.add_argument("--confirm-overwrite", action="store_true")
    parser.add_argument("--rebind-generated-manifest", action="store_true")
    parser.add_argument("--confirm-rebind", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    database_url = args.database_url or os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("export_postgres_seed: DATABASE_URL is required", file=sys.stderr)
        return 2
    if args.rebind_generated_manifest:
        if args.confirm_rebind != "REVIEWED_CANONICAL_POSTGRES":
            print(
                "export_postgres_seed: rebind requires "
                "--confirm-rebind REVIEWED_CANONICAL_POSTGRES",
                file=sys.stderr,
            )
            return 2
    elif args.confirm_rebind:
        print(
            "export_postgres_seed: --confirm-rebind requires "
            "--rebind-generated-manifest",
            file=sys.stderr,
        )
        return 2
    output = args.output.resolve()
    if output.exists() and not args.confirm_overwrite:
        print(
            "export_postgres_seed: output exists; pass --confirm-overwrite",
            file=sys.stderr,
        )
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.with_suffix(output.suffix + ".lock")
    lock_descriptor: int | None = None
    engine = None
    try:
        template = load_seed_archive(args.template.resolve())
        generated = validate_generated_bundle(args.generated_dir.resolve())
        if generated.bundle_version != template.bundle_version:
            raise SeedError("Generated data and seed template bundle versions differ")
        try:
            generated_manifest = json.loads(
                (args.generated_dir.resolve() / "00-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise SeedError("Validated generated manifest could not be loaded") from exc
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        engine = create_engine(database_url, future=True, pool_pre_ping=True)
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SELECT pg_advisory_xact_lock(484552410001)"))
                _assert_migration_revision(connection)
                tables = _read_reference_tables(connection, template)
                payload = _build_snapshot_payload(
                    template,
                    tables,
                    generated_manifest=generated_manifest,
                    generated_manifest_sha256=generated.manifest_sha256,
                    generated_files_checked=generated.files_checked,
                    generated_raw_inputs_checked=generated.raw_inputs_checked,
                    allow_manifest_rebind=args.rebind_generated_manifest,
                )
                transaction.commit()
            except Exception:
                transaction.rollback()
                raise
        digest = _write_deterministic_archive(output, payload)
        print(
            json.dumps(
                {
                    "status": "exported",
                    "runtime_database": "postgresql",
                    "output": str(output),
                    "archive_sha256": digest,
                    "manifest_sha256": payload["manifest_sha256"],
                    "table_counts": payload["source_table_counts"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (BundleIntegrityError, OSError, SeedError, ValueError) as exc:
        print(f"export_postgres_seed: {exc}", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()
        if lock_descriptor is not None:
            os.close(lock_descriptor)
            lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
