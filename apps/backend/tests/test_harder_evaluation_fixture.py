from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return " ".join(re.findall(r"[a-z0-9]+", plain.replace("đ", "d")))


def test_second_500_case_fixture_is_complete_unique_and_disjoint() -> None:
    root = Path(__file__).resolve().parents[3]
    old = json.loads(
        (root / "data/test-fixtures/24-hard-rag-evaluation-500.json").read_text(
            encoding="utf-8"
        )
    )
    new = json.loads(
        (root / "data/test-fixtures/25-harder-rag-evaluation-500.json").read_text(
            encoding="utf-8"
        )
    )
    records = new["records"]
    normalized = [_fold(record["query"]) for record in records]
    old_normalized = {_fold(record["query"]) for record in old["records"]}

    assert len(records) == 500
    assert len(set(normalized)) == 500
    assert not set(normalized).intersection(old_normalized)
    assert Counter(record["category"] for record in records) == {
        "schedule_compact_open_only": 180,
        "price_compact_exact_runtime": 140,
        "official_fact_cross_intent": 80,
        "bhyt_compact_tier_boundary": 50,
        "emergency": 10,
        "administrative_emergency_word": 10,
        "personal_bhyt_refusal": 10,
        "security": 10,
        "ocr_boundary": 10,
    }


def test_schedule_fixture_never_expects_closed_rows() -> None:
    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (root / "data/test-fixtures/25-harder-rag-evaluation-500.json").read_text(
            encoding="utf-8"
        )
    )
    schedule_cases = [
        record
        for record in payload["records"]
        if record["category"] == "schedule_compact_open_only"
    ]

    assert schedule_cases
    assert all("closed" in " ".join(case["must_not_include"]) for case in schedule_cases)
