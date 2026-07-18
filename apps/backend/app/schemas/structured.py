"""Schemas for structured lookup endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StructuredCitation(BaseModel):
    source_id: str
    title: str
    url: str | None = None


class ServicePriceRecord(BaseModel):
    service_record_id: str
    price_id: str
    display_name: str
    facility_code: str
    amount_vnd: int
    amount_raw: str | None = None
    section: str | None = None
    note: str | None = None
    exact_match: bool = False
    name_similarity: float = 0.0


class ServicePriceLookupResponse(BaseModel):
    query: str
    facility_code: str | None = None
    as_of_date: str | None = None
    classification: str
    warning: str
    records: list[ServicePriceRecord] = Field(default_factory=list)
    citations: list[StructuredCitation] = Field(default_factory=list)
    requires_clarification: bool = False


class BhytTierRecord(BaseModel):
    tier_id: str
    tier_order: int
    member_label: str
    rate_text: str | None = None
    monthly_amount_vnd: int | None = None
    annual_amount_vnd: int | None = None


class BhytLookupResponse(BaseModel):
    as_of_date: str
    policy_id: str
    classification: str
    policy_scope: str = "household_contribution"
    warning: str
    tiers: list[BhytTierRecord] = Field(default_factory=list)
    citations: list[StructuredCitation] = Field(default_factory=list)


class ScheduleEntryRecord(BaseModel):
    schedule_entry_id: str
    service_date: str
    facility_code: str
    room_label: str | None = None
    unit_label: str | None = None
    provider_text: str | None = None
    published_hours_raw: str | None = None
    duty_status: str
    assignee_type: str
    approval_status: str | None = None


class ScheduleLookupResponse(BaseModel):
    week_start: str
    service_date: str | None = None
    facility_code: str | None = None
    doctor_query: str | None = None
    room_query: str | None = None
    classification: str
    warning: str
    records: list[ScheduleEntryRecord] = Field(default_factory=list)
    citations: list[StructuredCitation] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)


class RuntimeClockResponse(BaseModel):
    reference_date: str
    mode: str
    first_schedule_date: str
    last_schedule_date: str


class ReadyResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    structured_bundle_ready: bool
    structured_bundle_path: str
    counts: dict[str, int] = Field(default_factory=dict)
