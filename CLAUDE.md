# NIIT AI SEO Agent

Self-hosted SEO management platform, first deployed for the NASTP Institute of
Information Technology (NIIT) and designed to become a multi-tenant SaaS product.
It crawls sites, runs a deterministic SEO rules engine, scores and prioritises
issues, and uses AI (Ollama first) only as an optional layer for explanations and
drafts.

Read before non-trivial work: `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`
(phases and feature status), `docs/SECURITY.md`, `docs/NIIT_CONFIGURATION.md`.

## Stack

- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg),
  Alembic, PostgreSQL, Argon2id, JWT. Package manager `uv`.
- Frontend: Next.js App Router, TypeScript strict, Tailwind, shadcn/ui, TanStack
  Query, React Hook Form + Zod, Recharts. Package manager `pnpm`.
- Crawling: httpx, selectolax, lxml, Playwright (opt-in). AI: Ollama via a provider
  interface.

## Layout

```
backend/app/core/        config, logging, db, security, errors
backend/app/modules/     one folder per module: models, schemas, service, router
backend/app/providers/   provider interfaces (AI, keywords, CMS, ...)
backend/alembic/         migrations
backend/tests/           unit, integration, security tests
frontend/src/            Next.js app, components, lib
frontend/e2e/            Playwright tests
docs/                    architecture, plan, security, NIIT configuration
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
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest

# frontend (from frontend/)
pnpm install
pnpm dev
pnpm lint && pnpm typecheck && pnpm build && pnpm test:e2e
```

## Non-negotiable rules

- **No fabricated data.** Never invent SEO metrics, keyword volumes, rankings,
  traffic, backlinks, competitor data or NIIT facts. Show empty states instead.
- **Deterministic core.** Crawling, rules, scoring and reports must work with AI off.
- **Tenant isolation.** Every tenant-owned query filters by `organisation_id`.
  Authorisation happens in the backend through the shared permission dependency.
  Foreign resources return 404.
- **No NIIT logic in the engine.** Institution-specific behaviour is configuration.
- **No publishing or external actions** (CMS writes, emails, paid APIs) without
  explicit owner authorisation. Phase 1 to 5 produce drafts and reports only.
- **Security.** SSRF guard on every outbound crawler request. No secrets in code.
  Generic error responses. See `docs/SECURITY.md`.
- **Tests.** Every behaviour change ships with tests. Routine tests never hit live
  NIIT infrastructure; use local fixtures.

## Working rules

- Work phase by phase as listed in `docs/IMPLEMENTATION_PLAN.md`. Update its feature
  status table when a phase changes state.
- Small commits, imperative subject lines, explain why. Never commit to `main`.
- Run lint, type checks and tests before each commit. Fix failures before moving on.
- Document reasonable assumptions in the plan and proceed; ask only for decisions
  that change scope or need owner authorisation.
- End each phase with a report: files changed, features done, tests run and results,
  run commands, known limitations, next step.

## Skills

| Skill | Use when |
|-------|----------|
| `/seo-audit` | Auditing a site or page and producing a prioritised findings report |
| `/fullstack-development` | Adding or changing backend, frontend or database code |
| `/security-review` | Reviewing a branch or pull request for security defects before merge |

## Ownership

Project owner: Office of the Principal, NIIT (principal@niit.edu.pk).
