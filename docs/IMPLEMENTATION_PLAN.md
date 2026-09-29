# Implementation Plan

Source brief: "NIIT AI SEO Agent: enterprise-grade, self-hosted, commercialisable
platform", supplied by the project owner on 2026-09-29.

## 1. Repository inspection (Phase 0)

| Item | Finding |
|------|---------|
| Existing application code | None. The repository held only `CLAUDE.md`, three Claude Code skills and a superseded draft plan. |
| Existing conventions | Working rules in `CLAUDE.md` (plan first, small commits, feature branches, no secrets, tests with every change). Kept. |
| Conflicts | The draft plan proposed a TypeScript backend. The brief prescribes Python/FastAPI. The draft was removed and `CLAUDE.md` updated. |
| Local toolchain (development container) | Python 3.12, uv, Node 22, pnpm 10, PostgreSQL 16, Docker. Ollama not installed. |
| Network | PyPI and npm reachable. `niit.edu.pk` is blocked by the development container's network policy, so no live crawl was possible. Not needed: tests use local fixtures. |

## 2. Assumptions

Documented per rule 12 of the brief. Each can be changed without redesign.

| # | Assumption |
|---|------------|
| A1 | Self-registration is disabled by default. The first platform administrator is created with a CLI command. |
| A2 | Only platform administrators create organisations in Phase 1. Self-service sign-up is a Phase 6 concern. |
| A3 | Logos are referenced by HTTPS URL in Phase 1. File upload with validation arrives with report branding in Phase 5. |
| A4 | NIIT's canonical website is `https://niit.edu.pk`. Authorised users can change it in project settings. |
| A5 | The Next.js server proxies `/api/v1` to FastAPI, giving one origin and first-party cookies. |
| A6 | Package managers: `uv` for Python, `pnpm` for Node. Both are free and fast; `pip` and `npm` also work. |
| A7 | Default AI model name is configurable and empty until Phase 4; no model is assumed. |

## 3. Prerequisites for local development

| Tool | Version | Needed from |
|------|---------|-------------|
| Python | 3.12 or newer | Phase 1 |
| uv (or pip) | recent | Phase 1 |
| Node.js | 20 or 22 LTS | Phase 1 |
| pnpm | 9 or newer | Phase 1 |
| PostgreSQL | 15 or 16, local or via Docker Compose | Phase 1 |
| Playwright Chromium | installed by `pnpm exec playwright install chromium` | Phase 1 (E2E), Phase 2 (rendering) |
| Ollama | recent, with one local model pulled | Phase 4 only |

## 4. Phases

Each phase ends with passing lint, type checks and tests, updated docs, and a phase
report (files, features, tests, commands, limitations, next step).

### Phase 0: Discovery and architecture (complete)

`docs/ARCHITECTURE.md`, this plan, `docs/SECURITY.md`, `docs/NIIT_CONFIGURATION.md`,
updated `CLAUDE.md` and skills.

### Phase 1: Foundation (complete)

Backend
- FastAPI app factory, settings via `pydantic-settings`, JSON logging, request IDs,
  consistent error handler, CORS allowlist, `/api/v1/health`.
- Async SQLAlchemy 2 with asyncpg, Alembic migration for users, refresh tokens,
  organisations, members, projects, project settings and audit logs.
- Auth: login, refresh with rotation and reuse detection, logout, `me`. Argon2id.
  Login rate limiting.
- Organisations: list mine, create (platform admin), read, update settings.
- Members: list, add existing user, change role, remove, with owner safeguards.
- Projects: list, create, read, update, soft delete; project settings read and
  update, validated by Pydantic.
- RBAC permission map and dependencies; 404 on cross-tenant access.
- Audit log entries for auth events and every create, update and delete.
- Provider interface stubs (`typing.Protocol`) for all providers in the brief.
- CLI: `create-admin`, `seed-niit` (creates the NIIT organisation and project with
  empty institutional profile for authorised users to complete).

Frontend
- Next.js App Router, Tailwind, shadcn/ui, TanStack Query, React Hook Form with Zod.
- Login page, authenticated layout with full navigation, organisation switcher.
- Overview with real counts from the API and empty states for crawl-dependent
  widgets. Projects list, create form, project detail and settings form.
- Organisation settings and member management pages.
- Unbuilt sections render "Not available yet" naming the delivering phase.

Tooling
- Ruff, mypy, pytest (unit, integration, security), ESLint, `tsc --noEmit`,
  Playwright E2E for login and project creation.
- Docker Compose for PostgreSQL (and Ollama under an optional profile).
- GitHub Actions CI running all of the above.

Exit criteria: fresh clone to running app using README commands only; cross-tenant
access tests pass; E2E login and create-project pass.

### Phase 2: Crawler (complete)

URL normalisation and validation, SSRF guard with IP pinning and per-hop
revalidation, robots.txt, sitemap discovery and parsing (including indexes and gzip),
breadth-first crawl with depth, page and concurrency limits, delay, timeout, size
cap, HTML extraction (title, meta, canonical, robots, headings, word count, images
and ALT, links, JSON-LD and microdata), content hashing, redirect chains, response
times, DB-backed job queue and worker, progress and cancellation, crawl explorer UI.
Tests against a local fixture site served by the test suite.

### Phase 3: SEO engine (complete)

Rule registry and all rules listed in section 7 of the brief, schema findings,
internal-link graph (in/out counts, orphans, over-linked pages, under-linked
important pages), duplicate and near-duplicate content, scoring, prioritisation
with explanations, issue lifecycle across crawls, issues and page dashboards.

Acceptance criteria from the project principles:
- Every issue carries evidence (affected URL, observed value, rule and threshold) and
  an actionable recommendation. The issue schema rejects findings missing either.
- Rules, scoring and prioritisation run with AI disabled and are covered by
  deterministic tests on local fixtures.
- No rule contains NIIT-specific logic; institution-specific behaviour comes from
  project settings such as important pages, page groups and content types.
- Scores are presented as site-health indicators, never as rankings or predictions.

### Phase 4: AI agent

`AIProvider` and `OllamaProvider`, health checks, typed agent tools, structured JSON
outputs with validation and retry, grounded summaries and recommendations, metadata
and content drafts, approval workflow (Draft, Pending Review, Approved, Rejected,
Published, Rolled Back) with version history. Drafts only; nothing is published.

### Phase 5: Reports and monitoring

HTML reports with the 13 sections in the brief, PDF export, crawl comparison,
historical charts, issue resolution tracking, management summaries, scheduled crawl
foundation (disabled by default).

### Phase 6: Commercial readiness

Multi-tenant verification suite, organisation branding and white-label reports,
plan and usage-limit architecture without payments, integration records with
encrypted credentials, deployment guide, production security review.

## 5. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| SSRF through the crawler | Internal network exposure | Dedicated URL safety module, IP pinning, per-hop checks, security tests (Phase 2) |
| Cross-tenant data leak | Severe for SaaS | `organisation_id` on every row, single authorisation dependency, isolation tests from Phase 1 |
| AI hallucination in drafts | Misleading institutional content | Grounded prompts, schema validation, human approval, no auto-publish |
| Overloading the NIIT site | Reputational | Conservative defaults (100 pages, depth 5, low concurrency, delay), robots.txt |
| Scope size | Delivery slips | Strict phase gates, each phase shippable on its own |
| In-process rate limiter | Ineffective across multiple API instances | Documented; replace with PostgreSQL or Redis store before scaling out |
| Ollama hardware needs | Slow or unavailable AI | AI is optional; small models documented; core works without it |
| No live-site access from the dev container | Cannot verify against real NIIT pages here | Fixture-based tests; owner runs first live crawl locally |

## 6. Recommended first milestone

Phase 1 foundation, delivered as backend first (models, migrations, auth, RBAC,
isolation tests), then the frontend shell against the real API. This proves
tenancy and security before any crawl data exists.

## 7. Feature status

| Area | Status |
|------|--------|
| Discovery documents | Done |
| Foundation (auth, organisations, projects, RBAC, dashboard shell) | Done |
| Crawler, crawl explorer and page browser | Done |
| SEO engine: rules, scoring, prioritisation, issues, SEO dashboards | Done |
| AI agent | Not started |
| Reports and monitoring | Not started |
| Commercial readiness | Not started |

## 8. Known limitations after Phase 1

| Limitation | Plan |
|------------|------|
| Login rate limiting is per process | Shared store before running several API instances |
| Sign-in events are not shown in organisation audit views | Platform audit view in Phase 6 |
| Members are added by email with an admin-set initial password; no invitation acceptance or forced password change | Invitations in Phase 6 |
| Logos are referenced by HTTPS URL; no upload | File upload with validation in Phase 5 |
| No user self-service profile page beyond the change-password API | Phase 6 |
| shadcn/ui components were written by hand because the component registry was not reachable from the build environment; `components.json` lets the CLI add more locally | None needed |
| `API_ORIGIN` is fixed at frontend build time | Documented; rebuild when the API address changes |
| Content types and page groups use a line-based editor | Richer editors when Phase 3 uses them |

## 9. Phase 1 report

Tests at completion of Phase 1:

| Suite | Result |
|-------|--------|
| Backend unit, integration and security tests (pytest) | 91 passed |
| Backend lint and types (ruff, mypy strict) | Clean |
| Frontend lint, types, production build | Clean |
| End-to-end (Playwright, Chromium) | 7 passed |
| Dependency audit (pip-audit, pnpm audit) | No known vulnerabilities |

## 10. Phase 2 report

Delivered: SSRF-guarded fetching, RFC 9309 robots.txt, sitemap and sitemap index
parsing, breadth-first crawling with page, depth, concurrency, timeout, delay and
duration limits, HTML extraction, content hashing, redirect chains, broken internal
links, orphan detection, incremental recrawls, a PostgreSQL-backed worker with
cancellation and recovery, crawl API endpoints, the Crawl Explorer, crawl results,
the Pages browser and page detail, and live crawl data on the Overview.

| Suite | Result |
|-------|--------|
| Backend unit, integration and security tests (pytest) | 171 passed |
| Backend lint and types (ruff, mypy strict), migration drift check | Clean |
| Frontend lint, types, production build | Clean |
| End-to-end (Playwright), including a full crawl of a local fixture site | 8 passed |

Defect found and fixed during Phase 2 end-to-end testing: the worker process did not
register every database model, so all page saves failed and the crawl appeared stuck.
Entry points now import all models, a test checks this, and storage failures now fail
the crawl instead of leaving it running.

### Known limitations after Phase 2

| Limitation | Plan |
|------------|------|
| JavaScript rendering is not available (security review needed for browser sub-requests) | Later phase, with request interception |
| External links are recorded but not checked | Optional, rate-limited external checks in a later phase |
| Pages found only in a sitemap are crawled but their links are not followed | By design, to keep crawls bounded |
| Orphans are not identified when a crawl hits its page limit | By design; raise the limit for a full picture |
| No automatic cleanup of old crawl data | Retention settings in Phase 5 |
| Plain-text sitemaps are not read | Add if a site needs it |

Recommended next step: Phase 3, the deterministic SEO rules engine, scoring and
prioritisation, using the observations Phase 2 now stores.

## 11. Phase 3 report

Delivered: 50 deterministic rules across technical, on-page, content, internal linking
and structured data; structured-data checks; near-duplicate detection; contextual
internal-link suggestions; configurable, explained scoring and prioritisation; issue
lifecycle across crawls with verified resolution and recurrence; triage (ignore and
reopen, audit-logged); automatic analysis after each crawl; the issues and results API;
and the SEO Audit, Issues, issue detail, Internal Linking and Structured Data pages,
with live scores on the Overview.

Phase 3 acceptance criteria:

| Criterion | How it is met |
|-----------|---------------|
| Every issue has evidence and a recommendation | Enforced by the `Finding` model; every rule has a test asserting both |
| Runs with AI disabled | No AI code in `app/modules/seo`; all tests run with `AI_PROVIDER=none` |
| No NIIT-specific logic | A test scans the engine source for institution names; NIIT behaviour comes from project settings |
| Scores are health indicators, not rankings | Stated in the score breakdown, the SEO Audit page and the docs |

| Suite | Result |
|-------|--------|
| Backend unit, integration and security tests (pytest) | 254 passed |
| Backend lint and types (ruff, mypy strict), migration drift check | Clean |
| Frontend lint, types, production build | Clean |
| End-to-end (Playwright), including crawl, analysis, issue review and triage | 9 passed |

Found and fixed during Phase 3: the first priority weights let a low-severity issue on
the home page tie with a high-severity error elsewhere. Severity steps now outweigh the
page-importance bonus, and a test locks this in.

### Known limitations after Phase 3

| Limitation | Plan |
|------------|------|
| Structured data checks cover common types only; microdata properties are not checked | Extend as sites need it |
| Link suggestions need an exact mention of the target's H1 or title phrase | Deliberately conservative; AI-assisted suggestions in Phase 4 stay evidence-based |
| Changing thresholds and re-running analysis can resolve issues that a stricter rule raised | Documented; the audit log records re-runs |
| Crawls made before Phase 3 have no stored page text, so near-duplicate and link-suggestion checks skip them | Re-crawl |
| Score history is stored but not charted | Monitoring in Phase 5 |
| Response-time checks use one sample from the crawler's location, not Core Web Vitals | Field data needs an approved provider (Search Console) later |

Recommended next step: Phase 4, the AI agent. Ollama integration behind the provider
interface, typed agent tools over the issues and pages now stored, grounded
explanations and drafts for metadata and content, and the approval workflow.
