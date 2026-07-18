"""Versioned API gateway for the HERA FastAPI backend."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.core.config import get_settings
from app.routers import booking, chat, feedback, health, structured

settings = get_settings()

api_router = APIRouter(prefix=settings.API_V1_STR)
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(feedback.router)
api_router.include_router(structured.router)
api_router.include_router(booking.router)


def register_api_gateway(app: FastAPI) -> None:
    """Mount all public API routes through one versioned gateway."""

    app.include_router(api_router)

