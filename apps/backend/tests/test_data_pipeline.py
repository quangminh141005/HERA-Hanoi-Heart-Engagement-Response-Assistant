from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import build_seed_from_generated, seed_postgres

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
SEED_ARCHIVE = BACKEND_ROOT / "data/hera_postgres_seed.json.gz"
GENERATED_DIR = REPOSITORY_ROOT / "data/generated"


def test_current_generated_bundle_builds_complete_staged_seed() -> None:
    baseline = seed_postgres.load_seed_archive(SEED_ARCHIVE)

    payload = build_seed_from_generated.build_candidate_payload(
        baseline_archive=baseline,
        generated_dir=GENERATED_DIR,
    )

    counts = payload["source_table_counts"]
    assert payload["manifest_sha256"] == baseline.manifest_sha256
    assert counts["service_catalog_records"] == 2_946
    assert counts["service_price_snapshots"] == 4_051
    assert counts["bhyt_contribution_tiers"] == 10
    assert counts["schedule_documents"] == 18
    assert counts["schedule_entries"] == 1_382
    assert counts["doctors"] == 82
    assert counts["booking_sessions"] == 771
    assert counts["support_channels"] == 2
    chunks = next(
        table["rows"]
        for table in payload["tables"]
        if table["name"] == "knowledge_chunks"
    )
    assert len(chunks) == 11
    assert all(row["embedding_model"] == "Vietnamese_Embedding" for row in chunks)
    assert all(row["embedding_dimension"] == 1024 for row in chunks)


def test_changed_fact_fails_closed_without_matching_embedding() -> None:
    baseline_archive = seed_postgres.load_seed_archive(SEED_ARCHIVE)
    baseline = build_seed_from_generated._rows_by_table(baseline_archive)
    source_pack = json.loads(
        (GENERATED_DIR / "01-sources-facts-and-templates.json").read_text(
            encoding="utf-8"
        )
    )
    changed = deepcopy(source_pack)
    changed["facts"][0]["claim_vi"] += " Nội dung đã thay đổi."

    with pytest.raises(
        build_seed_from_generated.SeedError,
        match="no matching.*Embedding",
    ):
        build_seed_from_generated._map_facts_and_chunks(
            changed,
            baseline,
            "2026-07-18T00:00:00+07:00",
        )


class _ScalarResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class _RuntimeConnection:
    def __init__(self, non_empty_table: str) -> None:
        self.non_empty_table = non_empty_table
        self.statements: list[str] = []

    def execute(self, statement: object) -> _ScalarResult:
        sql = str(statement)
        self.statements.append(sql)
        return _ScalarResult(1 if self.non_empty_table in sql else 0)


def test_reference_replacement_refuses_to_delete_runtime_data() -> None:
    connection = _RuntimeConnection("booking_holds")

    with pytest.raises(seed_postgres.SeedError, match="runtime data exists"):
        seed_postgres._replace_reference_data(connection)

    assert not any("TRUNCATE" in statement for statement in connection.statements)


def test_builder_requires_explicit_confirmation_and_staged_output() -> None:
    output = REPOSITORY_ROOT / ".tmp" / f"candidate-{uuid4().hex}.json.gz"

    assert (
        build_seed_from_generated.main(
            ["--generated-dir", str(GENERATED_DIR), "--output", str(output)]
        )
        == 2
    )
    output.unlink(missing_ok=True)
    assert not output.exists()
    assert (
        build_seed_from_generated.main(
            [
                "--generated-dir",
                str(GENERATED_DIR),
                "--output",
                str(SEED_ARCHIVE),
                "--confirm-build",
                "BUILD_REVIEWED_DATA_CANDIDATE",
            ]
        )
        == 2
    )
