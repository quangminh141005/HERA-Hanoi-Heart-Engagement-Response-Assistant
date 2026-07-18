"""Environment-based application configuration."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_parents = Path(__file__).resolve().parents
PROJECT_ROOT = _parents[4] if len(_parents) > 4 else _parents[-1]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent


class Settings(BaseSettings):
    """Settings loaded from environment and optional .env files."""

    model_config = SettingsConfigDict(
        env_file=(
            str(WORKSPACE_ROOT / ".env"),
            str(PROJECT_ROOT / ".env"),
            str(BACKEND_ROOT / ".env"),
        ),
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "HERA - Hanoi Heart Engagement Response Assistant"
    APP_VERSION: str = "0.1.0"
    APP_DEBUG: bool = True
    ENVIRONMENT: str = "development"
    SERVICE_NAME: str = "hera-api"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "plain"] = "json"

    API_V1_STR: str = "/api/v1"
    REFERENCE_DATE_MODE: Literal["request_time", "dataset_start", "fixed"] = (
        "dataset_start"
    )
    REFERENCE_DATE: date | None = None
    TREAT_PROVIDED_DATA_AS_LATEST: bool = True
    ALLOW_REVIEW_ONLY_DATA: bool = False
    CHAT_MAX_CHARS: int = Field(default=2000, ge=100, le=10_000)
    EPHEMERAL_CONTEXT_TTL_MINUTES: int = Field(default=30, ge=1)
    CONVERSATION_MEMORY_BACKEND: Literal["memory", "redis"] = "memory"
    CONSENTED_MESSAGE_TTL_DAYS: int = Field(default=7, ge=1)
    LOG_RAW_MESSAGES: bool = False

    DATABASE_URL: str = "postgresql+psycopg://hera:hera_password@localhost:5432/hera"
    DB_POOL_SIZE: int = Field(default=3, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=2, ge=0)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, ge=1)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=0)

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
    ]
    CORS_EXTRA_ORIGINS: str | None = None

    RATE_LIMIT_ENABLED: bool = True
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXY_CIDRS: list[str] = [
        "127.0.0.1/32",
        "::1/128",
        "172.16.0.0/12",
    ]
    RATE_LIMIT_STORAGE: Literal["memory", "redis"] = "memory"
    RATE_LIMIT_ALLOW_MEMORY_IN_PRODUCTION: bool = False
    STRUCTURED_CACHE_ENABLED: bool = False
    STRUCTURED_CACHE_TTL_SECONDS: int = Field(default=300, ge=1, le=86_400)
    STRUCTURED_CACHE_MAX_PAYLOAD_BYTES: int = Field(
        default=524_288,
        ge=1_024,
        le=5_242_880,
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = Field(default=120, ge=1)
    RATE_LIMIT_CHAT_PER_MINUTE: int = Field(default=30, ge=1)
    RATE_LIMIT_HEALTH_PER_MINUTE: int = Field(default=300, ge=1)

    PROMETHEUS_METRICS_ENABLED: bool = True
    PROMETHEUS_METRICS_PATH: str = "/metrics"

    LLM_PROVIDER: Literal["noop", "openai"] = "openai"
    LLM_MODEL: str = "gpt-oss-120b"
    API_KEY: str | None = None
    FPT_API_BASE_URL: str = "https://mkp-api.fptcloud.com"
    FPT_LLM_MODEL: str = "gpt-oss-120b"
    FPT_EMBEDDING_MODEL: str = "Vietnamese_Embedding"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-oss-120b"
    OPENAI_BASE_URL: str | None = None
    LLM_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    LLM_MAX_CONCURRENT_REQUESTS: int = Field(default=2, ge=1, le=100)
    LLM_QUEUE_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)
    LLM_RESPONSE_CACHE_ENABLED: bool = True
    LLM_RESPONSE_CACHE_TTL_SECONDS: int = Field(default=300, ge=1, le=86_400)
    LLM_RESPONSE_CACHE_MAX_ENTRIES: int = Field(default=512, ge=1, le=100_000)
    EMBEDDING_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    CHAT_OVERALL_TIMEOUT_SECONDS: float = Field(default=35.0, gt=0)
    MODEL_ROUTING_ENABLED: bool = True
    MODEL_ROUTING_TIMEOUT_SECONDS: float = Field(default=6.0, gt=0)
    MODEL_ROUTING_MAX_TOKENS: int = Field(default=1024, ge=32, le=4096)
    MODEL_ROUTING_EMERGENCY_CONFIDENCE_THRESHOLD: float = Field(
        default=0.62,
        ge=0.0,
        le=1.0,
    )
    MODEL_ROUTING_INTENT_CONFIDENCE_THRESHOLD: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
    )
    # Reserved for the concurrent deployment connectivity probe.
    MODEL_TIMEOUT_SECONDS: float = Field(default=45.0, gt=0)
    MODEL_PROBE_LLM_MAX_TOKENS: int = Field(default=8, ge=1, le=128)
    EMBEDDING_PROVIDER: Literal["noop", "openai"] = "openai"
    EMBEDDING_MODEL: str = "Vietnamese_Embedding"
    EMBEDDING_DIMENSIONS: int = Field(default=1024, ge=1)
    EMBEDDING_BASE_URL: str | None = None

    VECTOR_STORE_PROVIDER: Literal["none", "pgvector"] = "none"
    VECTOR_STORE_COLLECTION: str = "hera_official_knowledge"
    RAG_TOP_K: int = Field(default=3, ge=1)
    RAG_MIN_CONFIDENCE: float = Field(default=0.55, ge=0.0, le=1.0)
    RAG_GENERATION_MAX_TOKENS: int = Field(default=512, ge=32, le=512)

    HOSPITAL_NAME: str = "Hanoi Heart Hospital"
    HOSPITAL_PUBLIC_BASE_URL: str = "https://benhvientimhanoi.vn"
    HOSPITAL_HOTLINE: str = ""
    EMERGENCY_HOTLINE: str = "115"
    HOSPITAL_API_BASE_URL: str | None = None
    HOSPITAL_API_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)

    BOOKING_PROVIDER: Literal["redirect_only", "local_prototype", "hospital"] = (
        "local_prototype"
    )
    DEFAULT_DOCTOR_CAPACITY_PER_SESSION: int = Field(default=20, ge=1)
    BOOKING_HOLD_TTL_SECONDS: int = Field(default=300, ge=30)
    BOOKING_REQUIRE_APPROVED_DOCTOR: bool = True
    BOOKING_REQUIRE_APPROVED_CAPACITY_RULE: bool = False
    BOOKING_ALLOW_PROJECT_MVP_RULE: bool = True
    BOOKING_MAX_ACTIVE_HOLDS_PER_ANONYMOUS_SESSION: int = Field(default=2, ge=1)
    HOLD_TOKEN_SECRET: str = "development-only-change-me"
    BOOKING_PII_HASH_SECRET: str | None = None

    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_BASE_URL: str | None = None
    LANGFUSE_SAMPLE_RATE: float = Field(default=0.2, ge=0.0, le=1.0)
    LANGFUSE_CAPTURE_CONTENT: bool = False
    LANGFUSE_TRACE_INPUT_MAX_CHARS: int = Field(default=500, ge=0)
    LANGFUSE_TRACE_OUTPUT_MAX_CHARS: int = Field(default=1000, ge=0)

    @field_validator("APP_DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "debug"}
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            return json.loads(stripped)
        return [origin.strip() for origin in stripped.split(",") if origin.strip()]

    @field_validator("TRUSTED_PROXY_CIDRS", mode="before")
    @classmethod
    def parse_trusted_proxy_cidrs(cls, value):
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            return json.loads(stripped)
        return [network.strip() for network in stripped.split(",") if network.strip()]

    @model_validator(mode="after")
    def normalize_trusted_proxy_cidrs(self):
        normalized: list[str] = []
        for value in self.TRUSTED_PROXY_CIDRS:
            network = str(ip_network(value, strict=False))
            if network not in normalized:
                normalized.append(network)
        if self.TRUST_PROXY_HEADERS and not normalized:
            raise ValueError(
                "TRUSTED_PROXY_CIDRS must not be empty when proxy headers are trusted"
            )
        self.TRUSTED_PROXY_CIDRS = normalized
        return self

    @model_validator(mode="after")
    def normalize_cors_origins(self):
        origins = list(self.CORS_ORIGINS)
        if self.CORS_EXTRA_ORIGINS:
            origins.extend(
                origin.strip()
                for origin in self.CORS_EXTRA_ORIGINS.split(",")
                if origin.strip()
            )

        normalized: list[str] = []
        seen: set[str] = set()
        for origin in origins:
            clean = origin.strip().rstrip("/")
            if clean != "*" and not clean.startswith(("http://", "https://")):
                clean = f"https://{clean}"
            if clean and clean not in seen:
                normalized.append(clean)
                seen.add(clean)
        self.CORS_ORIGINS = normalized
        return self

    @model_validator(mode="after")
    def normalize_langfuse_endpoint(self):
        """Accept the SDK BASE_URL alias while keeping one internal host field."""

        host = self.LANGFUSE_HOST.strip().rstrip("/")
        base_url = (self.LANGFUSE_BASE_URL or "").strip().rstrip("/")
        if base_url:
            host = base_url
        self.LANGFUSE_HOST = host
        return self

    @model_validator(mode="after")
    def require_shared_rate_limit_storage(self):
        if (
            self.RATE_LIMIT_ENABLED
            and not self.APP_DEBUG
            and self.RATE_LIMIT_STORAGE != "redis"
            and not self.RATE_LIMIT_ALLOW_MEMORY_IN_PRODUCTION
        ):
            raise ValueError(
                "RATE_LIMIT_STORAGE must be 'redis' when APP_DEBUG is false, "
                "unless RATE_LIMIT_ALLOW_MEMORY_IN_PRODUCTION is true."
            )
        return self

    @model_validator(mode="after")
    def enforce_production_safety(self):
        production = self.ENVIRONMENT.lower() == "production"
        if not production:
            return self
        problems: list[str] = []
        if "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS must not contain '*' in production")
        if self.ALLOW_REVIEW_ONLY_DATA:
            problems.append("ALLOW_REVIEW_ONLY_DATA must be false in production")
        if self.BOOKING_PROVIDER == "local_prototype":
            problems.append(
                "BOOKING_PROVIDER=local_prototype is forbidden in production"
            )
        if self.BOOKING_ALLOW_PROJECT_MVP_RULE:
            problems.append(
                "BOOKING_ALLOW_PROJECT_MVP_RULE must be false in production"
            )
        if self.HOLD_TOKEN_SECRET == "development-only-change-me":
            problems.append("HOLD_TOKEN_SECRET must be changed in production")
        if not self.BOOKING_PII_HASH_SECRET:
            problems.append("BOOKING_PII_HASH_SECRET is required in production")
        elif self.BOOKING_PII_HASH_SECRET == self.HOLD_TOKEN_SECRET:
            problems.append(
                "BOOKING_PII_HASH_SECRET must differ from HOLD_TOKEN_SECRET"
            )
        if self.LOG_RAW_MESSAGES:
            problems.append("LOG_RAW_MESSAGES must be false in production")
        if self.LLM_PROVIDER == "openai" and not (self.API_KEY or self.OPENAI_API_KEY):
            problems.append("An API key is required for the configured LLM provider")
        if self.EMBEDDING_PROVIDER == "openai" and not (
            self.API_KEY or self.OPENAI_API_KEY
        ):
            problems.append("An API key is required for Vietnamese_Embedding")
        if self.API_KEY and self.FPT_LLM_MODEL != "gpt-oss-120b":
            problems.append("FPT_LLM_MODEL must be gpt-oss-120b for this release")
        if self.API_KEY and self.FPT_EMBEDDING_MODEL != "Vietnamese_Embedding":
            problems.append(
                "FPT_EMBEDDING_MODEL must be Vietnamese_Embedding for this release"
            )
        if self.API_KEY and self.EMBEDDING_DIMENSIONS != 1024:
            problems.append("Vietnamese_Embedding dimension must be 1024")
        if self.LANGFUSE_ENABLED and not (
            self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY
        ):
            problems.append(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required when "
                "Langfuse tracing is enabled"
            )
        if self.LANGFUSE_CAPTURE_CONTENT:
            problems.append("LANGFUSE_CAPTURE_CONTENT must be false in production")
        if problems:
            raise ValueError("; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
