from httpx import AsyncClient

from app.cli import seed_niit
from tests.conftest import make_user


async def test_health_reports_database_and_disabled_ai(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["ai"] == {"provider": "none", "status": "disabled", "detail": None}


async def test_health_stays_ok_when_ollama_is_unreachable(client: AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:9")
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "ok"
    assert body["ai"]["status"] == "unavailable"


async def test_error_envelope_and_request_id(client: AsyncClient) -> None:
    missing = await client.get("/api/v1/nope", headers={"X-Request-ID": "abcdef12-3456"})
    assert missing.status_code == 404
    assert missing.headers["x-request-id"] == "abcdef12-3456"
    assert missing.json()["error"]["code"] == "not_found"
    assert missing.json()["request_id"] == "abcdef12-3456"
    injected = await client.get("/api/v1/health", headers={"X-Request-ID": "bad id\n"})
    assert injected.headers["x-request-id"] != "bad id\n"
    assert injected.headers["x-content-type-options"] == "nosniff"
    assert injected.headers["x-frame-options"] == "DENY"


async def test_openapi_is_published(client: AsyncClient) -> None:
    spec = (await client.get("/api/v1/openapi.json")).json()
    assert "/api/v1/projects/{project_id}/settings" in spec["paths"]


async def test_seed_niit_is_idempotent_and_adds_no_invented_facts(client: AsyncClient) -> None:
    owner = await make_user(client, "principal@example.org")
    await seed_niit("principal@example.org")
    await seed_niit("principal@example.org")
    orgs = (await client.get("/api/v1/organisations", headers=owner.headers)).json()
    assert orgs["total"] == 1
    org = orgs["items"][0]
    assert org["name"] == "NASTP Institute of Information Technology"
    projects = (
        await client.get(f"/api/v1/organisations/{org['id']}/projects", headers=owner.headers)
    ).json()
    assert projects["total"] == 1
    project_id = projects["items"][0]["id"]
    settings = (
        await client.get(f"/api/v1/projects/{project_id}/settings", headers=owner.headers)
    ).json()["settings"]
    assert len(settings["content_types"]) == 9
    assert all(ct["url_patterns"] == [] for ct in settings["content_types"])
    assert settings["institutional_profile"]["description"] is None
    assert settings["institutional_profile"]["approved_sources"] == []


async def test_client_ip_uses_rightmost_forwarded_entry_only_when_trusted(
    client: AsyncClient, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.database import get_session_factory
    from app.modules.audit_logs.models import AuditLog

    await make_user(client, "ip@example.org")
    forged = {"X-Forwarded-For": "1.1.1.1, 198.51.100.7"}
    body = {"email": "ip@example.org", "password": "wrong-password-xx"}
    await client.post("/api/v1/auth/login", json=body, headers=forged)
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    await client.post("/api/v1/auth/login", json=body, headers=forged)
    async with get_session_factory()() as session:
        ips = list(
            await session.scalars(
                select(AuditLog.ip_address)
                .where(AuditLog.action == "auth.login_failed")
                .order_by(AuditLog.created_at)
            )
        )
    assert ips == ["203.0.113.10", "198.51.100.7"]
