from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import get_session_factory
from app.modules.audit_logs.models import AuditLog
from app.modules.users.models import User
from tests.conftest import PASSWORD, make_user

XHR = {"X-Requested-With": "XMLHttpRequest"}


async def _login(client: AsyncClient, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_login_issues_access_token_and_secure_refresh_cookie(client: AsyncClient) -> None:
    await make_user(client, "ana@example.org")
    response = await _login(client, "ANA@example.org")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    cookie = response.headers["set-cookie"].lower()
    assert "niit_refresh=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "ana@example.org"
    assert me.json()["memberships"] == []


async def test_login_failure_does_not_reveal_whether_account_exists(client: AsyncClient) -> None:
    await make_user(client, "ben@example.org")
    wrong_password = await _login(client, "ben@example.org", "wrong-password-xx")
    unknown_user = await _login(client, "nobody@example.org", "wrong-password-xx")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"] == unknown_user.json()["error"]


async def test_login_is_rate_limited(client: AsyncClient) -> None:
    await make_user(client, "cara@example.org")
    for _ in range(5):
        assert (await _login(client, "cara@example.org", "wrong-password-xx")).status_code == 401
    blocked = await _login(client, "cara@example.org")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


async def test_inactive_user_cannot_log_in(client: AsyncClient) -> None:
    await make_user(client, "dan@example.org")
    async with get_session_factory()() as session:
        user = await session.scalar(select(User).where(User.email == "dan@example.org"))
        assert user is not None
        user.is_active = False
        await session.commit()
    assert (await _login(client, "dan@example.org")).status_code == 401


async def test_protected_routes_require_valid_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401
    assert bad.headers["www-authenticate"] == "Bearer"
    basic = await client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"})
    assert basic.status_code == 401


async def test_refresh_rotates_and_detects_reuse(client: AsyncClient) -> None:
    await make_user(client, "eve@example.org")
    await _login(client, "eve@example.org")
    first_cookie = client.cookies.get("niit_refresh")
    assert first_cookie

    rotated = await client.post("/api/v1/auth/refresh", headers=XHR)
    assert rotated.status_code == 200
    second_cookie = client.cookies.get("niit_refresh")
    assert second_cookie and second_cookie != first_cookie

    # Replaying the first (already rotated) token revokes the whole family.
    client.cookies.set("niit_refresh", first_cookie, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh", headers=XHR)).status_code == 401
    client.cookies.set("niit_refresh", second_cookie, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh", headers=XHR)).status_code == 401

    async with get_session_factory()() as session:
        actions = set(await session.scalars(select(AuditLog.action)))
    assert "auth.refresh_reuse_detected" in actions


async def test_refresh_requires_csrf_header_and_cookie(client: AsyncClient) -> None:
    await make_user(client, "fay@example.org")
    await _login(client, "fay@example.org")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 403
    client.cookies.clear()
    assert (await client.post("/api/v1/auth/refresh", headers=XHR)).status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    await make_user(client, "gus@example.org")
    await _login(client, "gus@example.org")
    cookie = client.cookies.get("niit_refresh")
    assert (await client.post("/api/v1/auth/logout", headers=XHR)).status_code == 204
    client.cookies.set("niit_refresh", cookie or "", path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh", headers=XHR)).status_code == 401


async def test_change_password(client: AsyncClient) -> None:
    user = await make_user(client, "hal@example.org")
    await _login(client, "hal@example.org")
    old_cookie = client.cookies.get("niit_refresh")
    wrong = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "nope", "new_password": "another-long-password"},
        headers=user.headers,
    )
    assert wrong.status_code == 400
    short = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=user.headers,
    )
    assert short.status_code == 422
    ok = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "another-long-password"},
        headers=user.headers,
    )
    assert ok.status_code == 204
    client.cookies.set("niit_refresh", old_cookie or "", path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh", headers=XHR)).status_code == 401
    assert (await _login(client, "hal@example.org")).status_code == 401
    assert (await _login(client, "hal@example.org", "another-long-password")).status_code == 200


async def test_address_limit_is_separate_and_higher_than_email_limit(client: AsyncClient) -> None:
    # 20 failures spread across different emails from one address trip the address limit.
    for i in range(20):
        response = await _login(client, f"user{i}@example.org", "wrong-password-xx")
        assert response.status_code == 401
    blocked = await _login(client, "someone-new@example.org", "wrong-password-xx")
    assert blocked.status_code == 429


async def test_successful_login_is_not_blocked_by_other_users_failures(client: AsyncClient) -> None:
    await make_user(client, "victim@example.org")
    for _ in range(6):
        await _login(client, "attacker-target@example.org", "wrong-password-xx")
    assert (await _login(client, "victim@example.org")).status_code == 200
