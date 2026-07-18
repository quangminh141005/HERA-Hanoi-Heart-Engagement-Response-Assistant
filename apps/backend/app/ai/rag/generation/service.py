"""Grounded answer generation service."""

from __future__ import annotations

import re

from app.ai.llm.client import LLMClient
from app.ai.observability.tracing import start_observation
from app.ai.rag.generation.evidence_validator import validate_against_evidence
from app.ai.rag.schemas import GroundedAnswer, RetrievedChunk
from app.core.config import Settings


class GenerationService:
    """Generate grounded answers from retrieved chunks."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        settings: Settings | None = None,
    ):
        self.llm_client = llm_client
        self.settings = settings

    async def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        locale: str = "vi",
    ) -> GroundedAnswer:
        """Generate an answer. Refuse when no official context is available."""

        if not chunks:
            return GroundedAnswer(
                answer=(
                    "Hi\u1ec7n t\u1ea1i HERA ch\u01b0a c\u00f3 \u0111\u1ee7 "
                    "ngu\u1ed3n ch\u00ednh th\u1ee9c \u0111\u1ec3 tr\u1ea3 "
                    "l\u1eddi ch\u1eafc ch\u1eafn c\u00e2u h\u1ecfi n\u00e0y. "
                    "Vui l\u00f2ng ki\u1ec3m tra website ch\u00ednh th\u1ee9c "
                    "c\u1ee7a B\u1ec7nh vi\u1ec7n Tim H\u00e0 N\u1ed9i "
                    "ho\u1eb7c li\u00ean h\u1ec7 hotline b\u1ec7nh vi\u1ec7n "
                    "\u0111\u1ec3 \u0111\u01b0\u1ee3c x\u00e1c nh\u1eadn."
                ),
                citations=[],
                confidence=0.0,
            )

        context = "\n\n".join(
            f"[{chunk.source.source_id}] {_neutralize_prompt_control_tokens(chunk.text)}"
            for chunk in chunks
        )
        deterministic_answer = "\n".join(f"\u2022 {chunk.text}" for chunk in chunks)
        generation_mode = "deterministic"
        validation_issues: list[str] = []
        exact_approved_fact = (
            len(chunks) == 1
            and chunks[0].source.document_type == "official_fact_exact"
        )
        if exact_approved_fact:
            answer = deterministic_answer
            generation_mode = "deterministic_exact"
        elif getattr(self.llm_client, "provider_name", "") == "noop":
            answer = deterministic_answer
        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "B\u1ea1n l\u00e0 HERA. Tr\u1ea3 l\u1eddi \u0111\u00fang "
                        "c\u00e2u h\u1ecfi, ng\u1eafn g\u1ecdn b\u1eb1ng "
                        "ti\u1ebfng Vi\u1ec7t v\u00e0 ch\u1ec9 d\u00f9ng "
                        "nh\u1eefng fact li\u00ean quan tr\u1ef1c ti\u1ebfp "
                        "trong context. "
                        "Kh\u00f4ng li\u1ec7t k\u00ea fact kh\u00f4ng li\u00ean "
                        "quan; kh\u00f4ng th\u00eam gi\u00e1, l\u1ecbch, "
                        "b\u00e1c s\u0129, URL, s\u1ed1 \u0111i\u1ec7n tho\u1ea1i, "
                        "ch\u1ea9n \u0111o\u00e1n ho\u1eb7c l\u1eddi khuy\u00ean "
                        "\u0111i\u1ec1u tr\u1ecb ngo\u00e0i context. N\u1ebfu "
                        "context kh\u00f4ng \u0111\u1ee7 th\u00ec n\u00f3i "
                        "kh\u00f4ng \u0111\u1ee7 d\u1eef li\u1ec7u."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"C\u00e2u h\u1ecfi: {query}\n\n"
                        f"Fact \u0111\u00e3 duy\u1ec7t:\n{context}"
                    ),
                },
            ]
            generated = await self._generate_with_trace(
                messages,
                temperature=0.0,
                max_tokens=(
                    self.settings.RAG_GENERATION_MAX_TOKENS
                    if self.settings is not None
                    else 192
                ),
            )
            validation = validate_against_evidence(
                generated,
                query=query,
                evidence=[chunk.text for chunk in chunks],
            )
            if generated.startswith("HERA ch\u01b0a \u0111\u01b0\u1ee3c c\u1ea5u h\u00ecnh LLM"):
                answer = deterministic_answer
                validation_issues = ["provider_fallback"]
            elif validation.allowed:
                answer = generated
                generation_mode = "model_validated"
            else:
                # A direct approved fact is safer than displaying an unsupported
                # paraphrase. The model output is discarded and never persisted.
                answer = deterministic_answer
                validation_issues = list(validation.issues)
        return GroundedAnswer(
            answer=answer,
            citations=[chunk.source for chunk in chunks],
            record_ids=[chunk.chunk_id for chunk in chunks],
            confidence=max(chunk.score for chunk in chunks),
            generation_mode=generation_mode,
            validation_issues=validation_issues,
        )

    async def _generate_with_trace(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if self.settings is None:
            return await self.llm_client.generate(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        trace_kwargs = {
            "model": self.settings.FPT_LLM_MODEL,
            "model_parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        }
        if self.settings.LANGFUSE_CAPTURE_CONTENT:
            trace_kwargs["input"] = messages
        with start_observation(
            "hera.rag.generation_stage",
            settings=self.settings,
            as_type="span",
            metadata={
                "provider": self.settings.LLM_PROVIDER,
                "model": self.settings.FPT_LLM_MODEL,
                "max_tokens": max_tokens,
                "model_generation_requested": True,
                "content_capture": self.settings.LANGFUSE_CAPTURE_CONTENT,
                "streaming": False,
                "ttft_available": False,
            },
            **trace_kwargs,
        ) as observation:
            try:
                result = await self.llm_client.generate(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                observation.update(
                    metadata={
                        "result": "error",
                        "error_type": exc.__class__.__name__,
                    }
                )
                raise
            trace_update = {"metadata": {"result": "success"}}
            if self.settings.LANGFUSE_CAPTURE_CONTENT:
                trace_update["output"] = result
            observation.update(**trace_update)
            return result


_SOURCE_MARKER_RE = re.compile(r"\[\s*(?:source|src|sources?)\b", re.IGNORECASE)
_SOURCES_TAG_RE = re.compile(r"(?im)^([ \t]*)(sources?)(\s*:\s*)(\[?[\w,\-\s]+\]?)[ \t]*$")
_SEPARATOR_RE = re.compile(r"-{4,}")


def _neutralize_prompt_control_tokens(text: str) -> str:
    """Defang source-control tokens embedded inside retrieved text."""

    if not text:
        return text
    text = _SOURCE_MARKER_RE.sub("(source", text)
    text = _SOURCES_TAG_RE.sub(r"\1\2 \4", text)
    return _SEPARATOR_RE.sub("---", text)
