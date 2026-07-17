"""Guardrail pipeline for HERA assistant requests."""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.guardrails.input_guardrail import InputGuardrail
from app.ai.guardrails.output_guardrail import OutputGuardrail


@dataclass(frozen=True)
class GuardrailResult:
    """Generic guardrail result."""

    allowed: bool
    text: str
    reason: str | None = None
    violation_type: str | None = None


class GuardrailPipeline:
    """Run input and output guardrails in a consistent sequence."""

    def __init__(
        self,
        input_guardrail: InputGuardrail | None = None,
        output_guardrail: OutputGuardrail | None = None,
    ) -> None:
        self.input_guardrail = input_guardrail or InputGuardrail()
        self.output_guardrail = output_guardrail or OutputGuardrail()

    def validate_input(self, text: str) -> GuardrailResult:
        """Validate user input."""

        result = self.input_guardrail.validate(text)
        return GuardrailResult(
            allowed=result.allowed,
            text=result.sanitized_text,
            reason=result.message,
            violation_type=result.violation.value if result.violation else None,
        )

    def validate_output(
        self,
        text: str,
        *,
        has_citations: bool,
        requires_grounding: bool,
    ) -> GuardrailResult:
        """Validate assistant output."""

        result = self.output_guardrail.validate(
            text,
            has_citations=has_citations,
            requires_grounding=requires_grounding,
        )
        return GuardrailResult(
            allowed=result.allowed,
            text=text,
            reason=result.message,
            violation_type=result.violation.value if result.violation else None,
        )

