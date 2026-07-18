"""Emergency detection tests."""

from __future__ import annotations

import pytest
from app.ai.emergency.detector import EmergencyDetector


def test_detects_vietnamese_emergency_symptoms() -> None:
    assessment = EmergencyDetector().assess("Tôi đau ngực dữ dội và khó thở")

    assert assessment.is_emergency is True
    assert "severe_chest_pain" in assessment.matched_terms
    assert "shortness_of_breath" in assessment.matched_terms


def test_detects_real_vietnamese_d_character() -> None:
    assessment = EmergencyDetector().assess("Tôi đau ngực dữ dội")

    assert assessment.is_emergency is True
    assert "severe_chest_pain" in assessment.matched_terms


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


def test_service_price_with_emergency_word_is_not_flagged() -> None:
    assessment = EmergencyDetector().assess(
        "Gia tien sieu am cap cuu tai giuong benh la bao nhieu?"
    )

    assert assessment.is_emergency is False


def test_admin_lookup_does_not_hide_real_symptoms() -> None:
    assessment = EmergencyDetector().assess(
        "Toi kho tho, can hoi dich vu cap cuu tai giuong"
    )

    assert assessment.is_emergency is True
    assert "shortness_of_breath" in assessment.matched_terms


@pytest.mark.parametrize(
    "message",
    [
        (
            "Cho toi hoi gia tien sieu am cap cuu tai giuong benh la bao nhieu, "
            "co ap dung chung cho cac co so khong va co can dat lich truoc khong?"
        ),
        (
            "Trong bang gia ky thuat, muc phi tao nhip tim cap cuu voi dien cuc "
            "trong buong tim tai giuong la bao nhieu?"
        ),
        (
            "Toi dang so sanh chi phi soi day mat cap cuu tai giuong voi soi day "
            "mat cap cuu thong thuong, vui long tra dung bang gia."
        ),
        (
            "Neu dich vu co ten 'cap cuu bong mat ban dau' thi HERA co gia va ma "
            "dich vu nao trong du lieu khong?"
        ),
        (
            "Tuan sau bac si nao truc ca kham dich vu ky thuat cap cuu tai co so 2, "
            "toi chi hoi lich va khong co trieu chung."
        ),
        (
            "Can xem ma tuong duong BHYT cua phau thuat cap cuu long nguc co dung "
            "may tim phoi nhan tao, khong phai toi dang bi cap cuu."
        ),
    ],
)
def test_long_administrative_emergency_wording_is_not_flagged(message: str) -> None:
    assessment = EmergencyDetector().assess(message)

    assert assessment.is_emergency is False


@pytest.mark.parametrize(
    "message",
    [
        (
            "Toi muon hoi gia sieu am cap cuu tai giuong, nhung hien tai toi dau "
            "nguc du doi va kho tho lien tuc."
        ),
        (
            "Dang xem dich vu tao nhip tim cap cuu tai giuong, nguoi nha toi vua "
            "ngat va moi tim tai."
        ),
        (
            "Can biet lich bac si tuan sau, nhung bay gio benh nhan hoi hop trong "
            "nguc kem kho tho va choang."
        ),
        (
            "Hoi ve BHYT sau, hien tai ba toi nghi dot quy, meo mieng va noi kho."
        ),
    ],
)
def test_long_lookup_message_with_real_symptoms_is_flagged(message: str) -> None:
    assessment = EmergencyDetector().assess(message)

    assert assessment.is_emergency is True
    assert assessment.matched_terms


def test_negated_symptom_is_not_flagged() -> None:
    assessment = EmergencyDetector().assess(
        "Tôi không bị khó thở, chỉ muốn hỏi lịch bác sĩ."
    )

    assert assessment.is_emergency is False
