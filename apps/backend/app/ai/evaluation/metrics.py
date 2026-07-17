"""Evaluation metric names for HERA."""

CRITICAL_METRICS = (
    "faithfulness",
    "citation_accuracy",
    "emergency_recall",
    "emergency_false_negative_rate",
    "privacy_leak_rate",
)

MVP_METRICS = (
    *CRITICAL_METRICS,
    "answer_correctness",
    "context_precision",
    "context_recall",
    "refusal_accuracy",
    "handoff_rate",
    "latency_p95",
)

