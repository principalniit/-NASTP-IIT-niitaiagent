# NIIT AI SEO Agent

A self-hosted SEO management platform, first deployed for the NASTP Institute of
Information Technology (NIIT) and designed to grow into a multi-tenant SaaS product.
It crawls websites, runs a deterministic SEO rules engine, scores and prioritises
issues, and uses a local AI model only as an optional helper for explanations and
drafts. Nothing is ever published to a live website automatically.

**Status:** Phases 1 (foundation) and 2 (crawler) are complete. The SEO rules engine
and scoring arrive in Phase 3. See
[Feature status](#feature-status) and [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

## Contents

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation plan and roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Security](docs/SECURITY.md)
- [NIIT configuration](docs/NIIT_CONFIGURATION.md)
- [Local setup](#local-setup)
- [Environment variables](#environment-variables)
- [Database migrations](#database-migrations)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Deployment notes](#deployment-notes)

## Local setup

### 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | https://www.python.org/downloads/ |
| uv | recent | `pip install uv` or https://docs.astral.sh/uv/ |
| Node.js | 20.9+ (22 LTS recommended) | https://nodejs.org/ |
| pnpm | 9+ | `npm install -g pnpm` |
| PostgreSQL | 15 or 16 | Docker (below) or a local install |
| Ollama | optional, Phase 4 | https://ollama.com/download |

### 2. Start PostgreSQL

With Docker:

```bash
docker compose up -d db
```

This creates the `niit_seo` database plus `niit_seo_test` and `niit_seo_e2e` for tests,
all owned by user `niit` with password `niit` (local development only).

Without Docker, create the same role and databases in your local PostgreSQL:

```bash
psql -U postgres -c "CREATE ROLE niit WITH LOGIN PASSWORD 'niit' CREATEDB;"
psql -U postgres -c "CREATE DATABASE niit_seo OWNER niit;"
psql -U postgres -c "CREATE DATABASE niit_seo_test OWNER niit;"
psql -U postgres -c "CREATE DATABASE niit_seo_e2e OWNER niit;"
```

### 3. Backend API

```bash
cd backend
cp .env.example .env
# Edit .env: set JWT_SECRET to the output of
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
uv sync
uv run alembic upgrade head
uv run python -m app.cli create-admin --email you@niit.edu.pk --name "Your Name"
uv run python -m app.cli seed-niit --owner-email you@niit.edu.pk
uv run uvicorn app.main:app --reload --port 8000
```

`create-admin` prompts for a password (12 or more characters) or reads it from the
`ADMIN_PASSWORD` environment variable. `seed-niit` creates the NIIT organisation and
website project with only the facts listed in `docs/NIIT_CONFIGURATION.md`.

API documentation: http://localhost:8000/api/v1/docs

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

### 4. Crawl worker

Crawls run in a separate worker process. In another terminal:

```bash
cd backend
uv run python -m app.worker
```

Several workers can run at once. Without a worker, crawls stay queued.

### 5. Dashboard

In a second terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:3000 and sign in with the administrator account.

### 6. Ollama (optional, used from Phase 4)

```bash
docker compose --profile ai up -d ollama   # or install Ollama natively
ollama pull llama3.1:8b                     # any local model; choose to suit your hardware
```

Then set `AI_PROVIDER=ollama` in `backend/.env`. The health check on the Overview page
shows whether Ollama is reachable. Every feature built so far works with AI disabled.

## Environment variables

Backend variables live in `backend/.env` (template: `backend/.env.example`).

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENVIRONMENT` | `development` | `development`, `test` or `production`. Production refuses insecure settings. |
| `DATABASE_URL` | `postgresql+asyncpg://niit:niit@localhost:5432/niit_seo` | PostgreSQL connection |
| `JWT_SECRET` | development placeholder | Signing key for access tokens. 32+ random characters in production. |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | Access token lifetime |
| `REFRESH_TOKEN_TTL_DAYS` | `7` | Refresh token lifetime |
| `COOKIE_SECURE` | `false` | Must be `true` in production (HTTPS) |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated origins allowed to call the API directly |
| `TRUST_PROXY_HEADERS` | `false` | Use the right-most `X-Forwarded-For` entry. Only behind a proxy that appends it; see `docs/SECURITY.md`. |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Failed logins per email per window |
| `LOGIN_RATE_LIMIT_IP_ATTEMPTS` | `20` | Failed logins per client address per window |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `300` | Rate-limit window |
| `CRAWLER_USER_AGENT` | `NIIT-SEO-Agent/0.1 (+https://niit.edu.pk)` | Default crawler identity for new projects |
| `CRAWLER_ALLOWED_PRIVATE_NETWORKS` | empty | Comma-separated CIDRs the crawler may reach although not public. Loopback and link-local are refused in production. |
| `CRAWLER_MAX_RESPONSE_BYTES` | `5000000` | Largest page body read, after decompression |
| `CRAWLER_MAX_REDIRECTS` | `10` | Redirect hops followed per URL |
| `CRAWLER_MAX_SITEMAPS` | `20` | Sitemap files read per crawl |
| `CRAWLER_MAX_DURATION_SECONDS` | `3600` | A crawl stops after this long |
| `WORKER_POLL_SECONDS` | `2.0` | How often an idle worker checks for queued crawls |
| `WORKER_STALE_AFTER_SECONDS` | `300` | Running crawls without a heartbeat for this long are marked failed |
| `AI_PROVIDER` | `none` | `none` or `ollama` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama address |
| `TEST_DATABASE_URL` | `…/niit_seo_test` | Used by the pytest suite only |

Frontend variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_ORIGIN` | `http://127.0.0.1:8000` | Where Next.js proxies `/api/v1`. Read at build time. |

## Database migrations

```bash
cd backend
uv run alembic upgrade head                           # apply all migrations
uv run alembic downgrade -1                           # roll back one migration
uv run alembic revision --autogenerate -m "message"   # create a migration after model changes
uv run alembic check                                  # fail if models and migrations differ
```

Review every autogenerated migration before committing, and never edit a migration that
has been merged.

## Testing

```bash
# Backend: lint, format, types, unit + integration + security tests (needs PostgreSQL)
cd backend
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest

# Frontend: lint, types, production build
cd frontend
pnpm lint && pnpm typecheck && pnpm build

# End-to-end: resets niit_seo_e2e, starts a local fixture website on :8123, a worker,
# the API on :8001 and a production build on :3100
cd frontend
pnpm exec playwright install chromium   # first time only
pnpm test:e2e
```

The backend suite runs every migration down and up, then tests authentication, token
rotation and reuse detection, rate limiting, role permissions, cross-organisation
isolation, URL safety, settings validation, the NIIT seed, SSRF protection, robots.txt
and sitemap parsing, HTML extraction, and full crawls of a local fixture website. Tests never contact live
NIIT infrastructure. CI runs all of the above on every pull request
(`.github/workflows/ci.yml`), plus `pip-audit` and `pnpm audit`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `connection refused` on port 5432 | Start PostgreSQL: `docker compose up -d db` |
| `password authentication failed for user "niit"` | Create the role as shown in step 2, or fix `DATABASE_URL` |
| Dashboard shows "Could not load data" | Check the API is running on port 8000 and `API_ORIGIN` matches; rebuild after changing it |
| Signed out after every page reload | Access tokens live in memory by design; the refresh cookie restores the session. If it does not, check that you open the dashboard via `localhost:3000`, not the API port. |
| `Too many failed login attempts` | Wait five minutes, or restart the API in development |
| A crawl stays "Queued" | Start a worker: `uv run python -m app.worker` |
| Crawl finishes with nothing crawled and a robots.txt note | The site's robots.txt returned a server error or timed out; RFC 9309 then forbids crawling. Try again later. |
| Crawl pages show "Blocked destination" | The host resolves to a private address. Use `CRAWLER_ALLOWED_PRIVATE_NETWORKS` only for servers you own. |
| AI assistant shows "Unavailable" | Ollama is not reachable at `OLLAMA_BASE_URL`. The platform keeps working. |
| Production start fails with a `JWT_SECRET` or `COOKIE_SECURE` error | Intended safety check; set a strong secret and serve over HTTPS |

## Deployment notes

Phase 1 targets local and single-server deployment. A full deployment guide arrives in
Phase 6. Until then:

- Run the API with `ENVIRONMENT=production`, a strong `JWT_SECRET` and `COOKIE_SECURE=true`.
- Bind the API to `127.0.0.1` and expose only the Next.js server, behind an HTTPS reverse
  proxy such as nginx. See `docs/SECURITY.md` for the required `X-Forwarded-For` setup.
- Build the dashboard with `API_ORIGIN` pointing at the API, then `pnpm start`.
- Run `alembic upgrade head` before starting a new version.
- Run at least one `python -m app.worker` process under a supervisor such as systemd.
  Stop it with SIGTERM; it finishes its current crawl first. If it is killed instead,
  that crawl is marked failed after `WORKER_STALE_AFTER_SECONDS`.

## Feature status

| Area | Status |
|------|--------|
| Authentication, sessions, rate limiting | Done |
| Organisations, members, roles, audit log | Done |
| Projects and project settings (including NIIT configuration) | Done |
| Dashboard shell, overview, projects, settings, administration | Done |
| Crawler, Crawl Explorer, Pages browser (Phase 2) | Done; JavaScript rendering deferred |
| SEO rules, scoring, issues (Phase 3) | Not started |
| AI agent, drafts, approvals (Phase 4) | Not started; health check only |
| Reports and monitoring (Phase 5) | Not started |
| Commercial readiness (Phase 6) | Not started |

Known limitations are listed in `docs/IMPLEMENTATION_PLAN.md`.
