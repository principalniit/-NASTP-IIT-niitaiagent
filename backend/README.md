# Backend

FastAPI service for the NIIT AI SEO Agent. See the root `README.md` for setup, environment
variables, migrations and testing, and `docs/ARCHITECTURE.md` for the module layout.

```
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
```
