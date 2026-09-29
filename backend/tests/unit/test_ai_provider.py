"""OllamaProvider against a local fake Ollama server, and provider selection."""

from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.modules.ai.outputs import MetadataDraftOutput
from app.modules.ai.provider import (
    AIOutputInvalidError,
    AIUnavailableError,
    OllamaProvider,
    choose_provider,
)
from app.modules.organisations.schemas import OrganisationSettings
from tests.fixtures.fake_ollama import FakeOllama, Raw

VALID = {
    "title": "Admissions | Overview",
    "meta_description": "How to apply and what to prepare.",
    "rationale": "Based on the page heading.",
}
MESSAGES = [{"role": "user", "content": "draft"}]


@pytest.fixture
def ollama() -> Iterator[FakeOllama]:
    with FakeOllama(["llama3.1:latest"]) as fake:
        yield fake


def provider(fake: FakeOllama, model: str = "llama3.1") -> OllamaProvider:
    return OllamaProvider(model, base_url=fake.base, timeout=5)


async def test_structured_output_is_requested_and_validated(ollama: FakeOllama) -> None:
    ollama.script(VALID)
    output, attempts, raw = await provider(ollama).chat_structured(MESSAGES, MetadataDraftOutput)
    assert isinstance(output, MetadataDraftOutput) and output.title == VALID["title"]
    assert attempts == 1 and "Admissions" in raw
    request = ollama.requests[0]
    assert request["model"] == "llama3.1" and request["stream"] is False
    assert request["format"]["title"] == "MetadataDraftOutput"
    assert request["options"]["temperature"] == 0
    assert request["options"]["num_ctx"] == get_settings().ai_context_tokens


async def test_invalid_output_is_retried_with_the_errors(ollama: FakeOllama) -> None:
    ollama.script("not json at all", VALID)
    output, attempts, _ = await provider(ollama).chat_structured(MESSAGES, MetadataDraftOutput)
    assert attempts == 2 and output.meta_description == VALID["meta_description"]
    retry = ollama.requests[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": "not json at all"}
    assert "did not match the required JSON schema" in retry[-1]["content"]


async def test_invalid_output_twice_fails(ollama: FakeOllama) -> None:
    ollama.script({"title": "x"}, {"title": "y"})
    with pytest.raises(AIOutputInvalidError, match="not valid after 2 attempts"):
        await provider(ollama).chat_structured(MESSAGES, MetadataDraftOutput)


async def test_missing_model_and_server_errors(ollama: FakeOllama) -> None:
    with pytest.raises(AIUnavailableError, match="not installed"):
        await provider(ollama, "mistral").chat_structured(MESSAGES, MetadataDraftOutput)
    ollama.script(Raw(500, b"{}"))
    with pytest.raises(AIUnavailableError, match="HTTP 500"):
        await provider(ollama).chat_structured(MESSAGES, MetadataDraftOutput)
    ollama.script(Raw(200, b'{"unexpected": true}'))
    with pytest.raises(AIUnavailableError, match="unexpected response"):
        await provider(ollama).chat_structured(MESSAGES, MetadataDraftOutput)


async def test_unreachable_ollama() -> None:
    unreachable = OllamaProvider("llama3.1", base_url="http://127.0.0.1:9", timeout=2)
    with pytest.raises(AIUnavailableError, match="not reachable"):
        await unreachable.chat_structured(MESSAGES, MetadataDraftOutput)
    health = await unreachable.health()
    assert health.status == "unavailable" and health.detail == "Ollama is not reachable"


async def test_health_reports_missing_model(ollama: FakeOllama) -> None:
    assert (await provider(ollama).health()).status == "available"
    missing = await provider(ollama, "mistral").health()
    assert missing.status == "unavailable" and "not installed" in (missing.detail or "")


def test_choose_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    on = OrganisationSettings.model_validate({"ai": {"provider": "ollama", "model": "qwen2.5"}})
    assert not choose_provider(on).enabled  # the platform switch (AI_PROVIDER=none) wins

    monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
    monkeypatch.setattr(get_settings(), "ollama_default_model", "")
    choice = choose_provider(on)
    assert choice.enabled and choice.model == "qwen2.5"

    off = choose_provider(OrganisationSettings())
    assert not off.enabled and "organisation settings" in (off.reason or "")

    no_model = choose_provider(OrganisationSettings.model_validate({"ai": {"provider": "ollama"}}))
    assert not no_model.enabled and "No Ollama model" in (no_model.reason or "")
    monkeypatch.setattr(get_settings(), "ollama_default_model", "llama3.1")
    fallback = choose_provider(OrganisationSettings.model_validate({"ai": {"provider": "ollama"}}))
    assert fallback.enabled and fallback.model == "llama3.1"


def test_build_provider_refuses_a_disabled_choice() -> None:
    from app.modules.ai.provider import ProviderChoice, build_provider
    from app.providers.interfaces import AIProvider

    provider = build_provider(ProviderChoice(True, "ollama", "llama3.1"))
    assert isinstance(provider, OllamaProvider) and isinstance(provider, AIProvider)
    with pytest.raises(AIUnavailableError, match="turned off"):
        build_provider(ProviderChoice(False, "none", None, "AI is turned off."))
