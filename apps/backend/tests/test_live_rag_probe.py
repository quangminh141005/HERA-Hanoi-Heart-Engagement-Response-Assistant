from __future__ import annotations

import pytest

from scripts.verify_live_rag import (
    LiveRagProbeError,
    _metric_value,
    _provider_deltas,
    _validate_response,
)


def test_metric_parser_and_provider_deltas() -> None:
    before = (
        'hera_ai_tokens_total{kind="input",provider="fpt_llm"} 10\n'
        'hera_ai_tokens_total{kind="output",provider="fpt_llm"} 4\n'
        'hera_ai_tokens_total{kind="input",provider="fpt_embedding"} 2\n'
    )
    after = (
        'hera_ai_tokens_total{kind="input",provider="fpt_llm"} 110\n'
        'hera_ai_tokens_total{kind="output",provider="fpt_llm"} 34\n'
        'hera_ai_tokens_total{kind="input",provider="fpt_embedding"} 12\n'
    )

    assert _metric_value(
        after,
        "hera_ai_tokens_total",
        provider="fpt_llm",
        kind="input",
    ) == 110
    assert _provider_deltas(before, after) == {
        "llm_input_tokens_delta": 100,
        "llm_output_tokens_delta": 30,
        "embedding_input_tokens_delta": 10,
    }


def test_response_gate_requires_model_validated_grounding_and_utf8() -> None:
    payload = {
        "answer_vi": "Bạn nên đến sớm ít nhất 15 phút.",
        "grounded": True,
        "citations": [{"source_id": "SRC-1"}],
        "metadata": {
            "decision_source": "model",
            "generation_mode": "model_validated",
        },
    }

    _validate_response(
        payload,
        decoded='{"answer_vi":"Bạn nên đến sớm ít nhất 15 phút."}',
        content_type="application/json; charset=utf-8",
    )


def test_response_gate_rejects_deterministic_fallback() -> None:
    payload = {
        "answer_vi": "Bạn nên đến sớm ít nhất 15 phút.",
        "grounded": True,
        "citations": [{"source_id": "SRC-1"}],
        "metadata": {
            "decision_source": "deterministic_fallback",
            "generation_mode": "deterministic",
        },
    }

    with pytest.raises(LiveRagProbeError, match="routing did not use the model"):
        _validate_response(
            payload,
            decoded='{"answer_vi":"Bạn nên đến sớm ít nhất 15 phút."}',
            content_type="application/json; charset=utf-8",
        )
