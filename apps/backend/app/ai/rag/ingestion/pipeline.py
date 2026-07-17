"""Official knowledge ingestion pipeline placeholder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionPlan:
    """Planned ingestion inputs for official hospital documents."""

    source_paths: list[str]
    notes: list[str]


def build_ingestion_plan(source_paths: list[str]) -> IngestionPlan:
    """Build an ingestion plan without processing data yet."""

    return IngestionPlan(
        source_paths=source_paths,
        notes=[
            "TODO: verify each document is an official hospital source.",
            "TODO: attach scope metadata such as facility, department, "
            "and effective date.",
            "TODO: redact sensitive patient data before indexing.",
        ],
    )
