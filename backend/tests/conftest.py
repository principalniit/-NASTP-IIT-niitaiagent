"""Shared fixtures. Tests run against a real PostgreSQL database (TEST_DATABASE_URL)."""

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://niit:niit@localhost:5432/niit_seo_test"
)
os.environ["AI_PROVIDER"] = "none"
os.environ["LOG_LEVEL"] = "WARNING"

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from alembic import command
from app.core.database import Base, get_session_factory
from app.main import create_app
from app.modules.auth.service import reset_login_limits
from app.modules.users.service import build_user

PASSWORD = "correct-horse-battery"
BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Run every migration down and up once, which also tests the migrations themselves."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logging"] = False
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    reset_login_limits()
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with get_session_factory()() as session:
        await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await session.commit()


@pytest.fixture(scope="session")
def app():  # type: ignore[no-untyped-def]
    return create_app()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app, client=("203.0.113.10", 50000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@dataclass
class TestUser:
    __test__ = False  # a helper, not a test class

    id: str
    email: str
    headers: dict[str, str]


async def make_user(
    client: AsyncClient, email: str, *, platform_admin: bool = False, name: str = "Test User"
) -> TestUser:
    async with get_session_factory()() as session:
        user = build_user(email, name, PASSWORD, platform_admin=platform_admin)
        session.add(user)
        await session.commit()
        user_id = str(user.id)
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    client.cookies.clear()
    return TestUser(user_id, email, {"Authorization": f"Bearer {token}"})


async def make_org(client: AsyncClient, admin: TestUser, name: str) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        "/api/v1/organisations", json={"name": name}, headers=admin.headers
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def add_member(
    client: AsyncClient, owner: TestUser, org_id: str, user: TestUser, role: str
) -> dict:  # type: ignore[type-arg]
    """Attach an existing test account. Only platform administrators may attach existing
    accounts, so when `owner` is not one, a helper administrator does it instead."""
    url = f"/api/v1/organisations/{org_id}/members"
    body = {"email": user.email, "role": role}
    response = await client.post(url, json=body, headers=owner.headers)
    if response.status_code == 409 and response.json()["error"]["code"] == "account_exists":
        response = await client.post(url, json=body, headers=(await _helper_admin(client)).headers)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


HELPER_ADMIN = "platform-helper@example.test"


async def _helper_admin(client: AsyncClient) -> TestUser:
    from app.modules.users.service import get_by_email

    async with get_session_factory()() as session:
        existing = await get_by_email(session, HELPER_ADMIN)
    if existing is None:
        return await make_user(client, HELPER_ADMIN, platform_admin=True)
    response = await client.post(
        "/api/v1/auth/login", json={"email": HELPER_ADMIN, "password": PASSWORD}
    )
    client.cookies.clear()
    return TestUser(
        str(existing.id),
        HELPER_ADMIN,
        {"Authorization": f"Bearer {response.json()['access_token']}"},
    )


async def make_project(
    client: AsyncClient, user: TestUser, org_id: str, url: str = "https://example.org"
) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        f"/api/v1/organisations/{org_id}/projects",
        json={"name": "Site", "root_url": url},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]
