"""Keep unit tests isolated from developer-local service credentials."""

from __future__ import annotations

import os

# Process environment has higher priority than the repository-local .env. CI or
# integration jobs can still provide explicit values; ordinary unit tests never
# contact local Redis or export Langfuse traces merely because a developer enabled
# those services for the running application.
os.environ.setdefault("APP_DEBUG", "true")
os.environ.setdefault("RATE_LIMIT_STORAGE", "memory")
os.environ.setdefault("CONVERSATION_MEMORY_BACKEND", "memory")
os.environ.setdefault("STRUCTURED_CACHE_ENABLED", "false")
os.environ.setdefault("LANGFUSE_ENABLED", "false")
