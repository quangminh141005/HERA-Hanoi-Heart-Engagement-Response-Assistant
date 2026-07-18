"""Application service for local prototype booking capacity."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from time import perf_counter

from app.booking import BookingRepository
from app.core.config import Settings
from app.core.errors import HeraApiError
from app.observability.prometheus import (
    BOOKING_CAPACITY_LIMIT,
    BOOKING_HOLDS_TOTAL,
    BOOKING_OCCUPIED,
)
from app.schemas.booking import (
    BookingHoldResponse,
    BookingHoldStateResponse,
    BookingSessionListResponse,
    BookingSessionRecord,
)

PROTOTYPE_WARNING = (
    "Đây chỉ là giữ chỗ tạm trong bản demo HERA; chưa phải xác nhận lịch hẹn "
    "của Bệnh viện."
)
logger = logging.getLogger(__name__)


class BookingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repository = BookingRepository(
            hold_token_secret=settings.HOLD_TOKEN_SECRET,
            hold_ttl_seconds=settings.BOOKING_HOLD_TTL_SECONDS,
            max_active_holds_per_owner=(
                settings.BOOKING_MAX_ACTIVE_HOLDS_PER_ANONYMOUS_SESSION
            ),
            require_approved_doctor=settings.BOOKING_REQUIRE_APPROVED_DOCTOR,
            require_approved_capacity_rule=(
                settings.BOOKING_REQUIRE_APPROVED_CAPACITY_RULE
            ),
            pii_hash_secret=settings.BOOKING_PII_HASH_SECRET,
        )

    def _require_local_prototype(self) -> None:
        if self.settings.BOOKING_PROVIDER != "local_prototype":
            raise HeraApiError(
                code="BOOKING_REDIRECT_ONLY",
                message_vi=(
                    "HERA đang ở chế độ chuyển tiếp đặt lịch; "
                    "vui lòng dùng kênh chính thức của Bệnh viện."
                ),
                status_code=409,
            )
        if not self.settings.BOOKING_ALLOW_PROJECT_MVP_RULE:
            raise HeraApiError(
                code="CAPACITY_RULE_NOT_APPROVED",
                message_vi="Quy tắc số lượng của bản demo chưa được bật.",
                status_code=503,
            )

    def list_sessions(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        doctor_query: str | None,
        facility_code: str | None,
        session_key: str | None,
    ) -> BookingSessionListResponse:
        self._require_local_prototype()
        reference = self.repository.reference_date()
        start = from_date or reference
        end = to_date or (start + timedelta(days=27))
        if end < start:
            raise HeraApiError(
                code="VALIDATION_FAILED",
                message_vi="Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.",
                status_code=422,
            )
        rows = self.repository.list_sessions(
            from_date=start,
            to_date=end,
            doctor_query=doctor_query,
            facility_code=facility_code,
            session_key=session_key,
        )
        for row in rows:
            _record_capacity(
                str(row["booking_session_id"]),
                capacity_limit=int(row["capacity_limit"]),
                occupied_count=int(row["occupied_count"]),
            )
        return BookingSessionListResponse(
            reference_date=reference.isoformat(),
            warning=PROTOTYPE_WARNING,
            records=[BookingSessionRecord(**row) for row in rows],
        )

    def create_hold(
        self,
        *,
        booking_session_id: str,
        idempotency_key: str,
        owner_session_id: str,
        patient_identity: dict[str, str | None],
    ) -> BookingHoldResponse:
        self._require_local_prototype()
        started_at = perf_counter()
        try:
            result = self.repository.create_hold(
                booking_session_id=booking_session_id,
                idempotency_key=idempotency_key,
                owner_session_id=owner_session_id,
                patient_identity=patient_identity,
            )
        except HeraApiError as exc:
            BOOKING_HOLDS_TOTAL.labels(
                result=_booking_metric_result(exc.code)
            ).inc()
            snapshot = self._safe_capacity_snapshot(booking_session_id)
            log_fields: dict[str, object] = {
                "event": "booking_hold_rejected",
                "intent": "appointment_booking",
                "result_code": exc.code,
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            }
            if snapshot is not None:
                log_fields.update(
                    {
                        "booking_session_id": booking_session_id,
                        **snapshot,
                    }
                )
                _record_capacity(booking_session_id, **snapshot)
            logger.warning("booking hold rejected", extra=log_fields)
            raise
        result_code = "duplicate" if result["idempotent_replay"] else "success"
        BOOKING_HOLDS_TOTAL.labels(result=result_code).inc()
        occupied_count = int(result["capacity_limit"]) - int(result["remaining_count"])
        _record_capacity(
            booking_session_id,
            capacity_limit=int(result["capacity_limit"]),
            occupied_count=occupied_count,
        )
        logger.info(
            "booking hold accepted",
            extra={
                "event": "booking_hold_accepted",
                "intent": "appointment_booking",
                "booking_session_id": booking_session_id,
                "capacity_limit": int(result["capacity_limit"]),
                "occupied_count": occupied_count,
                "result_code": result_code.upper(),
                "latency_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        return BookingHoldResponse(**result, warning=PROTOTYPE_WARNING)

    def release_hold(self, *, hold_id: str, token: str) -> BookingHoldStateResponse:
        self._require_local_prototype()
        result = self.repository.release_hold(hold_id=hold_id, token=token)
        status = str(result["status"])
        BOOKING_HOLDS_TOTAL.labels(
            result="expired" if status == "expired" else "released"
        ).inc()
        session_id = str(result["booking_session_id"])
        snapshot = self._safe_capacity_snapshot(session_id)
        if snapshot is not None:
            _record_capacity(session_id, **snapshot)
            logger.info(
                "booking hold released",
                extra={
                    "event": "booking_hold_released",
                    "intent": "appointment_booking",
                    "booking_session_id": session_id,
                    **snapshot,
                    "result_code": status.upper(),
                },
            )
        return BookingHoldStateResponse(
            hold_id=hold_id,
            status=result["status"],
            expires_at=result["expires_at"],
            warning=PROTOTYPE_WARNING,
        )

    def request_confirmation(
        self,
        *,
        hold_id: str,
        token: str,
    ) -> BookingHoldStateResponse:
        self._require_local_prototype()
        result = self.repository.validate_hold_owner(hold_id=hold_id, token=token)
        if result["status"] != "held":
            if result["status"] == "expired":
                BOOKING_HOLDS_TOTAL.labels(result="expired").inc()
            return BookingHoldStateResponse(
                hold_id=hold_id,
                status=result["status"],
                expires_at=result["expires_at"],
                warning=PROTOTYPE_WARNING,
            )
        raise HeraApiError(
            code="HOSPITAL_CONFIRMATION_REQUIRED",
            message_vi=(
                "Chỗ đã được giữ trong bản demo nhưng HERA chưa thể xác nhận lịch "
                "hẹn của Bệnh viện. Vui lòng tiếp tục qua kênh đặt khám chính thức."
            ),
            status_code=409,
            retryable=False,
        )

    def _safe_capacity_snapshot(
        self,
        booking_session_id: str,
    ) -> dict[str, int] | None:
        try:
            return self.repository.capacity_snapshot(booking_session_id)
        except Exception as exc:
            logger.warning(
                "booking capacity metric refresh failed",
                extra={
                    "event": "booking_capacity_metric_failed",
                    "error_type": exc.__class__.__name__,
                },
            )
            return None


def _record_capacity(
    booking_session_id: str,
    *,
    capacity_limit: int,
    occupied_count: int,
) -> None:
    if not _BOOKING_SESSION_ID.fullmatch(booking_session_id):
        return
    BOOKING_CAPACITY_LIMIT.labels(session_id=booking_session_id).set(capacity_limit)
    BOOKING_OCCUPIED.labels(session_id=booking_session_id).set(occupied_count)


_BOOKING_SESSION_ID = re.compile(r"^BSESSION-[0-9A-F]{20}$")


def _booking_metric_result(error_code: str) -> str:
    if error_code == "CAPACITY_REACHED":
        return "capacity_reached"
    if error_code == "ACTIVE_HOLD_LIMIT_REACHED":
        return "quota_reached"
    if error_code == "IDEMPOTENCY_CONFLICT":
        return "duplicate"
    return "rejected"
