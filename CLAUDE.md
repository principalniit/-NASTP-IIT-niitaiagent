# CLAUDE.md — NIIT AI SEO Agent

## Project mission

Build a secure, modular, locally deployable AI SEO management platform, initially for
the NASTP Institute of Information Technology (NIIT) and later commercialised as a
multi-tenant SaaS. It crawls sites, runs a deterministic SEO rules engine, scores and
prioritises issues, and uses AI only as an optional layer for explanations and drafts.

Read before non-trivial work: `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`
(phases and feature status; `docs/PHASES.md` is the overview), `docs/SECURITY.md`,
`docs/NIIT_CONFIGURATION.md`. By topic: `docs/DATABASE.md` (tables, migrations),
`docs/PROMPTS.md` (AI prompts, grounding, evaluation), `docs/ERROR_HANDLING.md` (error
codes, job failures, troubleshooting).

## Core architecture

- **Frontend:** Next.js (App Router), TypeScript strict, Tailwind CSS, shadcn/ui,
  TanStack Query, React Hook Form + Zod, Recharts. Package manager `pnpm`.
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, Argon2id,
  JWT. Python 3.12, package manager `uv`.
- **Database:** PostgreSQL.
- **Crawler:** httpx behind the SSRF guard, selectolax for HTML, lxml for sitemaps.
  Optional JavaScript rendering per project with Playwright, where the browser has no
  network of its own: every sub-request is fetched by the guarded crawler client (see
  `docs/SECURITY.md`).
- **AI:** Ollama initially, behind the provider-independent interfaces in
  `backend/app/providers/`.
- **Tests:** pytest (unit, integration, security), frontend lint and type checks, and
  Playwright end-to-end tests.

```
backend/app/core/        config, logging, db, security, errors
backend/app/modules/     one folder per module: models, schemas, service, router
backend/app/providers/   provider interfaces (AI, keywords, CMS, ...)
backend/app/worker.py    background crawl worker
backend/alembic/         migrations
backend/tests/           unit, integration, security tests and fixtures
frontend/src/            Next.js app, components, lib
frontend/e2e/            Playwright tests
docs/                    architecture, plan, security, NIIT configuration
deploy/                  container stack and one-command installers
```

Next.js 16 has breaking changes from older versions. Before changing framework-level
frontend code, read `frontend/AGENTS.md` and the bundled docs in
`frontend/node_modules/next/dist/docs/`.

## Commands

```
# backend (from backend/)
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.worker          # crawl worker
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest

# frontend (from frontend/)
pnpm install
pnpm dev
pnpm lint && pnpm typecheck && pnpm build && pnpm test:e2e
```

## Non-negotiable principles

1. **The deterministic SEO engine must work without AI.** Crawling, rules, scoring and
   reports never depend on an AI provider being available.
2. **Never fabricate** SEO metrics, rankings, traffic, keyword volumes, backlinks or
   competitor data. When data is unavailable, show an empty state that says so.
3. **Every issue must include evidence and an actionable recommendation**: the affected
   URL, the observed value, the rule or threshold, and what to change.
4. **All organisation data is isolated and protected by backend authorisation.** Every
   tenant-owned query filters by `organisation_id`, access goes through the shared
   permission dependencies, and foreign resources return 404.
5. **The crawler implements SSRF protection and respects robots.txt** on every
   outbound request, including redirects and sitemaps.
6. **Never publish website changes without explicit human approval.** Phases 1 to 5
   produce drafts and reports only.
7. **Never store credentials in source code.** Use environment variables and keep
   `.env.example` to safe placeholders.
8. **No paid APIs or services** without explicit approval from the project owner.
9. **No mock data in production paths.** Fixtures and fakes belong in tests only.
10. **Preserve existing working functionality.** Run the full test suites before and
    after changes.
11. **Write tests for new functionality.** Routine tests use local fixtures and never
    contact live NIIT infrastructure.
12. **Update documentation** when architecture or behaviour changes.

Errors returned to users must stay generic; details go to logs. See `docs/SECURITY.md`.

## Development workflow

- Inspect existing code before modifying it, and extend existing modules rather than
  duplicating them.
- Implement one phase at a time, as listed in `docs/IMPLEMENTATION_PLAN.md`.
- Prefer small, reviewable changes: one concern per commit, imperative subject line,
  a body that explains why. Never commit to `main`.
- Run the relevant lint, type checks and tests after every modification, and fix
  errors before proceeding.
- Record unfinished work and known limitations in the implementation plan.
- Keep `README.md` and `docs/IMPLEMENTATION_PLAN.md` (including its feature status
  table) current.
- Document reasonable assumptions and proceed; ask only for decisions that change scope
  or need owner authorisation.
- End each phase with a report: files changed, features done, tests run and results,
  run commands, known limitations, next step.

## NIIT-specific requirements

- Do not invent institutional facts or claims.
- Treat official institutional information as verified only when it comes from
  approved content: the project's institutional profile and approved sources, entered
  by authorised users.
- Require human review for all content changes. Changes touching official claims,
  dates, eligibility, fees or admission requirements need a verified source as well.
- Preserve original content and maintain version history for every proposed change.
- Keep institutional configuration separate from generic application logic. NIIT is
  data (an organisation and its projects), never code paths in the engine.

## Commercialisation requirements

- Support multiple organisations and projects.
- Use provider interfaces for future integrations (AI, keywords, SERP, rankings,
  Search Console, analytics, CMS, notifications).
- Avoid hard-coded NIIT logic.
- Keep subscription and usage-limit architecture extensible; organisation-level limits
  such as crawl caps are the pattern to follow.
- Do not implement payment processing until authorised.

## Skills

| Skill | Use when |
|-------|----------|
| `/seo-audit` | Auditing a site or page and producing a prioritised findings report |
| `/fullstack-development` | Adding or changing backend, frontend or database code |
| `/security-review` | Reviewing a branch or pull request for security defects before merge |

## Ownership

Project owner: Office of the Principal, NIIT (principal@niit.edu.pk).
