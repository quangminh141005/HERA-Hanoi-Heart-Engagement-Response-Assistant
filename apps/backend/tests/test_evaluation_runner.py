from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from run_evaluation import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    LLM_MODEL,
    DatasetValidationError,
    EvidenceCatalog,
    build_report,
    evaluate_case,
    evaluate_conversation,
    load_evaluation_dataset,
    run_conversations,
    run_evaluation_cases,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATED_DATA = REPO_ROOT / "data" / "generated"


class SequenceClient:
    transport_name = "stub"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.conversation_ids: list[str | None] = []

    def send(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        del message
        self.conversation_ids.append(conversation_id)
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def _catalog() -> EvidenceCatalog:
    return EvidenceCatalog(
        source_ids=frozenset({"SRC-1"}),
        fact_ids=frozenset({"FACT-1", "FACT-2"}),
        record_ids=frozenset({"SRC-1", "FACT-1", "FACT-2", "PRICE-1"}),
    )


def _response(**overrides: Any) -> dict[str, Any]:
    response = {
        "conversation_id": "conversation-id-0001",
        "answer_vi": "Thông tin bắt buộc, an toàn.",
        "response": "Thông tin bắt buộc, an toàn.",
        "response_type": "grounded_answer",
        "intent": "booking",
        "citations": [{"source_id": "SRC-1"}],
        "structured_record_ids": ["CHUNK-FACT-1-001"],
        "requires_handoff": False,
    }
    response.update(overrides)
    return response


def test_loads_exact_complete_release_dataset_and_manifest_hashes() -> None:
    dataset = load_evaluation_dataset(GENERATED_DATA)

    assert len(dataset.evaluation_cases) == 100
    assert len(dataset.conversation_scenarios) == 24
    assert dataset.evaluation_cases[0]["case_id"] == "EVAL-0001"
    assert dataset.evaluation_cases[-1]["case_id"] == "EVAL-0100"
    assert dataset.conversation_scenarios[0]["scenario_id"] == "SYN-CONV-001"
    assert dataset.conversation_scenarios[-1]["scenario_id"] == "SYN-CONV-024"
    assert len(dataset.manifest_sha256) == 64
    assert "FACT-BOOKING-LEAD-TIME" in dataset.evidence_catalog.fact_ids
    assert "PRICE-2025-000001-CS1" in dataset.evidence_catalog.record_ids


def test_loader_rejects_an_incomplete_dataset() -> None:
    with pytest.raises(DatasetValidationError, match="Cannot parse 00-manifest"):
        load_evaluation_dataset(REPO_ROOT / "scripts")


def test_case_checks_intent_phrases_and_resolved_evidence() -> None:
    case = {
        "case_id": "EVAL-TEST",
        "category": "grounded_official",
        "expected_intent": "booking",
        "expected_response_type": "grounded_answer",
        "must_include": ["thông tin bắt buộc"],
        "must_not_include": ["bịa đặt"],
        "required_source_fact_ids": ["FACT-1"],
        "allowed_fact_ids": ["FACT-1"],
        "required_structured_record_ids": [],
        "allowed_structured_record_selectors": [],
    }

    result = evaluate_case(case, _response(), _catalog())

    assert result.passed
    assert all(value is not False for value in result.assertions.values())


def test_case_reports_forbidden_and_unresolved_evidence() -> None:
    case = {
        "case_id": "EVAL-TEST",
        "category": "grounded_official",
        "expected_intent": "booking",
        "expected_response_type": "grounded_answer",
        "must_include": [],
        "must_not_include": ["bịa đặt"],
        "required_source_fact_ids": [],
        "allowed_fact_ids": [],
        "required_structured_record_ids": [],
        "allowed_structured_record_selectors": [],
    }
    response = _response(
        answer_vi="Đây là nội dung bịa đặt.",
        citations=[{"source_id": "SRC-UNKNOWN"}],
    )

    result = evaluate_case(case, response, _catalog())

    assert not result.passed
    assert result.assertions["forbidden_claims"] is False
    assert result.assertions["citation_record_resolution"] is False


def test_conversation_preserves_id_and_checks_each_turn_evidence() -> None:
    scenario = {
        "scenario_id": "SYN-CONV-TEST",
        "category": "grounded_follow_up",
        "expected_terminal_state": "grounded_answer",
        "turns": [
            {"role": "user", "content": "Câu một"},
            {
                "role": "assistant",
                "expected_response_type": "grounded_answer",
                "source_fact_ids": "FACT-1",
            },
            {"role": "user", "content": "Câu hai"},
            {
                "role": "assistant",
                "expected_response_type": "grounded_answer",
                "source_fact_ids": "FACT-2",
            },
        ],
    }
    client = SequenceClient(
        [
            _response(structured_record_ids=["CHUNK-FACT-1-001"]),
            _response(structured_record_ids=["CHUNK-FACT-2-001"]),
        ]
    )

    result = evaluate_conversation(scenario, client, _catalog())

    assert result.passed
    assert client.conversation_ids == [None, "conversation-id-0001"]


def test_release_loops_execute_all_100_cases_and_24_scenarios() -> None:
    dataset = load_evaluation_dataset(GENERATED_DATA)
    case_client = SequenceClient(
        [_response() for _ in range(len(dataset.evaluation_cases))]
    )

    case_results = run_evaluation_cases(
        dataset.evaluation_cases,
        case_client,
        dataset.evidence_catalog,
    )

    conversation_turn_count = sum(
        len(item["turns"]) // 2 for item in dataset.conversation_scenarios
    )
    conversation_client = SequenceClient(
        [_response() for _ in range(conversation_turn_count)]
    )
    conversation_results = run_conversations(
        dataset.conversation_scenarios,
        conversation_client,
        dataset.evidence_catalog,
    )

    assert len(case_results) == 100
    assert len(case_client.conversation_ids) == 100
    assert len(conversation_results) == 24
    assert len(conversation_client.conversation_ids) == conversation_turn_count


def test_report_contains_release_provenance_and_failure_list() -> None:
    dataset = load_evaluation_dataset(GENERATED_DATA)
    passing = evaluate_case(
        {
            "case_id": "EVAL-PASS",
            "category": "other",
            "expected_intent": "booking",
            "expected_response_type": "grounded_answer",
            "must_include": [],
            "must_not_include": [],
            "required_source_fact_ids": ["FACT-1"],
            "allowed_fact_ids": ["FACT-1"],
            "required_structured_record_ids": [],
            "allowed_structured_record_selectors": [],
        },
        _response(),
        _catalog(),
    )
    failing = evaluate_case(
        {
            "case_id": "EVAL-FAIL",
            "category": "other",
            "expected_intent": "wrong",
            "expected_response_type": "grounded_answer",
            "must_include": [],
            "must_not_include": [],
            "required_source_fact_ids": [],
            "allowed_fact_ids": [],
            "required_structured_record_ids": [],
            "allowed_structured_record_selectors": [],
        },
        _response(),
        _catalog(),
    )

    report = build_report(
        dataset,
        [passing, failing],
        [],
        repo_root=REPO_ROOT,
        transport="stub",
        base_url=None,
    )
    decoded = json.loads(json.dumps(report))

    assert decoded["configuration"]["llm"]["model"] == LLM_MODEL
    assert decoded["configuration"]["embedding"]["model"] == EMBEDDING_MODEL
    assert decoded["configuration"]["embedding"]["dimensions"] == EMBEDDING_DIMENSIONS
    assert decoded["manifest"]["sha256"] == dataset.manifest_sha256
    assert decoded["summary"]["total_sample_count"] == 2
    assert decoded["summary"]["failure_count"] == 1
    assert decoded["failures"][0]["sample_id"] == "EVAL-FAIL"
    assert decoded["dataset"]["complete"] is False
