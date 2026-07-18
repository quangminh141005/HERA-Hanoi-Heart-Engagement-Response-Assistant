"""Structured lookup services backed by PostgreSQL."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.config import Settings
from app.schemas.structured import (
    BhytLookupResponse,
    BhytTierRecord,
    ScheduleEntryRecord,
    ScheduleLookupResponse,
    ServicePriceLookupResponse,
    ServicePriceRecord,
    StructuredCitation,
)
from app.structured.cache import (
    StructuredQueryCache,
    build_structured_query_cache,
)
from app.structured.postgres_repository import (
    PostgresStructuredRepository,
    StructuredReadRepository,
    StructuredRepositoryStats,
)


@dataclass(frozen=True)
class StructuredChatResult:
    intent: str
    response: str
    citations: list[StructuredCitation]
    metadata: dict
    requires_handoff: bool = False
    response_type: str = "structured_action"
    grounded: bool = True
    data_classification: str = "official_current"
    warnings: tuple[str, ...] = ()
    structured_record_ids: tuple[str, ...] = ()
    actions: tuple[dict, ...] = ()


class StructuredDataService:
    """Read approved structured answers from PostgreSQL."""

    def __init__(
        self,
        settings: Settings,
        repository: StructuredReadRepository | None = None,
        cache: StructuredQueryCache | None = None,
    ):
        self.settings = settings
        self.cache = cache or build_structured_query_cache(settings)
        approval_statuses = (
            ("approved_for_production",)
            if settings.ENVIRONMENT.lower() == "production"
            else ("approved_for_hackathon", "approved_for_production")
        )
        self.repository = repository or PostgresStructuredRepository(
            approval_statuses=approval_statuses,
        )

    def ready_stats(self) -> StructuredRepositoryStats | None:
        if not self.repository.exists():
            return None
        return self.repository.stats()

    def reference_date(self) -> date:
        if self.settings.REFERENCE_DATE_MODE == "fixed":
            if self.settings.REFERENCE_DATE is None:
                raise LookupError("REFERENCE_DATE is required when mode=fixed")
            return self.settings.REFERENCE_DATE
        if self.settings.REFERENCE_DATE_MODE == "dataset_start":
            return self.repository.reference_date()
        return date.today()

    def lookup_service_prices(
        self,
        *,
        query: str,
        facility_code: str | None,
        as_of_date: date | None,
    ) -> ServicePriceLookupResponse:
        normalized_query = query.strip()
        target_date = as_of_date.isoformat() if as_of_date else None
        rows = self._cached_rows(
            'service-prices',
            {
                'query': normalized_query,
                'facility_code': facility_code,
            },
            lambda: self.repository.search_service_prices(
                query=normalized_query,
                facility_code=facility_code,
            ),
        )
        source_ids = sorted({row["source_id"] for row in rows})
        source_map = self._source_map(source_ids)
        citations = [
            StructuredCitation(
                source_id=source["source_id"],
                title=source["title"],
                url=source["url"],
            )
            for source in source_map.values()
        ]
        records = [
            ServicePriceRecord(
                service_record_id=row["service_record_id"],
                price_id=row["price_id"],
                display_name=row["display_name"],
                facility_code=row["facility_code"],
                amount_vnd=row["amount_vnd"],
                amount_raw=row["amount_raw"],
                section=row["section"],
                note=row["ghi_chu"],
                exact_match=bool(row["exact_match"]),
                name_similarity=float(row["name_similarity"]),
            )
            for row in rows
        ]
        return ServicePriceLookupResponse(
            query=normalized_query,
            facility_code=facility_code,
            as_of_date=target_date,
            classification="official_current",
            warning=(
                "Kết quả được tra trực tiếp từ bộ dữ liệu giá mới nhất mà dự án "
                "đang sử dụng; mức thanh toán thực tế vẫn cần Bệnh viện xác nhận."
            ),
            records=records,
            citations=citations,
            requires_clarification=_price_records_require_clarification(
                records,
                facility_code=facility_code,
            ),
        )

    def lookup_bhyt(self, *, as_of_date: date) -> BhytLookupResponse:
        identity = {
            'as_of': as_of_date,
            'latest_available': self.settings.TREAT_PROVIDED_DATA_AS_LATEST,
        }
        cached = self.cache.get('bhyt-policy', identity)
        if (
            isinstance(cached, dict)
            and (cached.get('policy') is None or isinstance(cached.get('policy'), dict))
            and isinstance(cached.get('tiers'), list)
        ):
            policy = cached.get('policy')
            tiers = cached['tiers']
        else:
            policy, tiers = self.repository.find_bhyt_policy(
                as_of=as_of_date,
                latest_available=self.settings.TREAT_PROVIDED_DATA_AS_LATEST,
            )
            self.cache.set(
                'bhyt-policy',
                identity,
                {'policy': policy, 'tiers': tiers},
            )
        if policy is None:
            raise LookupError("Không tìm thấy policy BHYT phù hợp với ngày yêu cầu.")
        source_map = self.repository.get_sources_by_ids([policy["source_id"]])
        source = source_map.get(policy["source_id"])
        citations = []
        if source is not None:
            citations.append(
                StructuredCitation(
                    source_id=source["source_id"],
                    title=source["title"],
                    url=source["url"],
                )
            )
        return BhytLookupResponse(
            as_of_date=as_of_date.isoformat(),
            policy_id=policy["policy_id"],
            classification=(
                "official_current"
                if policy["current_lookup_eligible"]
                else "secondary_historical"
            ),
            warning=(
                "Đây là mức đóng BHYT hộ gia đình, không phải quyền lợi cá nhân hoặc "
                "mức quỹ chi trả cho dịch vụ."
            ),
            tiers=[
                BhytTierRecord(
                    tier_id=row["tier_key"],
                    tier_order=row["tier_order"],
                    member_label=row["member_label"],
                    rate_text=row["rate_text"],
                    monthly_amount_vnd=row["monthly_amount_vnd"],
                    annual_amount_vnd=row["annual_amount_vnd"],
                )
                for row in tiers
            ],
            citations=citations,
        )

    def lookup_schedules(
        self,
        *,
        week_start: date,
        service_date: date | None,
        facility_code: str | None,
        doctor_query: str | None,
        room_query: str | None,
    ) -> ScheduleLookupResponse:
        rows = self._cached_rows(
            'schedules',
            {
                'week_start': week_start,
                'service_date': service_date,
                'facility_code': facility_code,
                'doctor_query': doctor_query,
                'room_query': room_query,
            },
            lambda: self.repository.find_schedule_entries(
                week_start=week_start,
                service_date=service_date,
                facility_code=facility_code,
                doctor_query=doctor_query,
                room_query=room_query,
            ),
        )
        source_ids = sorted({row["source_id"] for row in rows})
        source_map = self._source_map(source_ids)
        citations = [
            StructuredCitation(
                source_id=source["source_id"],
                title=source["title"],
                url=source["url"],
            )
            for source in source_map.values()
        ]
        manifest_json = self.repository.get_bundle_meta("manifest_json")
        coverage = {}
        if manifest_json:
            manifest = json.loads(manifest_json)
            coverage = next(
                (
                    item
                    for item in manifest.get("schedule_week_summaries", [])
                    if item.get("week_start") == week_start.isoformat()
                ),
                {},
            )
        return ScheduleLookupResponse(
            week_start=week_start.isoformat(),
            service_date=service_date.isoformat() if service_date else None,
            facility_code=facility_code,
            doctor_query=doctor_query,
            room_query=room_query,
            classification="partial_official_snapshot",
            warning=(
                "Lịch làm việc không đồng nghĩa còn suất khám. Hệ thống chỉ trả roster "
                "đã công bố và chưa tự xác nhận khả năng đặt lịch."
            ),
            records=[
                ScheduleEntryRecord(
                    schedule_entry_id=row["schedule_entry_id"],
                    service_date=row["service_date"],
                    facility_code=row["facility_code"],
                    room_label=row["room_label"],
                    unit_label=row["unit_label"],
                    provider_text=row["assignee_text_raw"],
                    published_hours_raw=row["published_hours_raw"],
                    duty_status=row["duty_status"],
                    assignee_type=row["assignee_type"],
                    approval_status=row["approval_status"],
                )
                for row in rows
            ],
            citations=citations,
            coverage=coverage,
        )

    def chat_service_price(self, message: str) -> StructuredChatResult:
        facility_code = _extract_facility_code(message)
        rows = self.lookup_service_prices(
            query=_extract_search_phrase(message),
            facility_code=facility_code,
            as_of_date=None,
        )
        if not rows.records:
            return StructuredChatResult(
                intent="service_price_current",
                response=(
                    "Hiện mình chưa tìm thấy dòng giá phù hợp trong dữ liệu đã có. "
                    "Bạn hãy nêu rõ tên dịch vụ và cơ sở cần tra."
                ),
                citations=rows.citations,
                metadata={"structured_action": rows.model_dump()},
                requires_handoff=False,
                grounded=False,
                data_classification="official_current",
                warnings=(rows.warning,),
            )
        if rows.requires_clarification:
            relevant = [record for record in rows.records if record.exact_match]
            relevant = relevant or rows.records
            return StructuredChatResult(
                intent="service_price_current",
                response=(
                    "HERA tìm thấy nhiều dòng giá phù hợp nhưng không thể chọn an toàn "
                    "một mức duy nhất. Vui lòng chọn đúng cơ sở hoặc đối chiếu các "
                    "dòng dịch vụ trong bảng kết quả."
                ),
                citations=rows.citations,
                metadata={"structured_action": rows.model_dump()},
                data_classification=rows.classification,
                warnings=(rows.warning,),
                structured_record_ids=tuple(
                    record_id
                    for record in relevant
                    for record_id in (record.service_record_id, record.price_id)
                ),
            )
        top = rows.records[0]
        comparison_rows = rows
        if facility_code is not None:
            comparison_rows = self.lookup_service_prices(
                query=top.display_name,
                facility_code=None,
                as_of_date=None,
            )
        same_service = [
            record
            for record in comparison_rows.records
            if record.service_record_id == top.service_record_id
        ]
        facility_codes = sorted(
            {record.facility_code for record in same_service}
        )
        amounts = {record.amount_vnd for record in same_service}
        if len(facility_codes) > 1 and len(amounts) == 1:
            facilities = ' và '.join(facility_codes)
            prefix = (
                f'Dịch vụ này đang có cùng mức giá ở {facilities}'
                if facility_code is not None
                else f'{top.display_name} tại {facilities}'
            )
            return StructuredChatResult(
                intent='service_price_current',
                response=(
                    f'Theo dữ liệu giá mới nhất của hệ thống, {prefix} là '
                    f'{_format_vnd(top.amount_vnd)} VND. '
                    f'{rows.warning}'
                ),
                citations=rows.citations,
                metadata={'structured_action': comparison_rows.model_dump()},
                data_classification=rows.classification,
                warnings=(rows.warning,),
                structured_record_ids=tuple(
                    dict.fromkeys(
                        record_id
                        for record in same_service
                        for record_id in (record.service_record_id, record.price_id)
                    )
                ),
            )
        return StructuredChatResult(
            intent="service_price_current",
            response=(
                f"Theo dữ liệu giá mới nhất của hệ thống, {top.display_name} tại "
                f"{top.facility_code} là "
                f"{_format_vnd(top.amount_vnd)} VND. {rows.warning}"
            ),
            citations=rows.citations,
            metadata={"structured_action": rows.model_dump()},
            data_classification=rows.classification,
            warnings=(rows.warning,),
            structured_record_ids=(top.service_record_id, top.price_id),
        )

    def chat_bhyt(self, message: str) -> StructuredChatResult:
        target_date = _extract_as_of_date(message) or self.reference_date()
        policy = self.lookup_bhyt(as_of_date=target_date)
        if not policy.tiers:
            raise LookupError("Không tìm thấy tier BHYT.")
        requested_tier = _extract_bhyt_tier(message)
        selected = next(
            (tier for tier in policy.tiers if tier.tier_order == requested_tier),
            None,
        )
        if selected is None:
            response = (
                f"Dữ liệu mới nhất có {len(policy.tiers)} mức đóng BHYT hộ gia đình. "
                "Bạn có thể xem đầy đủ từng thành viên trong bảng bên dưới. "
                f"{policy.warning}"
            )
            tier_ids = tuple(tier.tier_id for tier in policy.tiers)
        else:
            response = (
                f"Theo dữ liệu mới nhất, {selected.member_label} đóng "
                f"{_format_vnd(selected.annual_amount_vnd)} VND mỗi 12 tháng. "
                f"{policy.warning}"
            )
            tier_ids = (selected.tier_id,)
        return StructuredChatResult(
            intent="bhyt_household_contribution",
            response=response,
            citations=policy.citations,
            metadata={"structured_action": policy.model_dump()},
            data_classification=policy.classification,
            warnings=(policy.warning,),
            structured_record_ids=(policy.policy_id, *tier_ids),
        )

    def chat_schedule(self, message: str) -> StructuredChatResult:
        reference_date = self.reference_date()
        target_date = _resolve_schedule_date(message, reference_date)
        target_week = _monday(target_date or reference_date)
        facility_code = _extract_facility_code(message)
        schedule = self.lookup_schedules(
            week_start=target_week,
            service_date=target_date,
            facility_code=facility_code,
            doctor_query=_extract_doctor_query(message),
            room_query=_extract_room_query(message),
        )
        if not schedule.records:
            return StructuredChatResult(
                intent="schedule",
                response=(
                    "Mình chưa tìm thấy lịch phù hợp trong ngày hoặc tuần bạn hỏi. "
                    "Bạn hãy thử một ngày khác, cơ sở khác hoặc nêu tên bác sĩ."
                ),
                citations=schedule.citations,
                metadata={"structured_action": schedule.model_dump()},
                requires_handoff=False,
                grounded=False,
                data_classification=schedule.classification,
                warnings=(schedule.warning,),
            )
        first = schedule.records[0]
        return StructuredChatResult(
            intent="schedule",
            response=(
                f"Lịch tìm thấy: ngày {first.service_date}, {first.room_label}, "
                f"{first.provider_text}. {schedule.warning}"
            ),
            citations=schedule.citations,
            metadata={"structured_action": schedule.model_dump()},
            data_classification=schedule.classification,
            warnings=(schedule.warning,),
            structured_record_ids=tuple(
                record.schedule_entry_id for record in schedule.records
            ),
        )

    def _cached_rows(
        self,
        namespace: str,
        identity: dict[str, object],
        loader: Callable[[], list[dict]],
    ) -> list[dict]:
        cached = self.cache.get(namespace, identity)
        if isinstance(cached, list) and all(
            isinstance(row, dict) for row in cached
        ):
            return [dict(row) for row in cached]
        rows = loader()
        self.cache.set(namespace, identity, rows)
        return rows

    def _source_map(self, source_ids: list[str]) -> dict[str, dict]:
        unique_ids = sorted(set(source_ids))
        cached = self.cache.get('sources', {'source_ids': unique_ids})
        if isinstance(cached, dict) and all(
            isinstance(source, dict) for source in cached.values()
        ):
            return {str(key): dict(value) for key, value in cached.items()}
        sources = self.repository.get_sources_by_ids(unique_ids)
        self.cache.set('sources', {'source_ids': unique_ids}, sources)
        return sources

    def close(self) -> None:
        self.cache.close()

    def active_template(self, template_key: str) -> str | None:
        return self.repository.get_active_template(template_key)

    def support_actions(self) -> tuple[dict, ...]:
        return tuple(
            {
                "type": "call" if row["channel_type"] == "phone" else "open_url",
                "channel_id": row["channel_id"],
                "label_vi": row["label_vi"],
                "target": row["target_value"],
            }
            for row in self.repository.get_support_channels()
        )


def _price_records_require_clarification(
    records: list[ServicePriceRecord],
    *,
    facility_code: str | None,
) -> bool:
    """Detect equally named price rows that cannot safely collapse to one value."""

    if len(records) < 2:
        return False
    exact_records = [record for record in records if record.exact_match]
    candidates = exact_records or records
    grouped: dict[tuple[str, str], set[int]] = {}
    for record in candidates:
        key = (_fold_text(record.display_name), record.facility_code)
        grouped.setdefault(key, set()).add(record.amount_vnd)
    if any(len(amounts) > 1 for amounts in grouped.values()):
        return True
    if facility_code is None and exact_records:
        choices = {
            (record.facility_code, record.amount_vnd) for record in exact_records
        }
        return len(choices) > 1
    return False


def _extract_facility_code(message: str) -> str | None:
    lowered = message.lower()
    if "cs1" in lowered or "cơ sở 1" in lowered or "co so 1" in lowered:
        return "CS1"
    if "cs2" in lowered or "cơ sở 2" in lowered or "co so 2" in lowered:
        return "CS2"
    return None


def _format_vnd(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _extract_search_phrase(message: str) -> str:
    lowered = message.lower()
    canonical_pairs = (
        ("khám bệnh", "khám bệnh"),
        ("kham benh", "khám bệnh"),
        ("bảo hiểm y tế", "bảo hiểm y tế"),
        ("bao hiem y te", "bảo hiểm y tế"),
    )
    for needle, result in canonical_pairs:
        if needle in lowered:
            return result

    cleanup_terms = (
        "giá",
        "gia",
        "tra giá",
        "tra gia",
        "chi phí",
        "chi phi",
        "cơ sở 1",
        "co so 1",
        "cơ sở 2",
        "co so 2",
        "là bao nhiêu",
        "la bao nhieu",
        "còn",
        "con",
        "thì sao",
        "thi sao",
        "dịch vụ đó",
        "dich vu do",
    )
    cleaned = lowered
    for term in cleanup_terms:
        cleaned = cleaned.replace(term, " ")
    collapsed = " ".join(cleaned.split())
    return collapsed or message.strip()


def _extract_as_of_date(message: str) -> date | None:
    iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", message)
    if iso:
        return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    vi = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", message)
    if vi:
        return date(int(vi.group(3)), int(vi.group(2)), int(vi.group(1)))
    return None


def _extract_week_start(message: str) -> date | None:
    extracted = _extract_as_of_date(message)
    if extracted is None:
        return None
    return _monday(extracted)


def _monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _resolve_schedule_date(message: str, reference_date: date) -> date | None:
    explicit = _extract_as_of_date(message)
    if explicit is not None:
        return explicit
    folded = _fold_text(message)
    if "ngay kia" in folded:
        return reference_date + timedelta(days=2)
    if "ngay mai" in folded or "mai" == folded.strip():
        return reference_date + timedelta(days=1)
    if "hom nay" in folded:
        return reference_date
    if "tuan sau" in folded:
        return _monday(reference_date) + timedelta(days=7)
    if "tuan nay" in folded:
        return None
    return None


def _fold_text(value: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.lower())
    return "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


def _extract_doctor_query(message: str) -> str | None:
    patterns = (
        r"bác sĩ\s+([^,.0-9]+)",
        r"bac si\s+([^,.0-9]+)",
        r"\bbs\.?\s*([^,.0-9]+)",
    )
    rejected_prefixes = ("cơ sở", "co so", "ngày", "ngay", "tuần", "tuan")
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            folded = candidate.lower()
            if any(folded.startswith(prefix) for prefix in rejected_prefixes):
                return None
            if len(candidate.split()) < 2:
                return None
            return candidate
    return None


def _extract_room_query(message: str) -> str | None:
    lowered = message.lower()
    if "phòng khám số" in lowered or "phong kham so" in lowered:
        return message.strip()
    if "p4" in lowered:
        return message.strip()
    return None


def _extract_bhyt_tier(message: str) -> int | None:
    folded = _fold_text(message)
    match = re.search(r"nguoi thu\s*([1-5])", folded)
    if match:
        return int(match.group(1))
    words = {"nhat": 1, "hai": 2, "ba": 3, "tu": 4, "nam": 5}
    for word, tier in words.items():
        if f"nguoi thu {word}" in folded:
            return tier
    return None
