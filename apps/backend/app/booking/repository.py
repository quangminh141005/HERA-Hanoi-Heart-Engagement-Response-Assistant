"""PostgreSQL repository for atomic prototype booking holds.

Every capacity decision runs in one PostgreSQL transaction.  An owner advisory
lock enforces the cross-session owner quota, while ``FOR UPDATE`` on the
canonical booking-session row serializes capacity decisions across every API
replica.  No process-local or SQLite counter participates in the decision.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import unicodedata
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import HeraApiError, capacity_reached

SessionFactory = Callable[[], Session]


class BookingRepository:
    """Own capacity decisions in the shared PostgreSQL database."""

    def __init__(
        self,
        *,
        hold_token_secret: str,
        hold_ttl_seconds: int,
        max_active_holds_per_owner: int,
        require_approved_doctor: bool = True,
        require_approved_capacity_rule: bool = False,
        pii_hash_secret: str | None = None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.secret = hold_token_secret.encode("utf-8")
        self.pii_secret = (pii_hash_secret or hold_token_secret).encode("utf-8")
        self.hold_ttl_seconds = hold_ttl_seconds
        self.max_active_holds_per_owner = max_active_holds_per_owner
        self.require_approved_doctor = require_approved_doctor
        self.require_approved_capacity_rule = require_approved_capacity_rule
        self.session_factory = session_factory or SessionLocal

    def reference_date(self) -> date:
        """Return the earliest canonical booking date in the seeded release."""

        try:
            with self.session_factory() as db:
                value = db.execute(
                    text("SELECT MIN(service_date) FROM booking_sessions")
                ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise _booking_unavailable() from exc
        if value is None:
            raise HeraApiError(
                code="BOOKING_DATA_UNAVAILABLE",
                message_vi="Chưa có ca đặt lịch nào trong dữ liệu đã duyệt.",
                status_code=503,
                retryable=True,
            )
        return value

    def list_sessions(
        self,
        *,
        from_date: date,
        to_date: date,
        doctor_query: str | None,
        facility_code: str | None,
        session_key: str | None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        now = _utc_now()
        filters = [
            "bs.status = 'open'",
            "bs.prototype_only = TRUE",
            "bs.service_date BETWEEN :from_date AND :to_date",
            "(bs.booking_opens_at IS NULL OR bs.booking_opens_at <= :now)",
            "(bs.booking_closes_at IS NULL OR bs.booking_closes_at > :now)",
        ]
        params: dict[str, Any] = {
            "from_date": from_date,
            "to_date": to_date,
            "now": now,
            "limit": limit,
        }
        if self.require_approved_doctor:
            filters.append(
                "d.approval_status IN "
                "('approved_for_hackathon', 'approved_for_production')"
            )
        if self.require_approved_capacity_rule:
            filters.append("bcr.hospital_approved = TRUE")
        if doctor_query:
            filters.append("d.normalized_name LIKE :doctor_query")
            params["doctor_query"] = f"%{_fold_text(doctor_query)}%"
        if facility_code:
            filters.append("bs.facility_code = :facility_code")
            params["facility_code"] = facility_code
        if session_key:
            filters.append("bs.session_key = :session_key")
            params["session_key"] = session_key

        statement = text(
            f"""
            SELECT
                bs.booking_session_id,
                bs.doctor_id,
                d.display_name AS doctor_name,
                bs.service_date,
                bs.session_key,
                bs.facility_code,
                bs.room_label,
                bs.capacity_limit,
                bs.status,
                bs.prototype_only,
                COUNT(bh.hold_id) FILTER (
                    WHERE bh.status = 'confirmed'
                       OR (bh.status = 'held' AND bh.expires_at > :now)
                ) AS occupied_count
            FROM booking_sessions bs
            JOIN doctors d ON d.doctor_id = bs.doctor_id
            JOIN booking_capacity_rules bcr
              ON bcr.capacity_rule_id = bs.capacity_rule_id
            LEFT JOIN booking_holds bh
              ON bh.booking_session_id = bs.booking_session_id
            WHERE {" AND ".join(filters)}
            GROUP BY bs.booking_session_id, d.display_name
            ORDER BY bs.service_date, d.display_name, bs.session_key
            LIMIT :limit
            """
        )
        try:
            with self.session_factory() as db:
                rows = db.execute(statement, params).mappings().all()
        except SQLAlchemyError as exc:
            raise _booking_unavailable() from exc

        records: list[dict[str, Any]] = []
        for row in rows:
            occupied = int(row["occupied_count"] or 0)
            capacity_limit = int(row["capacity_limit"])
            records.append(
                {
                    **dict(row),
                    "service_date": row["service_date"].isoformat(),
                    "prototype_only": bool(row["prototype_only"]),
                    "occupied_count": occupied,
                    "remaining_count": max(0, capacity_limit - occupied),
                }
            )
        return records

    def create_hold(
        self,
        *,
        booking_session_id: str,
        idempotency_key: str,
        owner_session_id: str,
        patient_identity: Mapping[str, str | None],
    ) -> dict[str, Any]:
        now = _utc_now()
        owner_hash = _hash_value(f"owner:{owner_session_id}")
        idem_hash = _hash_value(f"idem:{idempotency_key}")
        pii = _hash_patient_identity(patient_identity, self.pii_secret)
        hold_id = f"HOLD-{_hash_value(f'{booking_session_id}|{idem_hash}')[:24].upper()}"
        token = self._derive_hold_token(hold_id, owner_hash)
        token_hash = _hash_value(token)

        try:
            with self.session_factory() as db, db.begin():
                # The owner lock must always precede the session row lock.  This
                # global ordering prevents owner-quota races across two sessions.
                db.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": _advisory_lock_key(owner_hash)},
                )
                session = db.execute(
                    text(
                        """
                        SELECT bs.*, d.approval_status AS doctor_approval,
                               bcr.hospital_approved,
                               bcr.production_eligible,
                               bcr.config_source
                        FROM booking_sessions bs
                        JOIN doctors d ON d.doctor_id = bs.doctor_id
                        JOIN booking_capacity_rules bcr
                          ON bcr.capacity_rule_id = bs.capacity_rule_id
                        WHERE bs.booking_session_id = :booking_session_id
                        FOR UPDATE OF bs
                        """
                    ),
                    {"booking_session_id": booking_session_id},
                ).mappings().one_or_none()
                if session is None:
                    raise HeraApiError(
                        code="BOOKING_SESSION_NOT_FOUND",
                        message_vi="Không tìm thấy ca đặt lịch này.",
                        status_code=404,
                    )

                self._expire_relevant_holds(
                    db,
                    now=now,
                    booking_session_id=booking_session_id,
                    owner_hash=owner_hash,
                )
                replay = db.execute(
                    text(
                        """
                        SELECT bh.*, bs.capacity_limit
                        FROM booking_holds bh
                        JOIN booking_sessions bs
                          ON bs.booking_session_id = bh.booking_session_id
                        WHERE bh.booking_session_id = :booking_session_id
                          AND bh.idempotency_key_hash = :idempotency_key_hash
                        """
                    ),
                    {
                        "booking_session_id": booking_session_id,
                        "idempotency_key_hash": idem_hash,
                    },
                ).mappings().one_or_none()
                if replay is not None:
                    if replay["owner_session_hash"] != owner_hash:
                        raise HeraApiError(
                            code="IDEMPOTENCY_CONFLICT",
                            message_vi="Mã thao tác đã được dùng bởi một phiên khác.",
                            status_code=409,
                        )
                    if replay["patient_identity_hash"] != pii["patient_identity_hash"]:
                        raise HeraApiError(
                            code="IDEMPOTENCY_CONFLICT",
                            message_vi=(
                                "Mã thao tác đã được dùng với thông tin "
                                "người bệnh khác."
                            ),
                            status_code=409,
                        )
                    occupied = self._occupied(db, booking_session_id, now)
                    return self._hold_payload(
                        replay,
                        token=token,
                        occupied=occupied,
                        idempotent_replay=True,
                    )

                self._validate_open_session(session, now=now)
                active_owner_holds = int(
                    db.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM booking_holds
                            WHERE owner_session_hash = :owner_hash
                              AND (
                                status = 'confirmed'
                                OR (status = 'held' AND expires_at > :now)
                              )
                            """
                        ),
                        {"owner_hash": owner_hash, "now": now},
                    ).scalar_one()
                )
                if active_owner_holds >= self.max_active_holds_per_owner:
                    raise HeraApiError(
                        code="ACTIVE_HOLD_LIMIT_REACHED",
                        message_vi=(
                            "Phiên này đã có tối đa số chỗ đang giữ. "
                            "Hãy hủy hoặc chờ chỗ cũ hết hạn."
                        ),
                        status_code=429,
                        retryable=True,
                    )

                occupied = self._occupied(db, booking_session_id, now)
                capacity_limit = int(session["capacity_limit"])
                if occupied >= capacity_limit:
                    raise capacity_reached()

                expires_at = now + timedelta(seconds=self.hold_ttl_seconds)
                row = db.execute(
                    text(
                        """
                        INSERT INTO booking_holds(
                            hold_id, booking_session_id, anonymous_token_hash,
                            owner_session_hash, idempotency_key_hash,
                            patient_identity_hash, patient_name_hash,
                            patient_name_masked, patient_phone_hash,
                            patient_phone_masked, patient_cccd_hash,
                            patient_cccd_masked, patient_bhyt_hash,
                            patient_bhyt_masked, status,
                            expires_at, created_at
                        ) VALUES (
                            :hold_id, :booking_session_id, :token_hash,
                            :owner_hash, :idempotency_key_hash,
                            :patient_identity_hash, :patient_name_hash,
                            :patient_name_masked, :patient_phone_hash,
                            :patient_phone_masked, :patient_cccd_hash,
                            :patient_cccd_masked, :patient_bhyt_hash,
                            :patient_bhyt_masked, 'held',
                            :expires_at, :created_at
                        )
                        RETURNING *
                        """
                    ),
                    {
                        "hold_id": hold_id,
                        "booking_session_id": booking_session_id,
                        "token_hash": token_hash,
                        "owner_hash": owner_hash,
                        "idempotency_key_hash": idem_hash,
                        **pii,
                        "expires_at": expires_at,
                        "created_at": now,
                    },
                ).mappings().one()
                return self._hold_payload(
                    {**dict(row), "capacity_limit": capacity_limit},
                    token=token,
                    occupied=occupied + 1,
                    idempotent_replay=False,
                )
        except HeraApiError:
            raise
        except SQLAlchemyError as exc:
            raise _booking_unavailable() from exc

    def capacity_snapshot(self, booking_session_id: str) -> dict[str, int] | None:
        now = _utc_now()
        try:
            with self.session_factory() as db:
                capacity_limit = db.execute(
                    text(
                        """
                        SELECT capacity_limit
                        FROM booking_sessions
                        WHERE booking_session_id = :booking_session_id
                        """
                    ),
                    {"booking_session_id": booking_session_id},
                ).scalar_one_or_none()
                if capacity_limit is None:
                    return None
                occupied = self._occupied(db, booking_session_id, now)
        except SQLAlchemyError as exc:
            raise _booking_unavailable() from exc
        return {
            "capacity_limit": int(capacity_limit),
            "occupied_count": occupied,
        }

    def release_hold(self, *, hold_id: str, token: str) -> dict[str, Any]:
        now = _utc_now()
        try:
            with self.session_factory() as db, db.begin():
                row = self._get_owned_hold(db, hold_id, token, lock=True)
                status = str(row["status"])
                if status == "held" and row["expires_at"] <= now:
                    status = "expired"
                elif status == "held":
                    status = "released"
                if status != row["status"]:
                    row = db.execute(
                        text(
                            """
                            UPDATE booking_holds
                            SET status = :status,
                                released_at = CASE
                                    WHEN :status = 'released' THEN :now
                                    ELSE released_at
                                END
                            WHERE hold_id = :hold_id
                            RETURNING *
                            """
                        ),
                        {"status": status, "now": now, "hold_id": hold_id},
                    ).mappings().one()
                return self._hold_state_payload(row)
        except HeraApiError:
            raise
        except SQLAlchemyError as exc:
            raise _booking_unavailable() from exc

    def validate_hold_owner(self, *, hold_id: str, token: str) -> dict[str, Any]:
        now = _utc_now()
        try:
            with self.session_factory() as db, db.begin():
                row = self._get_owned_hold(db, hold_id, token, lock=True)
                if row["status"] == "held" and row["expires_at"] <= now:
                    row = db.execute(
                        text(
                            """
                            UPDATE booking_holds
                            SET status = 'expired'
                            WHERE hold_id = :hold_id
                            RETURNING *
                            """
                        ),
                        {"hold_id": hold_id},
                    ).mappings().one()
                return self._hold_state_payload(row)
        except HeraApiError:
            raise
        except SQLAlchemyError as exc:
            raise _booking_unavailable() from exc

    def _validate_open_session(self, session: Any, *, now: datetime) -> None:
        if session["status"] != "open" or not session["prototype_only"]:
            raise HeraApiError(
                code="BOOKING_SESSION_CLOSED",
                message_vi="Ca này hiện không mở nhận giữ chỗ.",
                status_code=409,
            )
        if session["booking_opens_at"] and session["booking_opens_at"] > now:
            raise HeraApiError(
                code="BOOKING_SESSION_CLOSED",
                message_vi="Ca này chưa đến thời gian nhận giữ chỗ.",
                status_code=409,
            )
        if session["booking_closes_at"] and session["booking_closes_at"] <= now:
            raise HeraApiError(
                code="BOOKING_SESSION_CLOSED",
                message_vi="Ca này đã hết thời gian nhận giữ chỗ.",
                status_code=409,
            )
        if self.require_approved_doctor and session["doctor_approval"] not in {
            "approved_for_hackathon",
            "approved_for_production",
        }:
            raise HeraApiError(
                code="DOCTOR_NOT_APPROVED",
                message_vi="Bác sĩ trong ca này chưa được duyệt cho bản demo.",
                status_code=409,
            )
        if self.require_approved_capacity_rule and not session["hospital_approved"]:
            raise HeraApiError(
                code="CAPACITY_RULE_NOT_APPROVED",
                message_vi="Quy tắc số lượng của ca này chưa được duyệt.",
                status_code=503,
            )

    @staticmethod
    def _expire_relevant_holds(
        db: Session,
        *,
        now: datetime,
        booking_session_id: str,
        owner_hash: str,
    ) -> None:
        db.execute(
            text(
                """
                UPDATE booking_holds
                SET status = 'expired'
                WHERE status = 'held'
                  AND expires_at <= :now
                  AND (
                    booking_session_id = :booking_session_id
                    OR owner_session_hash = :owner_hash
                  )
                """
            ),
            {
                "now": now,
                "booking_session_id": booking_session_id,
                "owner_hash": owner_hash,
            },
        )

    @staticmethod
    def _occupied(db: Session, booking_session_id: str, now: datetime) -> int:
        return int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM booking_holds
                    WHERE booking_session_id = :booking_session_id
                      AND (
                        status = 'confirmed'
                        OR (status = 'held' AND expires_at > :now)
                      )
                    """
                ),
                {"booking_session_id": booking_session_id, "now": now},
            ).scalar_one()
        )

    @staticmethod
    def _get_owned_hold(
        db: Session,
        hold_id: str,
        token: str,
        *,
        lock: bool,
    ) -> Any:
        lock_clause = " FOR UPDATE" if lock else ""
        row = db.execute(
            text(
                "SELECT * FROM booking_holds WHERE hold_id = :hold_id"
                + lock_clause
            ),
            {"hold_id": hold_id},
        ).mappings().one_or_none()
        if row is None:
            raise HeraApiError(
                code="HOLD_NOT_FOUND",
                message_vi="Không tìm thấy chỗ đang giữ.",
                status_code=404,
            )
        if not hmac.compare_digest(
            str(row["anonymous_token_hash"]),
            _hash_value(token),
        ):
            raise HeraApiError(
                code="HOLD_TOKEN_INVALID",
                message_vi="Bạn không có quyền thao tác chỗ đang giữ này.",
                status_code=403,
            )
        return row

    def _derive_hold_token(self, hold_id: str, owner_hash: str) -> str:
        digest = hmac.new(
            self.secret,
            f"{hold_id}|{owner_hash}".encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @staticmethod
    def _hold_payload(
        row: Any,
        *,
        token: str,
        occupied: int,
        idempotent_replay: bool,
    ) -> dict[str, Any]:
        capacity_limit = int(row["capacity_limit"])
        expires_at = row["expires_at"]
        return {
            "hold_id": row["hold_id"],
            "hold_token": token,
            "status": row["status"],
            "expires_at": (
                expires_at.isoformat()
                if isinstance(expires_at, datetime)
                else str(expires_at)
            ),
            "capacity_limit": capacity_limit,
            "remaining_count": max(0, capacity_limit - occupied),
            "idempotent_replay": idempotent_replay,
        }

    @staticmethod
    def _hold_state_payload(row: Any) -> dict[str, Any]:
        """Return only the non-secret fields needed by the application service."""

        expires_at = row["expires_at"]
        return {
            "hold_id": row["hold_id"],
            "booking_session_id": row["booking_session_id"],
            "status": row["status"],
            "expires_at": (
                expires_at.isoformat()
                if isinstance(expires_at, datetime)
                else str(expires_at)
            ),
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hmac_value(value: str, secret: bytes) -> str:
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _hash_patient_identity(
    patient_identity: Mapping[str, str | None],
    secret: bytes,
) -> dict[str, str | None]:
    name = _normalize_name(patient_identity.get("full_name"))
    phone = _digits(patient_identity.get("phone_number"))
    cccd = _digits(patient_identity.get("cccd_number"))
    bhyt = _normalize_identifier(patient_identity.get("bhyt_card_number"))
    identity_basis = "|".join(
        (
            f"name:{name}",
            f"phone:{phone}",
            f"cccd:{cccd or ''}",
            f"bhyt:{bhyt or ''}",
        )
    )
    return {
        "patient_identity_hash": _hmac_value(identity_basis, secret),
        "patient_name_hash": _hmac_value(f"name:{name}", secret),
        "patient_name_masked": _mask_name(name),
        "patient_phone_hash": _hmac_value(f"phone:{phone}", secret),
        "patient_phone_masked": _mask_tail(phone),
        "patient_cccd_hash": _hmac_value(f"cccd:{cccd}", secret) if cccd else None,
        "patient_cccd_masked": _mask_tail(cccd) if cccd else None,
        "patient_bhyt_hash": _hmac_value(f"bhyt:{bhyt}", secret) if bhyt else None,
        "patient_bhyt_masked": _mask_tail(bhyt) if bhyt else None,
    }


def _normalize_name(value: str | None) -> str:
    return " ".join(_fold_text(value or "").split())


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _normalize_identifier(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def _mask_tail(value: str, *, visible: int = 4) -> str:
    tail = value[-visible:]
    return f"{'*' * max(0, len(value) - len(tail))}{tail}"


def _mask_name(value: str) -> str:
    parts = [part for part in value.split() if part]
    if not parts:
        return "***"
    return " ".join(f"{part[:1]}***" for part in parts)


def _advisory_lock_key(owner_hash: str) -> int:
    """Map an opaque SHA-256 owner hash into PostgreSQL's signed BIGINT key."""

    return int.from_bytes(
        hashlib.sha256(owner_hash.encode("ascii")).digest()[:8],
        byteorder="big",
        signed=True,
    )


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().lower())
    return "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


def _booking_unavailable() -> HeraApiError:
    return HeraApiError(
        code="BOOKING_UNAVAILABLE",
        message_vi="Hệ thống giữ chỗ đang tạm gián đoạn. Vui lòng thử lại sau.",
        status_code=503,
        retryable=True,
    )
