"""Invitations and password resets by email."""

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core import mailer
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.modules.audit_logs.models import AuditLog
from app.modules.auth.models import PasswordResetToken
from app.modules.invitations.models import Invitation
from tests.conftest import PASSWORD, TestUser, add_member, make_org, make_user
from tests.integration.test_plans import assign, make_plan

NEW_PASSWORD = "a-long-new-password-123"


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, str, str]]]:
    """Email switched on, with messages captured instead of sent."""
    sent: list[tuple[str, str, str]] = []
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.test")
    monkeypatch.setattr(settings, "smtp_from", "seo@example.test")
    monkeypatch.setattr(mailer, "_send", lambda to, subject, body: sent.append((to, subject, body)))
    yield sent


def _token(body: str) -> str:
    match = re.search(r"#token=([\w-]+)", body)
    assert match, body
    return match.group(1)


async def _org_with_owner(client: AsyncClient) -> tuple[dict, TestUser]:  # type: ignore[type-arg]
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org A")
    owner = await make_user(client, "owner@example.org")
    await add_member(client, admin, org["id"], owner, "owner")
    return org, owner


async def _invite(
    client: AsyncClient, inviter: TestUser, org_id: str, email: str, role: str = "editor"
) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        f"/api/v1/organisations/{org_id}/invitations",
        json={"email": email, "role": role},
        headers=inviter.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def _roles(client: AsyncClient, user: TestUser, org_id: str) -> dict[str, str]:
    members = await client.get(f"/api/v1/organisations/{org_id}/members", headers=user.headers)
    return {m["user"]["email"]: m["role"] for m in members.json()["items"]}


async def test_a_new_person_accepts_by_creating_their_account(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    org, owner = await _org_with_owner(client)
    created = await _invite(client, owner, org["id"], " New.Person@Example.org ")
    assert created["email_sent"] is True
    assert created["invitation"]["email"] == "new.person@example.org"
    [(to, subject, body)] = outbox
    assert to == "new.person@example.org" and "Org A" in subject
    token = _token(body)
    assert created["invite_url"].endswith(f"/invite#token={token}")

    preview = await client.post("/api/v1/invitations/lookup", json={"token": token})
    assert preview.status_code == 200
    assert preview.json()["organisation_name"] == "Org A"
    assert preview.json()["account_exists"] is False

    accepted = await client.post(
        "/api/v1/invitations/accept-new",
        json={"token": token, "full_name": "New Person", "password": NEW_PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    login = await client.post(
        "/api/v1/auth/login", json={"email": "new.person@example.org", "password": NEW_PASSWORD}
    )
    assert login.status_code == 200
    assert (await _roles(client, owner, org["id"]))["new.person@example.org"] == "editor"

    # Single use.
    again = await client.post(
        "/api/v1/invitations/accept-new",
        json={"token": token, "full_name": "Someone", "password": NEW_PASSWORD},
    )
    assert again.status_code == 404
    assert (
        await client.post("/api/v1/invitations/lookup", json={"token": token})
    ).status_code == 404


async def test_an_existing_account_accepts_only_by_signing_in_as_itself(
    client: AsyncClient,
) -> None:
    org, owner = await _org_with_owner(client)
    existing = await make_user(client, "existing@example.org")
    other = await make_user(client, "other@example.org")
    created = await _invite(client, owner, org["id"], "existing@example.org", "viewer")
    assert created["email_sent"] is False  # email is off: the link is shared by hand
    token = _token(created["invite_url"])

    preview = await client.post("/api/v1/invitations/lookup", json={"token": token})
    assert preview.json()["account_exists"] is True
    # Nobody can take over the account by choosing a password for it.
    takeover = await client.post(
        "/api/v1/invitations/accept-new",
        json={"token": token, "full_name": "Intruder", "password": NEW_PASSWORD},
    )
    assert takeover.status_code == 409
    assert takeover.json()["error"]["code"] == "account_exists"
    # Another signed-in account cannot use someone else's invitation.
    wrong = await client.post(
        "/api/v1/invitations/accept", json={"token": token}, headers=other.headers
    )
    assert wrong.status_code == 403

    accepted = await client.post(
        "/api/v1/invitations/accept", json={"token": token}, headers=existing.headers
    )
    assert accepted.status_code == 200, accepted.text
    roles = await _roles(client, owner, org["id"])
    assert roles["existing@example.org"] == "viewer" and "other@example.org" not in roles
    login = await client.post(
        "/api/v1/auth/login", json={"email": "existing@example.org", "password": PASSWORD}
    )
    assert login.status_code == 200, "accepting must not change the password"


async def test_invitations_can_be_listed_replaced_revoked_and_expire(client: AsyncClient) -> None:
    org, owner = await _org_with_owner(client)
    base = f"/api/v1/organisations/{org['id']}/invitations"
    first = await _invite(client, owner, org["id"], "invitee@example.org")
    second = await _invite(client, owner, org["id"], "invitee@example.org", "viewer")
    pending = (await client.get(base, headers=owner.headers)).json()
    assert [p["id"] for p in pending] == [second["invitation"]["id"]]
    # The replaced link no longer works.
    old = await client.post(
        "/api/v1/invitations/lookup", json={"token": _token(first["invite_url"])}
    )
    assert old.status_code == 404

    revoked = await client.delete(f"{base}/{second['invitation']['id']}", headers=owner.headers)
    assert revoked.status_code == 204
    assert (await client.get(base, headers=owner.headers)).json() == []
    gone = await client.post(
        "/api/v1/invitations/lookup", json={"token": _token(second["invite_url"])}
    )
    assert gone.status_code == 404
    again = await client.delete(f"{base}/{second['invitation']['id']}", headers=owner.headers)
    assert again.status_code == 404

    third = await _invite(client, owner, org["id"], "late@example.org")
    async with get_session_factory()() as session:
        await session.execute(
            update(Invitation).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    expired = await client.post(
        "/api/v1/invitations/accept-new",
        json={
            "token": _token(third["invite_url"]),
            "full_name": "Late",
            "password": NEW_PASSWORD,
        },
    )
    assert expired.status_code == 404
    assert expired.json()["error"]["message"] == "This invitation is not valid or has expired"

    async with get_session_factory()() as session:
        actions = set(await session.scalars(select(AuditLog.action)))
    assert {"invitation.created", "invitation.revoked"} <= actions


async def test_inviting_follows_the_member_rules(client: AsyncClient) -> None:
    org, owner = await _org_with_owner(client)
    admin_user = await make_user(client, "org-admin@example.org")
    await add_member(client, owner, org["id"], admin_user, "admin")
    editor = await make_user(client, "editor@example.org")
    await add_member(client, owner, org["id"], editor, "editor")
    url = f"/api/v1/organisations/{org['id']}/invitations"

    for_editor = await client.post(
        url, json={"email": "x@example.org", "role": "viewer"}, headers=editor.headers
    )
    assert for_editor.status_code == 403
    owner_by_admin = await client.post(
        url, json={"email": "x@example.org", "role": "owner"}, headers=admin_user.headers
    )
    assert owner_by_admin.status_code == 403
    member_again = await client.post(
        url, json={"email": "EDITOR@example.org", "role": "viewer"}, headers=owner.headers
    )
    assert member_again.status_code == 409
    assert (await client.get(url, headers=editor.headers)).status_code == 403


async def test_accepting_respects_the_plan_member_limit(client: AsyncClient) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Org A")  # the admin is its first member
    await make_plan(client, admin, "duo", {"max_members": 2})
    await assign(client, admin, org["id"], "duo")
    one = await _invite(client, admin, org["id"], "one@example.org")
    two = await _invite(client, admin, org["id"], "two@example.org")
    body = {"full_name": "Person", "password": NEW_PASSWORD}
    first = await client.post(
        "/api/v1/invitations/accept-new", json={"token": _token(one["invite_url"]), **body}
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/invitations/accept-new", json={"token": _token(two["invite_url"]), **body}
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "plan_limit_reached"
    # The refused acceptance created no account.
    login = await client.post(
        "/api/v1/auth/login", json={"email": "two@example.org", "password": NEW_PASSWORD}
    )
    assert login.status_code == 401


async def test_password_reset_by_email(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    user = await make_user(client, "forgetful@example.org")
    available = await client.get("/api/v1/auth/password-reset/available")
    assert available.json() == {"email_enabled": True}
    assert user.headers  # signed in before the reset

    unknown = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "nobody@example.org"}
    )
    known = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "Forgetful@example.org"}
    )
    # The same answer either way, so the form does not reveal which accounts exist.
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    [(to, _, body)] = outbox
    assert to == "forgetful@example.org"
    token = _token(body)

    weak = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "short"}
    )
    assert weak.status_code == 422
    done = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert done.status_code == 204
    reused = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reused.status_code == 404

    old = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": NEW_PASSWORD}
    )
    assert new.status_code == 200


async def test_only_the_newest_reset_link_works_and_links_expire(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    await make_user(client, "forgetful@example.org")
    for _ in range(2):
        await client.post(
            "/api/v1/auth/password-reset/request", json={"email": "forgetful@example.org"}
        )
    first, second = (_token(body) for _, _, body in outbox)
    stale = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": first, "new_password": NEW_PASSWORD}
    )
    assert stale.status_code == 404
    async with get_session_factory()() as session:
        await session.execute(
            update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    expired = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": second, "new_password": NEW_PASSWORD}
    )
    assert expired.status_code == 404


async def test_reset_requests_are_limited_per_address(
    client: AsyncClient, outbox: list[tuple[str, str, str]]
) -> None:
    await make_user(client, "forgetful@example.org")
    for _ in range(6):
        response = await client.post(
            "/api/v1/auth/password-reset/request", json={"email": "forgetful@example.org"}
        )
        assert response.status_code == 202
    assert len(outbox) == 3


async def test_without_email_nothing_is_sent(client: AsyncClient) -> None:
    await make_user(client, "forgetful@example.org")
    available = await client.get("/api/v1/auth/password-reset/available")
    assert available.json() == {"email_enabled": False}
    response = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "forgetful@example.org"}
    )
    assert response.status_code == 202
    async with get_session_factory()() as session:
        assert list(await session.scalars(select(PasswordResetToken))) == []


async def test_a_mail_server_failure_still_gives_the_link(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, outbox: list[tuple[str, str, str]]
) -> None:
    def refuse(to: str, subject: str, body: str) -> None:
        raise ConnectionRefusedError("mail server down")

    monkeypatch.setattr(mailer, "_send", refuse)
    org, owner = await _org_with_owner(client)
    created = await _invite(client, owner, org["id"], "someone@example.org")
    assert created["email_sent"] is False
    assert "#token=" in created["invite_url"]
    reset = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "owner@example.org"}
    )
    assert reset.status_code == 202
