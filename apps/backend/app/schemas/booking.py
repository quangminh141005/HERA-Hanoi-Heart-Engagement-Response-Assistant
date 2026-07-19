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


class BookingDoctorOption(BaseModel):
    doctor_id: str
    doctor_name: str
    facility_codes: list[str] = Field(default_factory=list)
    room_labels: list[str] = Field(default_factory=list)
    unit_labels: list[str] = Field(default_factory=list)
    next_service_date: str
    session_keys: list[str] = Field(default_factory=list)
    open_session_count: int
    remaining_count: int


class BookingDoctorListResponse(BaseModel):
    reference_date: str
    capacity_source: str = "project_mvp_default"
    warning: str
    records: list[BookingDoctorOption] = Field(default_factory=list)


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
    date_of_birth: str | None = Field(default=None, max_length=20)
    gender: str | None = Field(default=None, max_length=24)
    address: str | None = Field(default=None, max_length=240)
    visit_reason: str | None = Field(default=None, max_length=500)
    height_cm: int | None = Field(default=None, ge=30, le=250)
    weight_kg: float | None = Field(default=None, ge=1, le=300)
    blood_pressure: str | None = Field(default=None, max_length=32)
    heart_rate_bpm: int | None = Field(default=None, ge=20, le=250)
    spo2_percent: int | None = Field(default=None, ge=50, le=100)

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

    @field_validator("date_of_birth", "gender", "address", "visit_reason", "blood_pressure")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return " ".join(str(value).split())


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
