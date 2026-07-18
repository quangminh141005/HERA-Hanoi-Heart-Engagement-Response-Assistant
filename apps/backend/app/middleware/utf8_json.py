"""Ensure JSON responses declare UTF-8 for legacy HTTP clients."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.datastructures import MutableHeaders


class Utf8JsonContentTypeMiddleware:
    """Append an explicit UTF-8 charset to JSON response content types."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_utf8(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                content_type = headers.get("content-type", "")
                media_type = content_type.split(";", 1)[0].strip().lower()
                if media_type == "application/json" and "charset=" not in content_type.lower():
                    headers["content-type"] = "application/json; charset=utf-8"
            await send(message)

        await self.app(scope, receive, send_with_utf8)
