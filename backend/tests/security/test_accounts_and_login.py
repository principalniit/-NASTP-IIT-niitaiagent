"""Findings from the Phase 6 security review: accounts, sign-in limits, configuration."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.cli import create_admin
from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.rate_limit import FailureLimiter
from app.main import create_app
from app.modules.auth.models import RefreshToken
from tests.conftest import PASSWORD, add_member, make_org, make_user


async def _setup(client: AsyncClient):  # type: ignore[no-untyped-def]
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org_a = await make_org(client, admin, "Org A")
    org_b = await make_org(client, admin, "Org B")
    owner_a = await make_user(client, "owner-a@example.org")
    owner_b = await make_user(client, "owner-b@example.org")
    await add_member(client, admin, org_a["id"], owner_a, "owner")
    await add_member(client, admin, org_b["id"], owner_b, "owner")
    return admin, org_a, org_b, owner_a, owner_b


async def test_an_admin_cannot_attach_an_account_another_organisation_created(
    client: AsyncClient,
) -> None:
    admin, org_a, org_b, owner_a, owner_b = await _setup(client)
    # Org A's owner creates an account for someone else's address, with a known password.
    planted = await client.post(
        f"/api/v1/organisations/{org_a['id']}/members",
        json={
            "email": "victim@other.example",
            "role": "viewer",
            "full_name": "Victim",
            "password": "attacker-knows-this",
        },
        headers=owner_a.headers,
    )
    assert planted.status_code == 201
    # Org B's owner tries to add the real person: the planted account is not attached.
    attach = await client.post(
        f"/api/v1/organisations/{org_b['id']}/members",
        json={"email": "victim@other.example", "role": "admin"},
        headers=owner_b.headers,
    )
    assert attach.status_code == 409
    body = attach.json()["error"]
    assert body["code"] == "account_exists"
    assert "Victim" not in attach.text  # no name or id is disclosed
    members = (
        await client.get(f"/api/v1/organisations/{org_b['id']}/members", headers=owner_b.headers)
    ).text
    assert "victim@other.example" not in members
    # A platform administrator can still attach it deliberately.
    ok = await client.post(
        f"/api/v1/organisations/{org_b['id']}/members",
        json={"email": "victim@other.example", "role": "viewer"},
        headers=admin.headers,
    )
    assert ok.status_code == 201


async def test_promoting_an_existing_account_resets_its_password(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_user(client, "planted@example.org")
    await client.post(
        "/api/v1/auth/login", json={"email": "planted@example.org", "password": PASSWORD}
    )
    client.cookies.clear()
    monkeypatch.setenv("ADMIN_PASSWORD", "operator-chosen-password")
    await create_admin("planted@example.org", "Planted")
    old = await client.post(
        "/api/v1/auth/login", json={"email": "planted@example.org", "password": PASSWORD}
    )
    assert old.status_code == 401
    async with get_session_factory()() as session:
        live = list(
            await session.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
        )
        assert live == []  # sessions opened with the old password are ended
    new = await client.post(
        "/api/v1/auth/login",
        json={"email": "planted@example.org", "password": "operator-chosen-password"},
    )
    assert new.status_code == 200


@pytest.fixture
async def dashboard_client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    """Requests as the API sees them through the dashboard: from a loopback address."""
    transport = ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def test_failed_sign_ins_through_the_dashboard_do_not_lock_everyone_out(
    dashboard_client: AsyncClient,
) -> None:
    await make_user(dashboard_client, "real@example.org")
    limit = get_settings().login_rate_limit_ip_attempts
    for n in range(limit + 5):
        await dashboard_client.post(
            "/api/v1/auth/login", json={"email": f"guess{n}@example.org", "password": "wrong"}
        )
    ok = await dashboard_client.post(
        "/api/v1/auth/login", json={"email": "real@example.org", "password": PASSWORD}
    )
    assert ok.status_code == 200


async def test_direct_clients_are_still_limited_per_address(client: AsyncClient) -> None:
    await make_user(client, "real@example.org")
    limit = get_settings().login_rate_limit_ip_attempts
    for n in range(limit):
        await client.post(
            "/api/v1/auth/login", json={"email": f"guess{n}@example.org", "password": "wrong"}
        )
    blocked = await client.post(
        "/api/v1/auth/login", json={"email": "real@example.org", "password": PASSWORD}
    )
    assert blocked.status_code == 429


def test_limiter_forgets_expired_keys() -> None:
    limiter = FailureLimiter(max_failures=3, window_seconds=0)
    limiter.SWEEP_ABOVE = 5
    for n in range(20):
        limiter.record_failure(f"k{n}")
    assert len(limiter._events) <= 6


def test_weak_jwt_secrets_never_sign_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    for weak in ("", "replace-with-a-long-random-value", "short"):
        with pytest.raises(ValidationError):
            Settings(environment="production", jwt_secret=weak, cookie_secure=True)
        a = Settings(environment="development", jwt_secret=weak).jwt_secret.get_secret_value()
        b = Settings(environment="development", jwt_secret=weak).jwt_secret.get_secret_value()
        assert a != weak and len(a) >= 32 and a != b  # random for each process


async def test_api_docs_are_not_published_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "environment", "production")
    prod = create_app()
    async with AsyncClient(transport=ASGITransport(app=prod), base_url="http://t") as c:
        assert (await c.get("/api/v1/docs")).status_code == 404
        assert (await c.get("/api/v1/openapi.json")).status_code == 404


async def test_only_owners_change_data_retention(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org")
    org_admin = await make_user(client, "orgadmin@example.org")
    await add_member(client, admin, org["id"], org_admin, "admin")
    url = f"/api/v1/organisations/{org['id']}"
    current = (await client.get(url, headers=org_admin.headers)).json()["settings"]
    # Other settings stay editable by admins.
    same = {**current, "brand_tone": "Plain and factual"}
    assert (
        await client.patch(url, json={"settings": same}, headers=org_admin.headers)
    ).status_code == 200
    destructive = {**current, "data_retention": {"keep_crawls": 2}}
    refused = await client.patch(url, json={"settings": destructive}, headers=org_admin.headers)
    assert refused.status_code == 403
    allowed = await client.patch(url, json={"settings": destructive}, headers=admin.headers)
    assert allowed.status_code == 200
    audit = (await client.get(f"{url}/audit-logs", headers=admin.headers)).json()["items"]
    changed = [e for e in audit if e["details"] and "data_retention" in e["details"]]
    assert changed and changed[0]["details"]["data_retention"]["to"]["keep_crawls"] == 2
