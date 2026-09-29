"""AI providers. Ollama is the first implementation; others can be added behind the same
interface. The platform keeps working when no provider is available."""

import json
import logging
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.modules.organisations.schemas import OrganisationSettings
from app.providers.interfaces import AIHealth, AIProvider

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
Message = dict[str, str]


class AIError(Exception):
    """A user-facing AI failure. The message is safe to show."""


class AIUnavailableError(AIError):
    pass


class AIOutputInvalidError(AIError):
    pass


@dataclass(frozen=True)
class ProviderChoice:
    enabled: bool
    provider: str
    model: str | None
    reason: str | None = None


def choose_provider(org_settings: OrganisationSettings) -> ProviderChoice:
    settings = get_settings()
    if settings.ai_provider == "none":
        return ProviderChoice(False, "none", None, "AI is disabled on this platform.")
    if org_settings.ai.provider == "none":
        return ProviderChoice(False, "none", None, "AI is turned off in organisation settings.")
    model = org_settings.ai.model or settings.ollama_default_model
    if not model:
        return ProviderChoice(False, "ollama", None, "No Ollama model is configured.")
    return ProviderChoice(True, "ollama", model)


class OllamaProvider:
    """Talks to Ollama's HTTP API and asks for JSON constrained by a JSON schema."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.model = model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = timeout or settings.ai_timeout_seconds
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, trust_env=False, transport=self._transport)

    async def health(self) -> AIHealth:
        try:
            async with self._client(3.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
            if response.status_code != 200:
                return AIHealth(
                    provider="ollama", status="unavailable", detail=f"HTTP {response.status_code}"
                )
            names = {m.get("name", "") for m in response.json().get("models", [])}
            if self.model in names or f"{self.model}:latest" in names:
                return AIHealth(provider="ollama", status="available", detail=self.model)
            return AIHealth(
                provider="ollama",
                status="unavailable",
                detail=f"Model '{self.model}' is not installed in Ollama",
            )
        except (httpx.HTTPError, ValueError):
            return AIHealth(
                provider="ollama", status="unavailable", detail="Ollama is not reachable"
            )

    async def chat_structured(
        self, messages: list[Message], schema: type[T], *, max_attempts: int = 2
    ) -> tuple[T, int, str]:
        """Return (validated output, attempts used, raw text of the final reply)."""
        conversation = list(messages)
        last_error = "no reply"
        for attempt in range(1, max_attempts + 1):
            body: dict[str, Any] = {
                "model": self.model,
                "messages": conversation,
                "stream": False,
                "format": schema.model_json_schema(),
                "options": {"temperature": 0},
            }
            try:
                async with self._client(self.timeout) as client:
                    response = await client.post(f"{self.base_url}/api/chat", json=body)
            except httpx.TimeoutException as exc:
                raise AIUnavailableError("The AI model did not respond in time.") from exc
            except httpx.HTTPError as exc:
                raise AIUnavailableError("The AI service (Ollama) is not reachable.") from exc
            if response.status_code == 404:
                raise AIUnavailableError(f"Model '{self.model}' is not installed in Ollama.")
            if response.status_code != 200:
                raise AIUnavailableError(f"The AI service returned HTTP {response.status_code}.")
            try:
                content = response.json()["message"]["content"]
            except (ValueError, KeyError, TypeError) as exc:
                raise AIUnavailableError("The AI service returned an unexpected response.") from exc
            try:
                return schema.model_validate_json(content), attempt, content
            except ValidationError as exc:
                last_error = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:10]
                )
                logger.info(
                    "AI output failed validation", extra={"attempt": attempt, "errors": last_error}
                )
                conversation = [
                    *conversation,
                    {"role": "assistant", "content": content[:4000]},
                    {
                        "role": "user",
                        "content": (
                            "Your reply did not match the required JSON schema: "
                            f"{last_error}. Reply again with only JSON that matches the schema."
                        ),
                    },
                ]
        raise AIOutputInvalidError(
            f"The AI reply was not valid after {max_attempts} attempts ({last_error})."
        )


def build_provider(choice: ProviderChoice) -> AIProvider:
    """The provider for an enabled choice. New providers are added here."""
    if choice.provider == "ollama" and choice.model:
        return OllamaProvider(choice.model)
    raise AIUnavailableError(choice.reason or "AI is not available.")


def schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))
