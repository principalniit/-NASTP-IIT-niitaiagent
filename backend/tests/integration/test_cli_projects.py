"""Bulk project creation from the command line uses the same checks as the dashboard."""

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.cli import add_projects
from tests.conftest import make_org, make_user


async def test_add_projects_from_a_list(
    client: AsyncClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Example Institute")
    sites = tmp_path / "sites.csv"
    sites.write_text(
        "# name, address\n"
        "Admissions, https://admissions.example.org\n"
        "Library, https://lib.example.org\n"
        "\n"
        "Intranet, http://localhost:8080\n"
        "Admissions again, https://admissions.example.org/\n",
        encoding="utf-8",
    )
    await add_projects(org["slug"], "admin@example.org", str(sites))
    out = capsys.readouterr().out
    assert "Created Admissions" in out and "Created Library" in out
    assert "Skipped Intranet" in out  # local addresses are refused, as in the dashboard
    assert "Skipped Admissions again: A project for this domain already exists" in out
    assert "2 of 4 projects created." in out

    listed = (
        await client.get(f"/api/v1/organisations/{org['id']}/projects", headers=admin.headers)
    ).json()
    assert {p["name"] for p in listed["items"]} == {"Admissions", "Library"}
    audit = (
        await client.get(f"/api/v1/organisations/{org['id']}/audit-logs", headers=admin.headers)
    ).text
    assert "project.created" in audit


async def test_add_projects_needs_an_owner_or_admin(client: AsyncClient, tmp_path: Path) -> None:
    admin = await make_user(client, "admin@example.org", platform_admin=True)
    org = await make_org(client, admin, "Example Institute")
    await make_user(client, "outsider@example.org")
    sites = tmp_path / "sites.csv"
    sites.write_text("Admissions, https://admissions.example.org\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not a member"):
        await add_projects(org["slug"], "outsider@example.org", str(sites))
