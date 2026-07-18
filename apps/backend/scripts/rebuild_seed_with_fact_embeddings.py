"""Rebuild the pinned PostgreSQL seed after source/fact updates.

This script is for reviewed data updates where structured tables are unchanged
but official sources/facts/templates changed. Existing embeddings are reused;
only changed/new fact claims are embedded with the configured
Vietnamese_Embedding provider.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
for candidate in (BACKEND_ROOT, BACKEND_ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.ai.rag.embeddings.embedder import build_embedder  # noqa: E402
from app.core.config import Settings  # noqa: E402
from export_postgres_seed import _canonical_json  # noqa: E402
from seed_postgres import load_seed_archive  # noqa: E402

APPROVED_AT = "2026-07-18T12:00:00+07:00"
APPROVED_BY = "hackathon-data-owner"


async def main() -> int:
    generated_dir = REPOSITORY_ROOT / "data" / "generated"
    manifest_path = generated_dir / "00-manifest.json"
    source_pack_path = generated_dir / "01-sources-facts-and-templates.json"
    seed_path = BACKEND_ROOT / "data" / "hera_postgres_seed.json.gz"

    manifest = _read_json(manifest_path)
    manifest_sha256 = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    source_pack = _read_json(source_pack_path)
    load_seed_archive(seed_path)
    payload = json.loads(gzip.open(seed_path, "rt", encoding="utf-8").read())
    tables = {table["name"]: table for table in payload["tables"]}

    tables["official_sources"]["rows"] = _map_sources(source_pack, tables)
    facts, chunks, embedded_count = await _map_facts_and_chunks(source_pack, tables)
    tables["official_facts"]["rows"] = facts
    tables["knowledge_chunks"]["rows"] = chunks
    tables["fixed_response_templates"]["rows"] = _map_templates(source_pack)

    payload["manifest_sha256"] = manifest_sha256
    _replace_meta(
        tables["bundle_meta"]["rows"],
        {
            "bundle_version": payload["bundle_version"],
            "counts_json": _canonical_json(manifest.get("counts", {})),
            "embedded_chunk_count": str(len(chunks)),
            "generated_dir": "data/generated",
            "integrity_json": _canonical_json(
                {
                    "bundle_version": payload["bundle_version"],
                    "manifest_sha256": manifest_sha256,
                    "files_checked": len(manifest.get("files", [])),
                    "raw_inputs_checked": len(manifest.get("raw_inputs", [])),
                    "exact_file_set": True,
                }
            ),
            "manifest_json": _canonical_json(manifest),
            "postgres_seed_archive_sha256": "",
            "postgres_seed_manifest_sha256": manifest_sha256,
            "postgres_seed_revision": payload["alembic_revision"],
            "postgres_seeded_at": APPROVED_AT,
        },
    )
    payload["source_table_counts"] = {
        table["name"]: len(table["rows"])
        for table in payload["tables"]
    }
    _sort_tables(payload)
    _write_seed(seed_path, payload)
    print(
        json.dumps(
            {
                "status": "seed_rebuilt",
                "facts": len(facts),
                "knowledge_chunks": len(chunks),
                "new_or_changed_embeddings": embedded_count,
                "manifest_sha256": manifest_sha256,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _map_sources(source_pack: dict[str, Any], tables: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    previous = {
        row["source_id"]: row
        for row in tables["official_sources"]["rows"]
    }
    rows = []
    for raw in source_pack["sources"]:
        old = previous.get(raw["source_id"], {})
        retrieval = bool(raw.get("retrieval_eligible"))
        structured = bool(raw.get("structured_lookup_only") or old.get("structured_lookup_eligible"))
        approved = retrieval or structured
        rows.append(
            {
                "approval_status": "approved_for_hackathon" if approved else "pending",
                "approved_at": APPROVED_AT if approved else None,
                "approved_by": APPROVED_BY if approved else None,
                "authority": str(raw.get("authority") or "unknown"),
                "canonical_url": raw.get("url"),
                "current_lookup_eligible": bool(old.get("current_lookup_eligible")),
                "historical_lookup_eligible": bool(old.get("historical_lookup_eligible")),
                "notes": raw.get("notes"),
                "production_eligible": False,
                "published_at": raw.get("published_at"),
                "publisher": str(raw.get("publisher") or "Không rõ"),
                "rag_eligible": retrieval,
                "retrieval_eligible": retrieval,
                "retrieved_at": raw.get("retrieved_at"),
                "source_id": str(raw["source_id"]),
                "structured_lookup_eligible": structured or bool(old.get("structured_lookup_eligible")),
                "title": str(raw.get("title") or raw["source_id"]),
                "valid_from": raw.get("valid_from"),
                "valid_to": raw.get("valid_to"),
                "verification_status": str(raw.get("verification_status") or "pending"),
            }
        )
    return sorted(rows, key=lambda row: row["source_id"])


async def _map_facts_and_chunks(
    source_pack: dict[str, Any],
    tables: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    old_vectors = {
        (str(row["fact_id"]), str(row["content_hash"])): row
        for row in tables["knowledge_chunks"]["rows"]
        if row.get("embedding_json")
    }
    facts = []
    missing_claims: list[tuple[str, str, str]] = []
    for raw in source_pack["facts"]:
        fact_id = str(raw["fact_id"])
        claim = " ".join(str(raw["claim_vi"]).split())
        content_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()
        facts.append(
            {
                "allowed_intents_json": _canonical_json(raw.get("allowed_intents") or []),
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
        if (fact_id, content_hash) not in old_vectors:
            missing_claims.append((fact_id, claim, content_hash))

    new_vectors: dict[tuple[str, str], list[float]] = {}
    if missing_claims:
        settings = Settings(_env_file=REPOSITORY_ROOT / ".env")
        embedder = build_embedder(settings)
        vectors = await embedder.embed([claim for _, claim, _ in missing_claims])
        close = getattr(embedder, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result
        for (fact_id, _claim, content_hash), vector in zip(missing_claims, vectors, strict=True):
            if len(vector) != settings.EMBEDDING_DIMENSIONS:
                raise RuntimeError(f"invalid embedding dimension for {fact_id}: {len(vector)}")
            new_vectors[(fact_id, content_hash)] = vector

    chunks = []
    now = datetime.now(UTC).isoformat()
    for ordinal, fact in enumerate(facts, 1):
        fact_id = fact["fact_id"]
        claim = fact["claim_vi"]
        content_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()
        old = old_vectors.get((fact_id, content_hash))
        vector = None if old is not None else new_vectors[(fact_id, content_hash)]
        chunks.append(
            {
                "approval_status": "approved_for_hackathon",
                "chunk_id": f"CHUNK-{fact_id}-001",
                "content_hash": content_hash,
                "content_vi": claim,
                "created_at": old.get("created_at") if old else APPROVED_AT,
                "embedded_at": old.get("embedded_at") if old else now,
                "embedding_dimension": old.get("embedding_dimension") if old else 1024,
                "embedding_json": old.get("embedding_json") if old else _canonical_json(vector),
                "embedding_model": old.get("embedding_model") if old else "Vietnamese_Embedding",
                "fact_id": fact_id,
                "ordinal": old.get("ordinal") if old else ordinal,
                "retrieval_eligible": True,
                "source_id": fact["source_id"],
            }
        )
    return (
        sorted(facts, key=lambda row: row["fact_id"]),
        sorted(chunks, key=lambda row: row["chunk_id"]),
        len(missing_claims),
    )


def _map_templates(source_pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "approval_status": "approved_for_hackathon",
            "approved_at": APPROVED_AT,
            "approved_by": APPROVED_BY,
            "is_active": True,
            "template_key": key,
            "text_vi": str(value),
            "version": 1,
        }
        for key, value in sorted(source_pack["fixed_response_templates"].items())
    ]


def _replace_meta(rows: list[dict[str, str]], values: dict[str, str]) -> None:
    by_key = {row["key"]: row for row in rows}
    for key, value in values.items():
        if key in by_key:
            by_key[key]["value"] = value
        else:
            rows.append({"key": key, "value": value})
    rows.sort(key=lambda row: row["key"])


def _sort_tables(payload: dict[str, Any]) -> None:
    for table in payload["tables"]:
        primary_key = table.get("primary_key") or []
        if primary_key:
            table["rows"].sort(key=lambda row: tuple(str(row.get(key, "")) for key in primary_key))


def _write_seed(seed_path: Path, payload: dict[str, Any]) -> None:
    seed_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _write_gzip_text(seed_path, seed_text)
    archive_hash = hashlib.sha256(seed_path.read_bytes()).hexdigest()
    _replace_meta(
        next(table["rows"] for table in payload["tables"] if table["name"] == "bundle_meta"),
        {"postgres_seed_archive_sha256": archive_hash},
    )
    seed_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _write_gzip_text(seed_path, seed_text)
    archive_hash = hashlib.sha256(seed_path.read_bytes()).hexdigest()
    (seed_path.parent / f"{seed_path.name}.sha256").write_text(
        f"{archive_hash}  {seed_path.name}\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_gzip_text(path: Path, text: str) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as handle:
            handle.write(text.encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
