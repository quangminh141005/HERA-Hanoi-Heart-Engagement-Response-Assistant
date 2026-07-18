"""Structured lookup routes backed by PostgreSQL."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.schemas.structured import (
    BhytLookupResponse,
    RuntimeClockResponse,
    ScheduleLookupResponse,
    ServicePriceLookupResponse,
)
from app.services.structured import StructuredDataService

router = APIRouter(tags=["structured"])


@lru_cache(maxsize=1)
def get_structured_service() -> StructuredDataService:
    return StructuredDataService(settings=get_settings())


def close_structured_service() -> None:
    if get_structured_service.cache_info().currsize:
        get_structured_service().close()
        get_structured_service.cache_clear()


@router.get("/service-prices", response_model=ServicePriceLookupResponse)
def service_prices(
    query: str = Query(..., min_length=1),
    facility_code: str | None = Query(default=None),
    as_of: date | None = Query(default=None),
    service: StructuredDataService = Depends(get_structured_service),
) -> ServicePriceLookupResponse:
    return service.lookup_service_prices(
        query=query,
        facility_code=facility_code,
        as_of_date=as_of,
    )


@router.get("/bhyt/household-contributions", response_model=BhytLookupResponse)
def bhyt_household_contributions(
    as_of: date | None = Query(default=None),
    service: StructuredDataService = Depends(get_structured_service),
) -> BhytLookupResponse:
    return service.lookup_bhyt(as_of_date=as_of or service.reference_date())


@router.get("/schedules", response_model=ScheduleLookupResponse)
def schedules(
    week_start: date | None = Query(default=None),
    service_date: date | None = Query(default=None, alias="date"),
    facility_code: str | None = Query(default=None),
    doctor_query: str | None = Query(default=None),
    room_query: str | None = Query(default=None),
    service: StructuredDataService = Depends(get_structured_service),
) -> ScheduleLookupResponse:
    target_date = service_date
    target_week = week_start
    if target_week is None:
        basis = target_date or service.reference_date()
        target_week = basis.fromordinal(basis.toordinal() - basis.weekday())
    return service.lookup_schedules(
        week_start=target_week,
        service_date=target_date,
        facility_code=facility_code,
        doctor_query=doctor_query,
        room_query=room_query,
    )


@router.get("/runtime-clock", response_model=RuntimeClockResponse)
def runtime_clock(
    service: StructuredDataService = Depends(get_structured_service),
) -> RuntimeClockResponse:
    reference = service.reference_date()
    first_date, last_date = service.repository.schedule_date_range()
    return RuntimeClockResponse(
        reference_date=reference.isoformat(),
        mode=service.settings.REFERENCE_DATE_MODE,
        first_schedule_date=first_date.isoformat(),
        last_schedule_date=last_date.isoformat(),
    )
