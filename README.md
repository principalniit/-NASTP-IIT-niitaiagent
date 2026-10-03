# NIIT AI SEO Agent

A self-hosted SEO management platform, first deployed for the NASTP Institute of
Information Technology (NIIT) and designed to grow into a multi-tenant SaaS product.
It crawls websites, runs a deterministic SEO rules engine, scores and prioritises
issues, and uses a local AI model only as an optional helper for explanations and
drafts. Nothing is ever published to a live website automatically.

**Status:** Phases 1 to 6 are complete: foundation, crawler, SEO engine, AI assistant
with drafts and approvals, reports and monitoring, and commercial readiness. Since then
the platform has gained:
- invitations;
- Google Search Console;
- JavaScript rendering;
- AI measurement;
- a configurable product name;
- a one-command installer.

See [Feature status](#feature-status) and
[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).

**Quickest install:** with Docker, run `./deploy/install.sh` (Windows:
`deploy\install.ps1`). See [`deploy/README.md`](deploy/README.md). The steps below set up
a development machine instead.

## Contents

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation plan and roadmap](docs/IMPLEMENTATION_PLAN.md)
- [Security](docs/SECURITY.md)
- [NIIT configuration](docs/NIIT_CONFIGURATION.md)
- [Deployment guide](docs/DEPLOYMENT.md) and [security review](docs/SECURITY_REVIEW.md)
- [Local setup](#local-setup)
- [Environment variables](#environment-variables)
- [Database migrations](#database-migrations)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Deployment](#deployment)

## Local setup

### 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | https://www.python.org/downloads/ |
| uv | recent | `pip install uv` or https://docs.astral.sh/uv/ |
| Node.js | 20.9+ (22 LTS recommended) | https://nodejs.org/ |
| pnpm | 9+ | `npm install -g pnpm` |
| PostgreSQL | 15 or 16 | Docker (below) or a local install |
| Ollama | optional, for the AI assistant | https://ollama.com/download |

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
`ADMIN_PASSWORD` environment variable. Used on an existing account, it sets a new
password and signs that account out everywhere. `seed-niit` creates the NIIT organisation and
website project with only the facts listed in `docs/NIIT_CONFIGURATION.md`.

API documentation (not served in production): http://localhost:8000/api/v1/docs

Other administrative commands:

```bash
uv run python -m app.cli reset-password --email someone@niit.edu.pk   # also ends their sessions
uv run python -m app.cli rotate-secrets   # after putting a new key first in INTEGRATIONS_ENCRYPTION_KEYS
uv run python -m app.cli add-projects --org niit --owner-email you@niit.edu.pk --file sites.csv
uv run python -m app.cli ai-report --org niit --days 30      # how AI tasks went and why they failed
uv run python -m app.cli ai-eval --org niit --project "NIIT website" --out before.json   # score the AI
uv run python -m app.cli ai-eval --org niit --project "NIIT website" --cases evals/niit-website.json
uv run python -m app.cli ai-feedback-cases --org niit --out feedback-cases.json   # complaints as tests
```

`add-projects` creates one project per line of `Name, https://address` (lines starting
with `#` are ignored), with the same address checks, plan limits and audit entries as
**New project** in the dashboard. Existing domains are skipped.

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

### 6. PDF reports (optional)

Reports are always available as HTML. For PDF downloads, install Chromium once:

```bash
cd backend
uv run playwright install chromium
```

Then restart the worker. Without it, reports show "PDF not installed" and can still be
printed to PDF from the browser.

### 7. Ollama (optional AI assistant)

```bash
docker compose --profile ai up -d ollama   # or install Ollama natively
ollama pull llama3.1:8b                     # any local model; choose to suit your hardware
```

Then, in `backend/.env`, set `AI_PROVIDER=ollama` and `OLLAMA_DEFAULT_MODEL=llama3.1:8b`,
and restart the API and the worker. AI tasks run in the worker. An organisation owner
or admin then turns AI on under **Settings → AI provider**. The Overview shows whether
the model is available.

Everything else works with AI off. With AI on, the platform produces explanations,
recommendations and drafts for human review; it never changes the website. The AI code
has been tested against a scripted stand-in for Ollama, not a live model. Check the
output on your own pages before relying on it (see `docs/IMPLEMENTATION_PLAN.md`,
section 12).

## Environment variables

Backend variables live in `backend/.env` (template: `backend/.env.example`).

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENVIRONMENT` | `development` | `development`, `test` or `production`. Production refuses insecure settings. |
| `DATABASE_URL` | `postgresql+asyncpg://niit:niit@localhost:5432/niit_seo` | PostgreSQL connection |
| `JWT_SECRET` | empty | Signing key for access tokens, 32+ random characters. Required in production; elsewhere an empty or placeholder value is replaced by a random one each time the API starts. |
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
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama address. Operator-only; organisations cannot change it. |
| `OLLAMA_DEFAULT_MODEL` | empty | Model used when an organisation does not name one, for example `llama3.1:8b` |
| `AI_TIMEOUT_SECONDS` | `180` | Longest wait for one model reply. Use `600` on a PC without a GPU |
| `REPORT_PDF_BROWSER_PATH` | empty | Chromium executable for PDF reports. Empty uses the browser installed by `uv run playwright install chromium` |
| `SCHEDULER_ENABLED` | `false` | Allows scheduled crawls. Each project's schedule must also be turned on |
| `AI_CONTEXT_TOKENS` | `8192` | Prompt window per request. Ollama may otherwise use a smaller default and cut off long prompts |
| `AI_KEEP_ALIVE` | `30m` | How long Ollama keeps the model loaded after a task, so the next one does not wait for it to load. A duration with a unit; `-1m` keeps it until Ollama stops |
| `AI_MAX_ACTIVE_JOBS_PER_ORG` | `3` | Queued or running AI tasks allowed per organisation |
| `INTEGRATIONS_ENCRYPTION_KEYS` | empty | Comma-separated Fernet keys that encrypt integration credentials; the first encrypts. Empty means credentials cannot be stored. Back it up separately from the database |
| `CRAWLER_BROWSER_PATH` | empty | Chromium for projects that render JavaScript. Empty uses `REPORT_PDF_BROWSER_PATH`, then the browser installed by `uv run playwright install chromium` |
| `PRODUCT_NAME` | `AI SEO Agent` | Name in emails and the API documentation (`APP_NAME` is still read). The dashboard's own `NEXT_PUBLIC_PRODUCT_NAME` (in `frontend/.env.local`, see `frontend/.env.example`) sets it on screen |
| `SEARCH_CONSOLE_DAYS` | `90` | Days of Google Search Console data each import fetches. Connecting is done per organisation in the dashboard (`docs/SEARCH_CONSOLE.md`) |
| `PUBLIC_BASE_URL` | `http://localhost:3000` | The dashboard's public address, used in invitation and reset links |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | empty, `587`, empty, empty, empty, `true` | Your organisation's own mail server. Empty `SMTP_HOST` turns email off: invitation links are then shared by hand and password resets go through an administrator |
| `INVITATION_TTL_DAYS` | `7` | How long an invitation link works |
| `PASSWORD_RESET_TTL_MINUTES` | `60` | How long a password reset link works |
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

# End-to-end: resets niit_seo_e2e, seeds an admin and a reviewer, starts a local fixture
# website on :8123, a scripted fake Ollama on :11500, a worker, the API on :8001 and a
# production build on :3100
cd frontend
pnpm exec playwright install chromium   # first time only
pnpm test:e2e
```

The backend suite runs every migration down and up, then tests authentication, token
rotation and reuse detection, rate limiting, role permissions, cross-organisation
isolation, URL safety, settings validation, the NIIT seed, SSRF protection, robots.txt
and sitemap parsing, HTML extraction, full crawls of a local fixture website, every SEO
rule, scoring and prioritisation, the issue lifecycle across repeated crawls, the AI
provider, grounding checks and agent tools against a fake Ollama server, the draft
approval workflow, report generation (including PDF rendering with no network access)
and crawl schedules. Tests never contact live NIIT infrastructure or a real AI model. CI runs all of the above on every pull request
(`.github/workflows/ci.yml`), plus `pip-audit` and `pnpm audit`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `connection refused` on port 5432 | Start PostgreSQL: `docker compose up -d db` |
| `password authentication failed for user "niit"` | Create the role as shown in step 2, or fix `DATABASE_URL` |
| Dashboard shows "Could not load data" with "Internal Server Error" or "The API server is not responding" | The dashboard cannot reach the API. Look at the API window: if it stopped with "The database schema is out of date", run `uv run alembic upgrade head` in `backend` and start it again. Otherwise start it (`uv run uvicorn app.main:app --reload`) and check that `API_ORIGIN` matches; rebuild after changing it |
| Signed out after every page reload | Access tokens live in memory by design; the refresh cookie restores the session. If it does not, check that you open the dashboard via `localhost:3000`, not the API port. |
| `Too many failed login attempts` | Wait five minutes, or restart the API in development |
| A crawl stays "Queued" | Start a worker: `uv run python -m app.worker` |
| SEO pages say "No analysis results yet" | The worker analyses each completed crawl automatically; make sure it is running. A failed analysis shows its reason on the crawl page. |
| Crawl finishes with nothing crawled and a robots.txt note | The site's robots.txt returned a server error or timed out; RFC 9309 then forbids crawling. Try again later. |
| Crawl pages show "Blocked destination" | The host resolves to a private address. Use `CRAWLER_ALLOWED_PRIVATE_NETWORKS` only for servers you own. |
| AI assistant shows "Unavailable" | Ollama is not reachable at `OLLAMA_BASE_URL`, or the model is not pulled (`ollama list`). The platform keeps working. |
| AI assistant shows "off" | Set `AI_PROVIDER=ollama` on the server and turn AI on in organisation settings |
| AI answers are slow, or the first one after a break is much slower | Run `ollama ps` while a task runs: PROCESSOR must say `100% GPU`. Keep the model loaded with `AI_KEEP_ALIVE` (default 30 minutes). `ai-report` shows how many tasks waited for the model to load ("Cold") |
| You want to know whether a change made the AI better | Run `ai-eval` before and after with `--out`, and compare the pass counts and times. It runs a fixed test set like real tasks and saves nothing to the database |
| AI task failed: "The AI model did not respond in time" | Normal on a PC without a GPU. Set `AI_TIMEOUT_SECONDS=600` in `backend/.env` and restart the API and worker, or use a smaller model such as `llama3.2:3b`, or a PC with an NVIDIA GPU |
| Report PDF shows "not installed" | Run `uv run playwright install chromium` in `backend`, then restart the worker. The HTML report works meanwhile and can be printed to PDF from the browser |
| A report stays "Queued" | The worker is not running; reports are generated there |
| Scheduled crawls never start | Set `SCHEDULER_ENABLED=true` in `backend/.env`, restart the worker, and turn the schedule on for the project |
| AI tasks stay "Waiting for the worker" | Start `uv run python -m app.worker`; AI tasks run there, not in the API |
| An AI task failed with "claims not supported by the project data" | The model added numbers or claims that are not in the crawl evidence, so the result was discarded. Try again, or use a larger model |
| "People who wrote or submitted this draft cannot approve it" | Intended: a second person with an approving role, who did not work on the draft, must review |
| "This email already has an account. Send an invitation instead…" | Intended: existing accounts join through an invitation they accept by signing in; platform administrators can still add them directly (see `docs/SECURITY.md`) |
| Sign-in does not get past the sign-in page after updating, or the API or worker stops with "The database schema is out of date" | Run `uv run alembic upgrade head` in `backend`, then restart the API and the worker. Run it after every `git pull` |
| Production start fails with a `JWT_SECRET` or `COOKIE_SECURE` error | Intended safety check; set a strong secret and serve over HTTPS |

## Deployment

The simplest way is the one-command container install: [`deploy/README.md`](deploy/README.md).
For running without containers, see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): a single
Windows machine, or a Linux server behind nginx with HTTPS and systemd, including
secrets, backups, upgrades and key rotation. The latest security review is
[`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md).

## Feature status

| Area | Status |
|------|--------|
| Authentication, sessions, rate limiting | Done |
| Organisations, members, roles, audit log | Done |
| Invitations (people choose their own password) and password reset by email | Done; email is optional and uses your own SMTP server (`docs/EMAIL.md`) |
| AI measurement: run details, `ai-report`, `ai-eval` test sets, feedback on results | Done |
| Google Search Console: clicks, impressions, CTR and position per project, page and query; click opportunities; used by the AI and its title drafts | Done; free, read-only, with your own service account (`docs/SEARCH_CONSOLE.md`) |
| Configurable product name (`PRODUCT_NAME`, `NEXT_PUBLIC_PRODUCT_NAME`) | Done |
| One-command install and upgrade with Docker (Linux, macOS, Windows), optional HTTPS and GPU | Done (`deploy/README.md`) |
| Projects and project settings (including NIIT configuration) | Done |
| Dashboard shell, overview, projects, settings, administration | Done |
| Crawler, Crawl Explorer, Pages browser (Phase 2) | Done; optional JavaScript rendering per project, with every browser request fetched by the guarded crawler |
| SEO engine: 50 rules, scoring, prioritisation, issue lifecycle, SEO dashboards (Phase 3) | Done |
| AI assistant, recommendations, content drafts, approvals (Phase 4) | Done; not yet validated against a live Ollama model |
| Reports (13 sections, HTML and PDF), monitoring, crawl comparison, schedule foundation (Phase 5) | Done |
| Interface uplift: animated sign-in, grouped navigation, interactive overview tiles and tabs, page thumbnails drawn from crawl data, search-result previews, project tiles | Done; motion stops under reduced-motion settings |
| Commercial readiness: tenant verification suite, plans and usage limits, integration records with encrypted credentials, white-label reports, data retention, platform audit log, deployment guide, security review (Phase 6) | Done; integrations are records only, no payments |

Known limitations are listed in `docs/IMPLEMENTATION_PLAN.md`.
