"""Booking contracts for the isolated local-capacity prototype."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class BookingSessionRecord(BaseModel):
    booking_session_id: str
    doctor_id: str
    doctor_name: str
    service_date: str
    session_key: str
    facility_code: str | None = None
    room_label: str | None = None
    capacity_limit: int
    occupied_count: int
    remaining_count: int
    status: str
    prototype_only: bool = True
    hospital_appointment_confirmed: bool = False


class BookingSessionListResponse(BaseModel):
    reference_date: str
    capacity_scope: str = "doctor_date_session"
    capacity_source: str = "project_mvp_default"
    warning: str
    records: list[BookingSessionRecord] = Field(default_factory=list)


class BookingPatientIdentity(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone_number: str = Field(min_length=8, max_length=32)
    cccd_number: str | None = Field(default=None, min_length=9, max_length=20)
    bhyt_card_number: str | None = Field(default=None, min_length=8, max_length=32)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) < 8 or len(digits) > 15:
            raise ValueError("phone_number must contain 8-15 digits")
        return value.strip()

    @field_validator("cccd_number")
    @classmethod
    def validate_cccd_number(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        digits = re.sub(r"\D", "", value)
        if len(digits) not in {9, 12}:
            raise ValueError("cccd_number must contain 9 or 12 digits")
        return value.strip()

    @field_validator("bhyt_card_number")
    @classmethod
    def validate_bhyt_card_number(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = re.sub(r"\s+", "", value).upper()
        if len(normalized) < 8 or len(normalized) > 20:
            raise ValueError("bhyt_card_number must contain 8-20 characters")
        return normalized


class BookingHoldRequest(BaseModel):
    booking_session_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=200)
    patient: BookingPatientIdentity


class BookingHoldResponse(BaseModel):
    hold_id: str
    hold_token: str | None = None
    status: str
    expires_at: str
    capacity_limit: int
    capacity_scope: str = "doctor_date_session"
    capacity_source: str = "project_mvp_default"
    remaining_count: int | None = None
    hospital_appointment_confirmed: bool = False
    warning: str
    idempotent_replay: bool = False


class BookingHoldStateResponse(BaseModel):
    hold_id: str
    status: str
    expires_at: str
    hospital_appointment_confirmed: bool = False
    warning: str
