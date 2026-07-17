"""Human handoff decisions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HandoffDecision:
    """Decision to route a user to a human support channel."""

    required: bool
    reason: str
    channel: str | None = None


class HandoffService:
    """Decide and format human handoff guidance."""

    def __init__(self, hospital_hotline: str = ""):
        self.hospital_hotline = hospital_hotline

    def required(self, reason: str) -> HandoffDecision:
        """Return a required handoff decision."""

        return HandoffDecision(
            required=True,
            reason=reason,
            channel=self.hospital_hotline or None,
        )

    def format_message(self, decision: HandoffDecision) -> str:
        """Format handoff guidance for the user."""

        if decision.channel:
            return (
                f"Mình cần chuyển bạn sang kênh hỗ trợ chính thức: {decision.channel}. "
                f"Lý do: {decision.reason}"
            )
        return (
            "Mình cần chuyển bạn sang nhân viên hỗ trợ hoặc kênh chính thức "
            "của bệnh viện. "
            f"Lý do: {decision.reason}"
        )
