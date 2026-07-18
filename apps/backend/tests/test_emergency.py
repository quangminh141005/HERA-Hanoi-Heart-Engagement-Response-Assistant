"""Emergency detection tests."""

from __future__ import annotations

from app.ai.emergency.detector import EmergencyDetector


def test_detects_vietnamese_emergency_symptoms() -> None:
    assessment = EmergencyDetector().assess("Tôi đau ngực dữ dội và khó thở")

    assert assessment.is_emergency is True
    assert "severe_chest_pain" in assessment.matched_terms
    assert "shortness_of_breath" in assessment.matched_terms


def test_detects_explicit_urgent_language() -> None:
    assessment = EmergencyDetector().assess("Tình trạng này có nguy cấp không?")

    assert assessment.is_emergency is True
    assert "explicit_emergency_request" in assessment.matched_terms


def test_detects_suspected_cardiovascular_emergency_terms() -> None:
    detector = EmergencyDetector()

    assert detector.assess("Tôi nghi bị nhồi máu cơ tim").is_emergency is True
    assert detector.assess("Người nhà bị méo miệng và nói khó").is_emergency is True


def test_non_emergency_admin_question_is_not_flagged() -> None:
    assessment = EmergencyDetector().assess("Cho tôi hỏi quy trình khám BHYT")

    assert assessment.is_emergency is False


def test_negated_symptom_is_not_flagged() -> None:
    assessment = EmergencyDetector().assess(
        "Tôi không bị khó thở, chỉ muốn hỏi lịch bác sĩ."
    )

    assert assessment.is_emergency is False
