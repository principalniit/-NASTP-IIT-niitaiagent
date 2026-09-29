"""Integration records with encrypted credentials, and the related admin commands."""

import uuid

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import select, text

from app.cli import reset_password, rotate_secrets
from app.core import crypto
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.auth.models import RefreshToken
from tests.conftest import PASSWORD, add_member, make_org, make_user

SECRET = "wp-application-password-abcd"


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> str:
    value = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "integrations_encryption_keys", _secret(value))
    return value


def _secret(value: str):  # type: ignore[no-untyped-def]
    from pydantic import SecretStr

    return SecretStr(value)


async def setup(client: AsyncClient):  # type: ignore[no-untyped-def]
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org")
    return admin, org


async def test_credentials_are_encrypted_and_never_returned(client: AsyncClient, key: str) -> None:
    admin, org = await setup(client)
    base = f"/api/v1/organisations/{org['id']}/integrations"
    assert (await client.get(f"{base}/encryption", headers=admin.headers)).json() == {
        "available": True
    }
    providers = {
        p["key"]
        for p in (await client.get("/api/v1/integration-providers", headers=admin.headers)).json()
    }
    assert {
        "google_search_console",
        "google_analytics",
        "wordpress",
        "smtp_email",
        "webhook",
    } <= providers

    created = await client.post(
        base,
        json={
            "provider": "wordpress",
            "name": "NIIT website",
            "config": {"site_url": "https://niit.edu.pk", "username": "seo-bot"},
            "secret": SECRET,
        },
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["enabled"] is False and body["connected"] is False
    assert body["secret_set"] is True and body["secret_hint"] == "…abcd"
    assert SECRET not in created.text

    listed = await client.get(base, headers=admin.headers)
    assert SECRET not in listed.text and listed.json()[0]["config"]["username"] == "seo-bot"

    async with get_session_factory()() as session:
        raw = await session.scalar(
            text("SELECT secret FROM integrations WHERE id = :id"), {"id": uuid.UUID(body["id"])}
        )
        assert raw and SECRET.encode() not in bytes(raw)
        assert crypto.decrypt(bytes(raw)) == SECRET

    updated = await client.patch(
        f"/api/v1/integrations/{body['id']}",
        json={"enabled": True, "clear_secret": True},
        headers=admin.headers,
    )
    assert updated.json()["enabled"] is True and updated.json()["secret_set"] is False
    audit = (
        await client.get(f"/api/v1/organisations/{org['id']}/audit-logs", headers=admin.headers)
    ).text
    assert "integration.created" in audit and "integration.updated" in audit and SECRET not in audit
    assert (
        await client.delete(f"/api/v1/integrations/{body['id']}", headers=admin.headers)
    ).status_code == 204


async def test_settings_are_validated_per_provider(client: AsyncClient, key: str) -> None:
    admin, org = await setup(client)
    base = f"/api/v1/organisations/{org['id']}/integrations"
    for bad in (
        {"provider": "zapier", "name": "Nope"},
        {
            "provider": "wordpress",
            "name": "WP",
            "config": {"site_url": "http://insecure.example.org", "username": "a"},
        },
        {
            "provider": "wordpress",
            "name": "WP",
            "config": {"site_url": "https://x.org", "username": "a", "password": "p"},
        },
        {"provider": "google_analytics", "name": "GA", "config": {"property_id": "abc"}},
        {"provider": "webhook", "name": "Hook", "config": {"url": "https://127.0.0.1/hook"}},
    ):
        response = await client.post(base, json=bad, headers=admin.headers)
        assert response.status_code in (400, 422), (bad, response.text)


async def test_no_key_means_no_stored_secrets(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "integrations_encryption_keys", _secret(""))
    admin, org = await setup(client)
    base = f"/api/v1/organisations/{org['id']}/integrations"
    refused = await client.post(
        base,
        json={
            "provider": "smtp_email",
            "name": "Mail",
            "config": {"host": "smtp.example.org", "from_address": "seo@example.org"},
            "secret": "pw",
        },
        headers=admin.headers,
    )
    assert (
        refused.status_code == 409 and refused.json()["error"]["code"] == "encryption_key_missing"
    )
    without_secret = await client.post(
        base,
        json={
            "provider": "smtp_email",
            "name": "Mail",
            "config": {"host": "smtp.example.org", "from_address": "seo@example.org"},
        },
        headers=admin.headers,
    )
    assert without_secret.status_code == 201


async def test_only_owners_and_admins_manage_integrations(client: AsyncClient, key: str) -> None:
    admin, org = await setup(client)
    manager = await make_user(client, "manager@example.org")
    await add_member(client, admin, org["id"], manager, "seo_manager")
    base = f"/api/v1/organisations/{org['id']}/integrations"
    assert (await client.get(base, headers=manager.headers)).status_code == 403
    created = await client.post(
        base,
        json={
            "provider": "webhook",
            "name": "Hook",
            "config": {"url": "https://hooks.example.org/x"},
        },
        headers=admin.headers,
    )
    iid = created.json()["id"]
    assert (
        await client.patch(
            f"/api/v1/integrations/{iid}", json={"enabled": True}, headers=manager.headers
        )
    ).status_code == 403


async def test_rotate_secrets_and_reset_password(
    client: AsyncClient, key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, org = await setup(client)
    created = await client.post(
        f"/api/v1/organisations/{org['id']}/integrations",
        json={
            "provider": "webhook",
            "name": "Hook",
            "config": {"url": "https://hooks.example.org/x"},
            "secret": "signing-secret-1234",
        },
        headers=admin.headers,
    )
    iid = uuid.UUID(created.json()["id"])
    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "integrations_encryption_keys", _secret(f"{new_key},{key}"))
    await rotate_secrets()
    monkeypatch.setattr(
        get_settings(), "integrations_encryption_keys", _secret(new_key)
    )  # old key retired
    async with get_session_factory()() as session:
        raw = await session.scalar(
            text("SELECT secret FROM integrations WHERE id = :id"), {"id": iid}
        )
        assert crypto.decrypt(bytes(raw)) == "signing-secret-1234"

    monkeypatch.setenv("ADMIN_PASSWORD", "a-brand-new-password")
    await reset_password("admin@example.org")
    old = await client.post(
        "/api/v1/auth/login", json={"email": "admin@example.org", "password": PASSWORD}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.org", "password": "a-brand-new-password"},
    )
    assert new.status_code == 200
    async with get_session_factory()() as session:
        live = list(
            await session.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
        )
        assert len(live) == 1  # only the session opened after the reset
