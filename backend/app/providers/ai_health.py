"""AI provider availability check. Generation arrives in Phase 4."""

import httpx

from app.core.config import get_settings
from app.providers.interfaces import AIHealth


async def check_ai_health() -> AIHealth:
    settings = get_settings()
    if settings.ai_provider == "none":
        return AIHealth(provider="none", status="disabled")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
        if response.status_code == 200:
            return AIHealth(provider="ollama", status="available")
        return AIHealth(
            provider="ollama", status="unavailable", detail=f"HTTP {response.status_code}"
        )
    except httpx.HTTPError:
        return AIHealth(provider="ollama", status="unavailable", detail="Ollama is not reachable")
