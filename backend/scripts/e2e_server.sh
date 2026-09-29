#!/usr/bin/env bash
# Reset the end-to-end database, seed a known admin and the NIIT tenant, then serve the API.
# Used by frontend/playwright.config.ts. Never point E2E_DATABASE_URL at a real database.
set -euo pipefail
cd "$(dirname "$0")/.."

export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+asyncpg://niit:niit@localhost:5432/niit_seo_e2e}"
export ENVIRONMENT=test
export AI_PROVIDER=none
export ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-e2e-admin-password}"
PORT="${E2E_API_PORT:-8001}"

case "$DATABASE_URL" in
  *_e2e*) ;;
  *) echo "Refusing to reset a database whose name does not contain _e2e" >&2; exit 1 ;;
esac

uv run alembic downgrade base
uv run alembic upgrade head
uv run python -m app.cli create-admin --email "${E2E_ADMIN_EMAIL:-admin@e2e.example.org}" --name "E2E Admin"
uv run python -m app.cli seed-niit --owner-email "${E2E_ADMIN_EMAIL:-admin@e2e.example.org}"
exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
