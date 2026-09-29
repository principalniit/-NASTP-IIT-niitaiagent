from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import get_session_factory
from app.providers.ai_health import check_ai_health
from app.providers.interfaces import AIHealth

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    ai: AIHealth
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        database: Literal["ok", "unavailable"] = "ok"
    except Exception:
        database = "unavailable"
    ai = await check_ai_health()
    # AI being off or unreachable does not degrade the platform; the core runs without it.
    return HealthResponse(
        status="ok" if database == "ok" else "degraded", database=database, ai=ai, version="0.1.0"
    )
