"""No-op trace helpers with Langfuse-ready shape."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class NoopObservation:
    """Observation object that accepts update calls."""

    def update(self, **kwargs: Any) -> None:
        del kwargs


@contextmanager
def start_observation(name: str, **kwargs: Any) -> Iterator[NoopObservation]:
    """Start an observation or return no-op until tracing is configured."""

    del name, kwargs
    yield NoopObservation()

