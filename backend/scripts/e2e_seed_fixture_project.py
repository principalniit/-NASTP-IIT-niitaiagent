"""Test-only: add a project pointing at the local fixture site to the E2E database.

Project creation through the API rejects local addresses, so the E2E suite seeds this
directly. Never run against a real database; e2e_server.sh guards the database name.
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.database import dispose_engine, get_session_factory
from app.modules.organisations.models import Organisation
from app.modules.projects.models import Project, ProjectSettings
from app.modules.projects.schemas import CrawlSettings, ProjectSettingsData


async def main(port: int) -> None:
    async with get_session_factory()() as session:
        org = await session.scalar(select(Organisation).where(Organisation.slug == "niit"))
        if org is None:
            sys.exit("Run seed-niit first")
        project = Project(
            organisation_id=org.id,
            name="Fixture site",
            root_url=f"http://127.0.0.1:{port}/",
            domain="127.0.0.1",
        )
        session.add(project)
        await session.flush()
        settings = ProjectSettingsData(
            crawl=CrawlSettings(delay_ms=0), excluded_paths=["/wp-admin/*"]
        )
        session.add(
            ProjectSettings(
                project_id=project.id,
                organisation_id=org.id,
                settings=settings.model_dump(mode="json"),
            )
        )
        await session.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
