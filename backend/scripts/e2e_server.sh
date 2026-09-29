#!/usr/bin/env bash
# Reset the end-to-end database, seed a known admin, a reviewer, the NIIT tenant and a
# project that points at a local fixture website, then serve the fixture site, a fake
# Ollama, the worker and the API. Used by frontend/playwright.config.ts. Never point E2E_DATABASE_URL at a real
# database.
set -euo pipefail
cd "$(dirname "$0")/.."

export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+asyncpg://niit:niit@localhost:5432/niit_seo_e2e}"
export ENVIRONMENT=test
# AI runs against a scripted stand-in for Ollama (tests/fixtures/fake_ollama.py), never a
# real model. Organisations still start with AI off until an admin enables it.
export AI_PROVIDER=ollama
export OLLAMA_DEFAULT_MODEL=llama3.1
export ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-e2e-admin-password}"
export WORKER_POLL_SECONDS=0.5
PORT="${E2E_API_PORT:-8001}"
FIXTURE_PORT="${E2E_FIXTURE_PORT:-8123}"
OLLAMA_PORT="${E2E_OLLAMA_PORT:-11500}"
export OLLAMA_BASE_URL="http://127.0.0.1:$OLLAMA_PORT"
# Chromium for PDF reports, if one is installed; otherwise reports are HTML only.
export REPORT_PDF_BROWSER_PATH="${E2E_PDF_BROWSER_PATH:-}"
ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-admin@e2e.example.org}"

case "$DATABASE_URL" in
  *_e2e*) ;;
  *) echo "Refusing to reset a database whose name does not contain _e2e" >&2; exit 1 ;;
esac

trap 'kill $(jobs -p) 2>/dev/null || true' EXIT INT TERM

uv run alembic downgrade base
uv run alembic upgrade head
uv run python -m app.cli create-admin --email "$ADMIN_EMAIL" --name "E2E Admin"
uv run python -m app.cli seed-niit --owner-email "$ADMIN_EMAIL"
uv run python -m scripts.e2e_seed_fixture_project "$FIXTURE_PORT"

uv run python -m tests.fixtures.site "$FIXTURE_PORT" &
uv run python -m tests.fixtures.fake_ollama "$OLLAMA_PORT" llama3.1:latest &
# Loopback is allowed here only so the worker can reach the fixture site; production
# refuses this setting.
CRAWLER_ALLOWED_PRIVATE_NETWORKS=127.0.0.1/32 uv run python -m app.worker &
uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
wait -n
