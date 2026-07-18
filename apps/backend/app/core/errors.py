"""Stable public error model for HERA APIs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeraApiError(Exception):
    """An expected failure that is safe to return to the browser."""

    code: str
    message_vi: str
    status_code: int = 400
    retryable: bool = False

    def __str__(self) -> str:
        return self.message_vi


def capacity_reached() -> HeraApiError:
    return HeraApiError(
        code="CAPACITY_REACHED",
        message_vi=(
            "Ca này đã đạt số lượng tối đa trong bản demo. "
            "Vui lòng chọn bác sĩ, ngày hoặc ca khác."
        ),
        status_code=409,
        retryable=False,
    )
