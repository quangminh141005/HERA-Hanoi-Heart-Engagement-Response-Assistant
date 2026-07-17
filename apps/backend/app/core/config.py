"""Environment-based application configuration."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_parents = Path(__file__).resolve().parents
PROJECT_ROOT = _parents[4] if len(_parents) > 4 else _parents[-1]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Settings loaded from environment and optional .env files."""

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
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
    RATE_LIMIT_STORAGE: Literal["memory", "redis"] = "memory"
    RATE_LIMIT_ALLOW_MEMORY_IN_PRODUCTION: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = Field(default=120, ge=1)
    RATE_LIMIT_CHAT_PER_MINUTE: int = Field(default=30, ge=1)
    RATE_LIMIT_HEALTH_PER_MINUTE: int = Field(default=300, ge=1)

    PROMETHEUS_METRICS_ENABLED: bool = True
    PROMETHEUS_METRICS_PATH: str = "/metrics"

    LLM_PROVIDER: Literal["noop", "openai", "anthropic", "gemini"] = "noop"
    LLM_MODEL: str = "placeholder"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-latest"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    EMBEDDING_PROVIDER: Literal["noop", "openai"] = "noop"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = Field(default=1536, ge=1)

    VECTOR_STORE_PROVIDER: Literal["none", "pgvector"] = "none"
    VECTOR_STORE_COLLECTION: str = "hera_official_knowledge"
    RAG_TOP_K: int = Field(default=5, ge=1)
    RAG_MIN_CONFIDENCE: float = Field(default=0.55, ge=0.0, le=1.0)

    HOSPITAL_NAME: str = "Hanoi Heart Hospital"
    HOSPITAL_PUBLIC_BASE_URL: str = "https://benhvientimhanoi.vn"
    HOSPITAL_HOTLINE: str = ""
    EMERGENCY_HOTLINE: str = "115"
    HOSPITAL_API_BASE_URL: str | None = None
    HOSPITAL_API_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)

    LANGFUSE_ENABLED: bool = False
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


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()

