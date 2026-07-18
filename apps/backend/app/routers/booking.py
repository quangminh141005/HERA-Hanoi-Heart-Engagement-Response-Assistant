"""Booking-session and hold endpoints."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, Query

from app.core.config import get_settings
from app.core.errors import HeraApiError
from app.schemas.booking import (
    BookingHoldRequest,
    BookingHoldResponse,
    BookingHoldStateResponse,
    BookingSessionListResponse,
)
from app.services.booking import BookingService

router = APIRouter(tags=["booking"])


@lru_cache(maxsize=1)
def get_booking_service() -> BookingService:
    return BookingService(get_settings())


@router.get("/booking-sessions", response_model=BookingSessionListResponse)
def list_booking_sessions(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    doctor_query: str | None = Query(default=None),
    facility_code: str | None = Query(default=None),
    session_key: str | None = Query(default=None),
    service: BookingService = Depends(get_booking_service),
) -> BookingSessionListResponse:
    return service.list_sessions(
        from_date=from_date,
        to_date=to_date,
        doctor_query=doctor_query,
        facility_code=facility_code,
        session_key=session_key,
    )


@router.post("/booking-holds", response_model=BookingHoldResponse, status_code=201)
def create_booking_hold(
    payload: BookingHoldRequest,
    anonymous_session_id: str = Header(
        ...,
        alias="X-Anonymous-Session-ID",
        min_length=8,
        max_length=200,
    ),
    service: BookingService = Depends(get_booking_service),
) -> BookingHoldResponse:
    return service.create_hold(
        booking_session_id=payload.booking_session_id,
        idempotency_key=payload.idempotency_key,
        owner_session_id=anonymous_session_id,
        patient_identity=payload.patient.model_dump(),
    )


@router.post(
    "/booking-holds/{hold_id}/confirm",
    response_model=BookingHoldStateResponse,
)
def confirm_booking_hold(
    hold_id: str,
    authorization: str | None = Header(default=None),
    service: BookingService = Depends(get_booking_service),
) -> BookingHoldStateResponse:
    return service.request_confirmation(
        hold_id=hold_id,
        token=_bearer_token(authorization),
    )


@router.delete(
    "/booking-holds/{hold_id}",
    response_model=BookingHoldStateResponse,
)
def release_booking_hold(
    hold_id: str,
    authorization: str | None = Header(default=None),
    service: BookingService = Depends(get_booking_service),
) -> BookingHoldStateResponse:
    return service.release_hold(
        hold_id=hold_id,
        token=_bearer_token(authorization),
    )


def _bearer_token(value: str | None) -> str:
    if not value or not value.lower().startswith("bearer "):
        raise HeraApiError(
            code="HOLD_TOKEN_REQUIRED",
            message_vi="Cần token của chỗ đang giữ để thực hiện thao tác này.",
            status_code=401,
        )
    token = value[7:].strip()
    if not token:
        raise HeraApiError(
            code="HOLD_TOKEN_REQUIRED",
            message_vi="Token giữ chỗ không hợp lệ.",
            status_code=401,
        )
    return token
