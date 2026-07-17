"""Hospital API integration contracts and placeholder client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HospitalApiResult:
    """Result returned by hospital integration tools."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    source: str = "hospital_api"


class HospitalApiClient:
    """Placeholder for scheduling, doctor, and service APIs."""

    async def lookup_appointment(self, context: dict[str, Any]) -> HospitalApiResult:
        """Look up appointment data.

        TODO: implement after authentication, patient consent, and appointment
        API contracts are available.
        """

        del context
        return _not_configured("Appointment API is not configured yet.")

    async def lookup_doctor_schedule(
        self,
        context: dict[str, Any],
    ) -> HospitalApiResult:
        """Look up doctor schedule data."""

        del context
        return _not_configured("Doctor schedule API is not configured yet.")

    async def lookup_service_price(self, context: dict[str, Any]) -> HospitalApiResult:
        """Look up current service pricing."""

        del context
        return _not_configured("Service price API is not configured yet.")


def _not_configured(message: str) -> HospitalApiResult:
    return HospitalApiResult(success=False, message=message)
