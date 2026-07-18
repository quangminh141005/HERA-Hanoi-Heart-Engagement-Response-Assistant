from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.core.config import Settings
from app.services.structured import StructuredDataService
from app.structured.cache import NoopStructuredQueryCache
from app.structured.postgres_repository import StructuredRepositoryStats


class GroupOnlyRepository:
    def exists(self) -> bool:
        return True

    def stats(self) -> StructuredRepositoryStats:
        return StructuredRepositoryStats(
            service_prices=2_946,
            bhyt_policies=2,
            schedule_documents=18,
            schedule_entries=1_382,
        )

    def search_service_price_groups(
        self,
        *,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        assert query == "ngày giường bệnh nội khoa"
        del limit
        return [
            {
                "service_record_id": "PRICE-2025-000005",
                "display_name": "Ngày giường bệnh Nội khoa:",
                "section": "KHÁM BỆNH VÀ NGÀY GIƯỜNG ĐIỀU TRỊ",
                "source_id": "SRC-PRICE-2025",
                "raw_json": json.dumps(
                    {
                        "raw_rag_payload": {
                            "metadata": {"item_type": "group"},
                            "answer_policy": {
                                "group_items_have_no_general_price": True
                            },
                            "canonical_answer_vi": (
                                "STT 5 - Ngày giường bệnh Nội khoa: là mục nhóm, "
                                "không có giá chung trong bảng nguồn. Các giá nằm "
                                "ở mục con: STT 5,1: Cơ sở 1: 305.500; "
                                "Cơ sở 2: 305.500."
                            ),
                        }
                    },
                    ensure_ascii=False,
                ),
                "exact_match": True,
                "name_similarity": 1.0,
                "title": "Giá dịch vụ kỹ thuật áp dụng tại Bệnh viện Tim Hà Nội",
                "url": "https://example.test/prices",
            }
        ]

    def search_service_prices(self, **kwargs) -> list[dict[str, Any]]:
        raise AssertionError(f"group match should not search price rows: {kwargs}")

    def find_bhyt_policy(self, **kwargs):
        raise AssertionError(kwargs)

    def find_schedule_entries(self, **kwargs) -> list[dict[str, Any]]:
        raise AssertionError(kwargs)

    def reference_date(self) -> date:
        return date(2026, 7, 17)

    def schedule_date_range(self) -> tuple[date, date]:
        return date(2026, 7, 17), date(2026, 7, 24)

    def get_active_template(self, template_key: str) -> str | None:
        del template_key
        return None

    def get_support_channels(self) -> list[dict[str, Any]]:
        return []

    def search_facts(self, **kwargs) -> list[dict[str, Any]]:
        raise AssertionError(kwargs)

    def get_embedded_knowledge_chunks(self) -> list[dict[str, Any]]:
        return []

    def search_embedded_knowledge_chunks(self, **kwargs) -> list[dict[str, Any]]:
        raise AssertionError(kwargs)

    def get_sources_by_ids(self, source_ids: list[str]) -> dict[str, dict[str, Any]]:
        del source_ids
        return {}

    def get_bundle_meta(self, key: str) -> str | None:
        del key
        return None

    def readiness_snapshot(self, **kwargs):
        raise AssertionError(kwargs)


def test_service_price_group_answer_uses_rag_canonical_payload() -> None:
    service = StructuredDataService(
        Settings(API_KEY="offline-test-key", RATE_LIMIT_ENABLED=False, _env_file=None),
        repository=GroupOnlyRepository(),
        cache=NoopStructuredQueryCache(),
    )

    result = service.chat_service_price("Giá Ngày giường bệnh Nội khoa là bao nhiêu?")

    assert result.grounded is True
    assert "là mục nhóm, không có giá chung" in result.response
    assert "STT 5,1" in result.response
    assert result.structured_record_ids == ("PRICE-2025-000005",)
    assert result.metadata["structured_group_answer"]["service_record_id"] == (
        "PRICE-2025-000005"
    )
