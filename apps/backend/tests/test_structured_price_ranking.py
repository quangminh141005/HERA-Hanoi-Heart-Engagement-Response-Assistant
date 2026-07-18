"""Regression tests for exact service-price lookup ranking."""

from __future__ import annotations

from app.schemas.structured import ServicePriceRecord
from app.services.structured import _price_records_require_clarification
from app.structured.postgres_repository import _rerank_service_price_rows


def test_internal_bed_day_parent_query_requires_clarification() -> None:
    records = [
        ServicePriceRecord(
            service_record_id="PRICE-2025-000006",
            price_id="PRICE-2025-000006-CS1",
            display_name=(
                "Ngày giường bệnh Nội khoa: Loại 1: Các khoa Truyền nhiễm, "
                "Hô hấp, Huyết học, Tim mạch"
            ),
            facility_code="CS1",
            amount_vnd=305_500,
            exact_match=False,
            name_similarity=0.72,
        ),
        ServicePriceRecord(
            service_record_id="PRICE-2025-000007",
            price_id="PRICE-2025-000007-CS1",
            display_name=(
                "Ngày giường bệnh Nội khoa: Loại 2: Các Khoa Cơ-Xương-Khớp, "
                "Da liễu, Tai-Mũi-Họng"
            ),
            facility_code="CS1",
            amount_vnd=273_800,
            exact_match=False,
            name_similarity=0.7,
        ),
    ]

    assert _price_records_require_clarification(records, facility_code="CS1") is True


def test_same_service_same_amount_across_facilities_does_not_need_clarification() -> None:
    records = [
        ServicePriceRecord(
            service_record_id="PRICE-2025-000004",
            price_id="PRICE-2025-000004-CS1",
            display_name="Ngày giường bệnh Hồi sức cấp cứu",
            facility_code="CS1",
            amount_vnd=558_600,
            exact_match=True,
            name_similarity=1.0,
        ),
        ServicePriceRecord(
            service_record_id="PRICE-2025-000004",
            price_id="PRICE-2025-000004-CS2",
            display_name="Ngày giường bệnh Hồi sức cấp cứu",
            facility_code="CS2",
            amount_vnd=558_600,
            exact_match=True,
            name_similarity=1.0,
        ),
    ]

    assert _price_records_require_clarification(records, facility_code=None) is False


def test_price_rerank_preserves_internal_medicine_type_discriminator() -> None:
    rows = [
        _price_row(
            "PRICE-2025-000012",
            "Ngày giường bệnh Ngoại khoa: Loại 1: Sau các phẫu thuật loại đặc biệt",
            342_100,
            0.72,
        ),
        _price_row(
            "PRICE-2025-000006",
            "Ngày giường bệnh Nội khoa: Loại 1: Các khoa Truyền nhiễm, Hô hấp, Huyết học, Tim mạch",
            305_500,
            0.69,
        ),
        _price_row(
            "PRICE-2025-000007",
            "Ngày giường bệnh Nội khoa: Loại 2: Các Khoa Cơ-Xương-Khớp, Da liễu, Tai-Mũi-Họng",
            273_800,
            0.67,
        ),
    ]

    ranked = _rerank_service_price_rows(
        "ngày giường bệnh nội khoa loại 1",
        rows,
        limit=3,
    )

    assert ranked[0]["service_record_id"] == "PRICE-2025-000006"


def test_price_rerank_rejects_unrelated_fake_service() -> None:
    rows = [
        _price_row(
            "PRICE-2025-000004",
            "Ngày giường bệnh Hồi sức cấp cứu",
            558_600,
            0.22,
        ),
        _price_row(
            "PRICE-2025-000321",
            "Siêu âm cấp cứu tại giường bệnh",
            58_600,
            0.18,
        ),
    ]

    ranked = _rerank_service_price_rows(
        "ghép tim robot lượng tử VIP",
        rows,
        limit=3,
    )

    assert ranked == []


def test_price_rerank_rejects_short_query_with_uncovered_business_token() -> None:
    rows = [
        _price_row(
            "PRICE-2025-001964",
            "Đặt stent khí phế quản",
            7_740_800,
            0.5,
        ),
        _price_row(
            "PRICE-2025-000450",
            "Đặt stent động mạch thận",
            7_118_100,
            0.48,
        ),
    ]

    ranked = _rerank_service_price_rows(
        "đặt stent bằng ma thuật",
        rows,
        limit=5,
    )

    assert ranked == []


def test_price_rerank_accepts_short_query_when_terms_are_covered() -> None:
    rows = [
        _price_row(
            "PRICE-2025-001964",
            "Đặt stent khí phế quản",
            7_740_800,
            0.72,
        ),
    ]

    ranked = _rerank_service_price_rows("đặt stent", rows, limit=5)

    assert [row["service_record_id"] for row in ranked] == ["PRICE-2025-001964"]


def _price_row(
    service_record_id: str,
    display_name: str,
    amount_vnd: int,
    similarity: float,
) -> dict:
    return {
        "service_record_id": service_record_id,
        "display_name": display_name,
        "display_name_search": display_name,
        "section": "KHÁM BỆNH VÀ NGÀY GIƯỜNG ĐIỀU TRỊ",
        "ghi_chu": None,
        "historical_year": 2026,
        "source_id": "SOURCE-PRICE",
        "price_id": f"{service_record_id}-CS1",
        "facility_code": "CS1",
        "amount_vnd": amount_vnd,
        "amount_raw": str(amount_vnd),
        "exact_match": False,
        "search_contains": False,
        "name_similarity": similarity,
    }
