"""Structured lookup services backed by PostgreSQL."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

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
            doctor_match_min_score=settings.SCHEDULE_DOCTOR_MATCH_MIN_SCORE,
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
            'open_schedules',
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
        rows = _deduplicate_schedule_rows(rows)
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

    def chat_service_price(
        self,
        message: str,
        query_override: str | None = None,
        facility_code_override: str | None = None,
    ) -> StructuredChatResult:
        facility_code = facility_code_override or _extract_facility_code(message)
        search_query = (
            _preserve_bracketed_service_qualifiers(query_override, message)
            if query_override
            else _extract_search_phrase(message)
        )
        group_answer = self._service_price_group_answer(
            query=(
                _extract_service_group_phrase(query_override or message)
                if not query_override
                else query_override
            )
        )
        if group_answer is not None:
            return group_answer
        rows = self.lookup_service_prices(
            query=search_query,
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
        if rows.requires_clarification and not _top_price_record_is_safe(rows.records):
            relevant = [record for record in rows.records if record.exact_match]
            relevant = relevant or rows.records
            summary = _summarize_price_choices(relevant)
            choices_text = (
                f" Các dòng gần nhất trong dữ liệu gồm: {summary}."
                if summary
                else ""
            )
            return StructuredChatResult(
                intent="service_price_current",
                response=(
                    "HERA tìm thấy nhiều dòng giá phù hợp nhưng không thể chọn an toàn "
                    "một mức duy nhất."
                    f"{choices_text} Vui lòng chọn đúng cơ sở hoặc đối chiếu các "
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
            prefix = f'{top.display_name} tại {facilities}'
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

    def chat_bhyt(
        self,
        message: str,
        tier_override: str | None = None,
    ) -> StructuredChatResult:
        target_date = _extract_as_of_date(message) or self.reference_date()
        policy = self.lookup_bhyt(as_of_date=target_date)
        if not policy.tiers:
            raise LookupError("Không tìm thấy tier BHYT.")
        requested_tier = (
            int(tier_override)
            if tier_override in {"1", "2", "3", "4", "5"}
            else _extract_bhyt_tier(message)
        )
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

    def chat_schedule(
        self,
        message: str,
        date_override: str | None = None,
        facility_code_override: str | None = None,
        doctor_query_override: str | None = None,
        room_query_override: str | None = None,
    ) -> StructuredChatResult:
        reference_date = self.reference_date()
        # The user's explicit date is authoritative. A routing model may infer a
        # wrong year for a short dd/mm date, so only use its normalized slot when
        # deterministic parsing found no date in the original message.
        target_date = _resolve_schedule_date(message, reference_date) or (
            _extract_as_of_date(date_override or "")
        )
        target_week = _monday(target_date or reference_date)
        facility_code = facility_code_override or _extract_facility_code(message)
        normalized_room_override = (
            _extract_room_query(room_query_override) or room_query_override
            if room_query_override
            else None
        )
        schedule = self.lookup_schedules(
            week_start=target_week,
            service_date=target_date,
            facility_code=facility_code,
            doctor_query=doctor_query_override or _extract_doctor_query(message),
            room_query=normalized_room_override or _extract_room_query(message),
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

    def _service_price_group_answer(
        self,
        *,
        query: str,
    ) -> StructuredChatResult | None:
        if not query.strip():
            return None
        rows = self.repository.search_service_price_groups(query=query, limit=3)
        if not rows:
            return None
        top = rows[0]
        exact_match = bool(top.get("exact_match"))
        similarity = float(top.get("name_similarity") or 0)
        if not exact_match and similarity < 0.92:
            return None
        raw_json = top.get("raw_json")
        payload = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        if not isinstance(payload, dict):
            return None
        rag_payload = payload.get("raw_rag_payload")
        if not isinstance(rag_payload, dict):
            return None
        canonical_answer = rag_payload.get("canonical_answer_vi")
        if not isinstance(canonical_answer, str) or not canonical_answer.strip():
            return None
        source_id = str(top.get("source_id") or "")
        title = str(top.get("title") or "")
        url = str(top.get("url") or "")
        citations = []
        if source_id and title and url:
            citations.append(
                StructuredCitation(source_id=source_id, title=title, url=url)
            )
        return StructuredChatResult(
            intent="service_price_current",
            response=canonical_answer,
            citations=citations,
            metadata={"structured_group_answer": top},
            data_classification="official_current",
            structured_record_ids=(str(top["service_record_id"]),),
        )

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
        return len(choices) > 1 and len({amount for _, amount in choices}) > 1
    if not exact_records:
        service_choices = {
            (_fold_text(record.display_name), record.amount_vnd)
            for record in candidates
        }
        return len({name for name, _ in service_choices}) > 1 and len(
            {amount for _, amount in service_choices}
        ) > 1
    return False


def _top_price_record_is_safe(records: list[ServicePriceRecord]) -> bool:
    """Allow a clear top service even when SQL returned lower-ranked neighbors."""

    if not records:
        return False
    top = records[0]
    if top.name_similarity < 0.65 and not top.exact_match:
        return False
    same_service = [
        record for record in records if record.service_record_id == top.service_record_id
    ]
    if not same_service:
        return False
    top_amounts = {record.amount_vnd for record in same_service}
    if len(top_amounts) != 1:
        return False
    competing = [
        record
        for record in records
        if record.service_record_id != top.service_record_id
        and record.name_similarity >= top.name_similarity - 0.05
    ]
    return not competing


def _summarize_price_choices(records: list[ServicePriceRecord], *, limit: int = 4) -> str:
    """Create a concise grounded summary of candidate price rows."""

    choices: dict[tuple[str, int], set[str]] = {}
    for record in records:
        key = (record.display_name, record.amount_vnd)
        choices.setdefault(key, set()).add(record.facility_code)
    parts: list[str] = []
    for (display_name, amount_vnd), facilities in list(choices.items())[:limit]:
        facility_text = "/".join(sorted(facilities))
        parts.append(f"{display_name} ({facility_text}: {_format_vnd(amount_vnd)} VND)")
    return "; ".join(parts)


def _extract_facility_code(message: str) -> str | None:
    lowered = message.lower()
    if "cs1" in lowered or "cơ sở 1" in lowered or "co so 1" in lowered:
        return "CS1"
    if "cs2" in lowered or "cơ sở 2" in lowered or "co so 2" in lowered:
        return "CS2"
    return None


def _preserve_bracketed_service_qualifiers(
    model_query: str,
    original_message: str,
) -> str:
    """Restore exact bracket qualifiers that a model extraction omitted."""

    query = " ".join(model_query.split())
    folded_query = _fold_text(query)
    for qualifier in re.findall(r"\[([^\[\]]{1,160})\]", original_message):
        cleaned = " ".join(qualifier.split())
        if re.fullmatch(r"[A-Z0-9_]+_REDACTED", cleaned):
            continue
        if cleaned and _fold_text(cleaned) not in folded_query:
            query = f"{query} [{cleaned}]"
            folded_query = _fold_text(query)
    return query


def _format_vnd(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _extract_search_phrase(message: str) -> str:
    folded = _fold_text(message)
    price_focused = _focus_price_query_region(folded)
    if price_focused:
        folded = price_focused
    canonical_pairs = (
        ("kham benh", "kham benh"),
        ("bao hiem y te", "bao hiem y te"),
    )
    for needle, result in canonical_pairs:
        if needle in folded:
            return result

    cleanup_terms = (
        "ban co",
        "ban cho minh",
        "cho minh",
        "minh can biet",
        "neu lam",
        "theo du lieu",
        "bang gia ghi muc nao",
        "bang gia",
        "muc nao",
        "khoang",
        "gia tien",
        "tra gia",
        "chi phi",
        "bao nhieu tien",
        "bao nhieu",
        "co so 1",
        "co so 2",
        "cs1",
        "cs2",
        "tai cs1",
        "tai cs2",
        "o cs1",
        "o cs2",
        "la bao nhieu",
        "thi sao",
        "thi",
        "dich vu do",
        "dich vu",
        "gia",
        "tien",
        "cho",
        "khong",
        "nhe",
    )
    cleaned = folded
    for term in cleanup_terms:
        cleaned = re.sub(rf"\b{re.escape(term)}\b", " ", cleaned)
    cleaned = re.sub(r"[^0-9a-zA-Z]+", " ", cleaned)
    collapsed = " ".join(cleaned.split())
    return collapsed or message.strip()


def _extract_service_group_phrase(message: str) -> str:
    cleaned = " ".join(message.strip().strip("?.!。").split())
    cleaned = re.sub(r"(?i)^\s*giá\s+", "", cleaned)
    cleanup_patterns = (
        r"\s+là\s+bao\s+nhiêu\s*$",
        r"\s+bao\s+nhiêu\s*$",
        r"\s+giá\s+bao\s+nhiêu\s*$",
        r"\s+là\s+gì\s*$",
    )
    for pattern in cleanup_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().lower()


def _focus_price_query_region(folded_message: str) -> str | None:
    """Extract the probable service-name span from a price question."""

    markers = (
        "muon biet gia",
        "can biet gia",
        "gia tien",
        "chi phi",
        "muc gia",
        "don gia",
        "gia",
    )
    candidates: list[tuple[int, str]] = []
    for marker in markers:
        index = folded_message.find(marker)
        if index < 0:
            continue
        prefix = folded_message[:index].strip()
        if len(prefix) > 20 and marker not in {"muon biet gia", "can biet gia"}:
            continue
        candidates.append((index + len(marker), marker))
    if not candidates:
        return None
    region = folded_message[min(start for start, _ in candidates) :]
    tail_markers = (
        " nhung ",
        " dong thoi ",
        " truoc het ",
        " sau do ",
        " va me ",
        " va toi ",
    )
    cut_at = len(region)
    for marker in tail_markers:
        index = region.find(marker)
        if index >= 0:
            cut_at = min(cut_at, index)
    region = region[:cut_at].strip()
    return region or None

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


def _deduplicate_schedule_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one deterministic record for each published open consultation slot."""

    unique_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        identity = tuple(
            str(row.get(field) or "").strip().casefold()
            for field in (
                "service_date",
                "facility_code",
                "room_label",
                "unit_label",
                "assignee_text_raw",
                "published_hours_raw",
            )
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique_rows.append(row)
    return unique_rows


def _resolve_schedule_date(message: str, reference_date: date) -> date | None:
    explicit = _extract_as_of_date(message)
    if explicit is not None:
        return explicit
    partial = _extract_day_month_date(message, default_year=reference_date.year)
    if partial is not None:
        return partial
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


def _extract_day_month_date(message: str, *, default_year: int) -> date | None:
    """Parse explicit Vietnamese day/month dates that omit the year.

    Hospital schedule questions commonly use short forms such as ``09/06`` or
    ``ngày 15-06``. Those are explicit dates in the dataset year, so they must
    not fall back to the reference week. Full yyyy-mm-dd and dd/mm/yyyy parsing
    stays in ``_extract_as_of_date``.
    """

    if re.search(r"\b(?:20\d{2})[-/]\d{1,2}[-/]\d{1,2}\b", message):
        return None
    if re.search(r"\b\d{1,2}[-/]\d{1,2}[-/](?:20\d{2})\b", message):
        return None
    folded = _fold_text(message)
    match = re.search(r"(?:\bngay\s*)?\b(\d{1,2})[-/](\d{1,2})\b", folded)
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    try:
        return date(default_year, month, day)
    except ValueError:
        return None


def _fold_text(value: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.lower())
    return "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


def _extract_doctor_query(message: str) -> str | None:
    patterns = (
        r"bác sĩ\s+(?:bsnt\.?|bs\.?|ths\.?\s*bs\.?|ts\.?\s*bs\.?)?\s*([^,.]+)",
        r"bac si\s+(?:bsnt\.?|bs\.?|ths\.?\s*bs\.?|ts\.?\s*bs\.?)?\s*([^,.]+)",
        r"bác sĩ\s+([^,.]+)",
        r"bac si\s+([^,.]+)",
        r"\bbs(?:nt|cki|ckii)?\.?\s*([^,.]+)",
        r"\bths\.?\s*bs\.?\s*([^,.]+)",
    )
    rejected_prefixes = ("cơ sở", "co so", "ngày", "ngay", "tuần", "tuan")
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            candidate = _trim_doctor_candidate(match.group(1).strip())
            folded = _fold_text(candidate)
            if any(folded.startswith(prefix) for prefix in rejected_prefixes):
                return None
            if len(candidate.split()) < 2:
                return None
            return candidate
    return None


def _trim_doctor_candidate(value: str) -> str:
    folded = _fold_text(value)
    cut_markers = (
        " co lich",
        " kham tai",
        " co kham",
        " ngay ",
        " o cs",
        " o co so",
        " tai cs",
        " tai co so",
    )
    cut_at = len(value)
    for marker in cut_markers:
        index = folded.find(marker)
        if index >= 0:
            cut_at = min(cut_at, index)
    candidate = value[:cut_at].strip(" -:;()")
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate


def _extract_room_query(message: str) -> str | None:
    room_code = re.search(r"\bP\d{3}(?:\.[A-Za-z0-9]+)?\b", message, re.IGNORECASE)
    if room_code:
        return room_code.group(0)
    folded = _fold_text(message)
    room_label = re.search(
        r"\bphong\s+(.+?)(?=\s+(?:tai|o|ngay|co)\b|[,.;?]|$)",
        folded,
    )
    if room_label:
        candidate = " ".join(room_label.group(1).split())
        return candidate[:80] or None
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
