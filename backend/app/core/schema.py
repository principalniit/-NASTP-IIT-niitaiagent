"""Start-up check that the database schema matches the code.

After pulling a new version, `alembic upgrade head` must run before the API or worker
starts. Without it, queries fail on missing columns and every screen shows a generic
error, which looks like a broken sign-in. Refusing to start with the exact command to run
is much clearer.
"""

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import get_engine

ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"
UPGRADE_HINT = "Run `uv run alembic upgrade head` in the backend folder, then start again."


class SchemaOutOfDateError(RuntimeError):
    """The database needs migrating before this version can run."""


def code_heads() -> set[str]:
    return set(ScriptDirectory(str(ALEMBIC_DIR)).get_heads())


async def database_revisions() -> set[str]:
    async with get_engine().connect() as connection:
        try:
            rows = await connection.execute(text("SELECT version_num FROM alembic_version"))
        except DBAPIError:
            return set()  # no alembic_version table: the database was never migrated
        return {row[0] for row in rows}


async def check_schema() -> None:
    current, expected = await database_revisions(), code_heads()
    if current != expected:
        found = ", ".join(sorted(current)) or "not migrated"
        raise SchemaOutOfDateError(
            f"The database schema is out of date (database: {found}; this version needs: "
            f"{', '.join(sorted(expected))}). {UPGRADE_HINT}"
        )
