"""Fixtures shared by integration tests."""

import uuid
from collections.abc import AsyncIterator

import pytest

from app.core.database import get_session_factory
from app.modules.organisations.models import Organisation
from app.modules.projects.models import Project, ProjectSettings
from app.modules.projects.schemas import ProjectSettingsData


@pytest.fixture
async def project() -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """An organisation and project with default settings, created directly in the database."""
    async with get_session_factory()() as session:
        org = Organisation(name="Test", slug=f"t-{uuid.uuid4().hex[:8]}", settings={})
        session.add(org)
        await session.flush()
        proj = Project(organisation_id=org.id, name="Site", root_url="http://x/", domain="x")
        session.add(proj)
        await session.flush()
        session.add(
            ProjectSettings(
                project_id=proj.id,
                organisation_id=org.id,
                settings=ProjectSettingsData().model_dump(mode="json"),
            )
        )
        await session.commit()
        yield org.id, proj.id
