"""The API and worker refuse to start on a database that has not been migrated."""

import pytest
from sqlalchemy import text

from app.core.database import get_session_factory
from app.core.schema import SchemaOutOfDateError, check_schema, code_heads


async def _set_version(version: str) -> None:
    async with get_session_factory()() as session:
        await session.execute(text("UPDATE alembic_version SET version_num = :v"), {"v": version})
        await session.commit()


async def test_a_migrated_database_passes() -> None:
    await check_schema()


async def test_an_outdated_database_is_refused_with_the_fix() -> None:
    (head,) = code_heads()
    await _set_version("0005")
    try:
        with pytest.raises(SchemaOutOfDateError, match="alembic upgrade head"):
            await check_schema()
    finally:
        await _set_version(head)
