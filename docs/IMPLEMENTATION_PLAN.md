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
| A2 | Only platform administrators create organisations in Phase 1. Self-service sign-up is deferred: it needs email verification and owner approval for commercial launch. |
| A3 | Logos are referenced by HTTPS URL. Reports fetch the logo once through the SSRF guard and embed it, so no upload store is needed. Upload was not needed in Phase 6. |
| A4 | NIIT's canonical website is `https://niit.edu.pk`. Authorised users can change it in project settings. |
| A5 | The Next.js server proxies `/api/v1` to FastAPI, giving one origin and first-party cookies. |
| A6 | Package managers: `uv` for Python, `pnpm` for Node. Both are free and fast; `pip` and `npm` also work. |
| A7 | Default AI model name is configurable and empty until Phase 4; no model is assumed. |
| A8 | AI runs only when both the platform (`AI_PROVIDER=ollama`) and the organisation turn it on. NIIT starts with AI off. |
| A9 | Approving a draft needs two people: the author or submitter of a version cannot approve it. The submitter of an AI draft counts as its author. |
| A10 | "Published" and "rolled back" are records of what a person did in the CMS. No CMS connection exists until the owner authorises one (Phase 6). |
| A11 | Any draft that adds, changes or removes a money amount, percentage, date, year or grade, or mentions fees, eligibility, deadlines or similar, is treated as touching official facts and needs a verified source to be approved. |
| A12 | A report always covers the latest analysed crawl at the time it is requested, and is stored as a snapshot. Issue statuses in it are as recorded at generation time. |
| A13 | PDF export is optional: it needs Chromium through Playwright on the server. Without it, reports are HTML (printable to PDF from a browser) and the PDF is marked unavailable. |
| A14 | Scheduled crawls need two switches: `SCHEDULER_ENABLED` on the server and the project's own schedule. Both are off by default, and NIIT has no schedule. |
| A15 | Plans are data, not offers. The seeded `internal` plan is the default and has no limits; the seeded `starter` and `professional` plans carry example numbers for the owner to replace before any commercial use. There is no payment processing. |
| A16 | Monthly and daily usage limits use UTC calendar periods. |
| A17 | Integrations are records only until the owner authorises a connection. Credentials can be stored only when the operator sets an encryption key outside the database. |
| A18 | Data retention is off by default and only owners can turn it on. The minimums are 2 kept crawls and 30 days for reports. It runs hourly in the worker. |
| A19 | Emails are not verified (no email provider is approved), so only platform administrators can add an account that already exists to an organisation. Since October 2026, organisation administrators invite such accounts instead, and the account's owner accepts by signing in. |
| A20 | White-label reports replace the organisation's name with a display name and add a cover note; colour, footer and logo come from Phase 5 branding. |

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

### Phase 4: AI agent (complete)

`AIProvider` and `OllamaProvider`, health checks, typed agent tools, structured JSON
outputs with validation and retry, grounded summaries and recommendations, metadata
and content drafts, approval workflow (Draft, Pending Review, Approved, Rejected,
Published, Rolled Back) with version history. Drafts only; nothing is published.
See section 12 for the report.

### Phase 5: Reports and monitoring (complete)

HTML reports with the 13 sections in the brief, PDF export, crawl comparison,
historical charts, issue resolution tracking, management summaries, scheduled crawl
foundation (disabled by default). See section 13 for the report.

### Phase 6: Commercial readiness (complete)

Multi-tenant verification suite, organisation branding and white-label reports,
plan and usage-limit architecture without payments, integration records with
encrypted credentials, data retention, platform audit log and admin commands,
deployment guide, production security review. See section 14 for the report.

## 5. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| SSRF through the crawler | Internal network exposure | Dedicated URL safety module, IP pinning, per-hop checks, security tests (Phase 2) |
| Cross-tenant data leak | Severe for SaaS | `organisation_id` on every row, single authorisation dependency, isolation tests from Phase 1 |
| AI hallucination in drafts | Misleading institutional content | Grounded prompts, schema validation, grounding checks that reject invented numbers and claims, protected-fact detection, two-person approval, no auto-publish |
| Overloading the NIIT site | Reputational | Conservative defaults (100 pages, depth 5, low concurrency, delay), robots.txt |
| Scope size | Delivery slips | Strict phase gates, each phase shippable on its own |
| In-process rate limiter | Ineffective across multiple API instances | Documented; replace with PostgreSQL or Redis store before scaling out |
| Ollama hardware needs | Slow or unavailable AI | AI is optional; small models documented; core works without it |
| Provider not yet tried with a real model | Real models may fail schema or grounding checks more often than the tests assume | Failures are safe (nothing saved); validate with the chosen model before enabling AI for NIIT (see section 12) |
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
| AI agent: provider, tools, grounded tasks, recommendations, drafts and approvals | Done (not yet validated against a live Ollama model; see section 12) |
| Reports and monitoring: 13-section reports, PDF export, score history, crawl comparison, schedule foundation | Done |
| Interface uplift: animated sign-in, grouped navigation, interactive tiles and tabs, data-drawn page thumbnails, search-result previews | Done |
| Invitations and password reset by email (own SMTP server, optional) | Done |
| Commercial readiness: tenant verification suite, plans and usage limits, integration records with encrypted credentials, white-label reports, retention, platform audit, deployment guide, security review | Done |

## 8. Known limitations after Phase 1

| Limitation | Plan |
|------------|------|
| Login rate limiting is per process | Shared store before running several API instances |
| Sign-in events are not shown in organisation audit views | Done: platform audit view (Phase 6) |
| Members are added by email with an admin-set initial password; no invitation acceptance or forced password change | Invitations need an approved email provider; until then only platform administrators attach existing accounts (Phase 6) |
| Logos are referenced by HTTPS URL; no upload | Reports embed the logo through the SSRF guard (Phase 5); no upload needed so far |
| No user self-service profile page beyond the change-password API | Still open after Phase 6; with the interface uplift |
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
| No automatic cleanup of old crawl data | Done: retention settings (Phase 6) |
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
| Score history is stored but not charted | Done: Monitoring page (Phase 5) |
| Response-time checks use one sample from the crawler's location, not Core Web Vitals | Field data needs an approved provider (Search Console) later |

Recommended next step: Phase 4, the AI agent. Ollama integration behind the provider
interface, typed agent tools over the issues and pages now stored, grounded
explanations and drafts for metadata and content, and the approval workflow.

## 12. Phase 4 report

Delivered:
- An Ollama provider behind the `AIProvider` interface: schema-constrained JSON,
  validation with one retry, and a health check that reports a missing model.
- Platform and organisation switches for AI. NIIT starts with AI off.
- Nine typed, read-only, project-scoped tools, and a bounded question-answering loop.
- Five tasks:
  - management summary;
  - issue explanation, which creates a recommendation;
  - page improvement plan, which creates recommendations;
  - title and description drafts;
  - content outline draft, with `[verify: ...]` markers for facts that need confirming.
- Grounding checks with one retry. An ungrounded reply is never saved.
- A deterministic crawl comparison, also available at `GET /projects/{id}/compare`.
- Recommendations that users can accept or dismiss.
- Drafts from people or the AI, with version history, the approval workflow, separation
  of duties, protected-fact detection, a full approval trail and audit logging.
- Dashboard pages: AI Recommendations, Content Opportunities, Approvals and draft
  review, plus "Explain with AI" on issues and AI drafting on crawled pages.

Phase 4 acceptance criteria:

| Criterion | How it is met |
|-----------|---------------|
| Core works with AI off | AI is off by default; the engine never calls it; with AI off, requests return 409 `ai_disabled` and the screens explain why; tested |
| Structured, validated output with retry | Pydantic schemas passed to Ollama as `format`; invalid JSON is retried once with the errors, then the task fails; tested against a fake server |
| Grounded, no fabricated metrics | Invented numbers, unknown issue ids and ranking, traffic, search-volume, backlink or guarantee claims are rejected after one retry; tested for each |
| Agent tools are typed, scoped and bounded | Argument models, allow-list, project and organisation filters, at most four tool calls; isolation and loop tests |
| Approval workflow with version history | Six states, only defined transitions, versions and trail stored; API and E2E tests |
| Nothing is published | No code writes to a website; "published" is a record, and the UI says so |
| Human review for institutional content | Two-person approval; protected facts need a verified source reference; tested in API and E2E |
| Tenant isolation | Analyses, recommendations, drafts and tools return 404 or refuse across organisations; security tests |

| Suite | Result |
|-------|--------|
| Backend unit, integration and security tests (pytest) | 288 passed |
| Backend lint and types (ruff, mypy strict), migration drift check | Clean |
| Frontend lint, types, production build | Clean |
| End-to-end (Playwright), including an AI draft approved by a second person, marked published, and a protected human draft needing a source | 11 passed |

Found and fixed during Phase 4:
- The ORM could insert an approval-trail row before its draft, because the two are
  not linked by a relationship. The draft is now flushed first.
- AI drafts have no human author, so the person who submitted one could also approve
  it. The submitter of a version is now barred as well.
- Human drafts accepted any public URL. They must now be on the project's site.
- A long question could outlive the stale-task window and be failed while healthy.
  The window now covers the worst-case number of model calls.

How AI was tested: Ollama and its model registry cannot be reached from the build
environment. The provider was written against Ollama's documented `/api/chat` and
`/api/tags` endpoints. It was tested only against `backend/tests/fixtures/fake_ollama.py`,
a local stand-in that returns scripted replies, or replies built from the prompt's own
evidence. **It has not been run against a real model.** Before enabling AI for NIIT:
1. Install Ollama and pull a model (`ollama pull llama3.1`).
2. Set `AI_PROVIDER=ollama` and `OLLAMA_DEFAULT_MODEL`.
3. Turn AI on in organisation settings.
4. Run each task on the NIIT project, and check the grounding pass rate and the
   quality of the drafts.

### Known limitations after Phase 4

| Limitation | Plan |
|------------|------|
| Not validated against a live Ollama model | Owner validation step above before enabling AI for NIIT |
| Grounding checks are pattern-based and English-oriented; they catch invented numbers and listed claim types, not every false statement | Human approval remains mandatory; extend patterns as real output is reviewed |
| Protected-fact detection is keyword-based and English-only | Reviewers see the reasons; extend per language when needed |
| One organisation member cannot approve their own drafts, so a one-person organisation cannot approve anything | By design; add a second member with an approving role |
| AI tasks are processed one at a time per worker; a slow model delays the queue | Run more workers, or a faster model |
| Draft evidence links to issues by id; resolved issues still link but may no longer be current | Shown with their status on the issue page |
| No streaming of AI output; results appear when the task completes | Acceptable for background tasks |

Recommended next step: Phase 5, reports and monitoring. HTML and PDF management
reports using the deterministic results and, where enabled, the grounded management
summary; score history charts; crawl comparison views over the comparison already
built; and the scheduled-crawl foundation, off by default.

## 13. Phase 5 report

Delivered:
- **Management reports** with the 13 sections of the brief:
  1. Executive summary
  2. Overall SEO health
  3. Crawl overview, with changes since the previous crawl
  4. Critical issues
  5. High-priority issues
  6. Technical SEO
  7. On-page SEO
  8. Content quality
  9. Internal linking
  10. Structured data
  11. AI recommendations
  12. Recommended action plan
  13. Methodology and limitations

  Every report states the crawl date and the number of pages analysed, and shows the
  evidence and affected URLs for each finding. The executive summary and action plan
  are written by fixed rules, so reports are complete with AI off. The AI section is
  optional and labelled.
- **Organisation branding**: primary colour, footer text and logo. The logo is fetched
  through the SSRF guard and embedded.
- **PDF export** through optional Chromium: A4 pages with a footer and page numbers,
  printed offline with JavaScript off and every request refused.
- **Storage and generation**: reports are stored as snapshots and generated by the
  worker. People can list, view, download and delete them, with permissions, limits
  and audit logging.
- **Monitoring page**: score history chart with a table view, and a comparison of any
  two analysed crawls. It shows:
  - score changes;
  - new, verified-resolved and recurring issues;
  - page status, title, description, redirect, content and internal-link changes.
- **Scheduled crawl foundation**: daily, weekly or monthly at an hour in the
  organisation's time zone. It is off on both the server and the project by default,
  missed runs are skipped, and no run starts while a crawl is active.

Phase 5 acceptance criteria:

| Criterion | How it is met |
|-----------|---------------|
| Reports identify the crawl date and pages analysed | Cover facts and executive summary; tested |
| Findings include evidence and affected URLs | Every issue card in sections 4 to 10; tested against the fixture site |
| Professional, neutral language; branding | Rule-written text, organisation colour, footer and logo; reviewed as rendered HTML and PDF |
| Reports work without AI | Executive summary and action plan never use AI; a report with AI excluded is tested |
| Resolved only after a verifying crawl | Comparison and reports use the Phase 3 issue lifecycle; stated in both |
| Scheduling configurable and off by default | Two switches, both default off; worker step tested with each off and on |
| Tenant isolation | Reports and schedules from another organisation return 404; security test |

| Suite | Result |
|-------|--------|
| Backend unit, integration and security tests (pytest) | 303 passed, including real PDF rendering and a no-network PDF test |
| Backend lint and types (ruff, mypy strict), migration drift check | Clean |
| Frontend lint, types, production build | Clean |
| End-to-end (Playwright), now including report generation and viewing, a second crawl feeding the comparison, and schedule settings | 12 passed |

Found and fixed during Phase 5:
- Time zones failed to validate on Windows, which has no system time zone database.
  `tzdata` was added, with a test that hides the system database.
- Some Ollama versions silently truncate long prompts, so the context window is now
  set explicitly (`AI_CONTEXT_TOKENS`).
- Site-wide issues in reports said "first 1 of 17 URLs"; they now show one example URL.
- Report fact labels split across PDF pages; each label now stays with its value.
- Two crawls on the same day produced identical chart labels; the time is now added.

### Known limitations after Phase 5

| Limitation | Plan |
|------------|------|
| PDF export needs Chromium installed on the server (`uv run playwright install chromium`) | Documented; HTML reports and browser printing work without it |
| No automatic retention or cleanup of old crawls and reports | Done: retention settings (Phase 6) |
| Scheduled crawls run from the worker's periodic check, so they can start up to about a minute late | Acceptable for daily to monthly schedules |
| A scheduled run is skipped, not delayed, if a crawl is already active at that time | Documented in the schedule card |
| Report history per project is a list; there is no side-by-side comparison of two reports | Crawl comparison on the Monitoring page covers the need |
| Notifications (report ready, critical issue detected) are preferences only; nothing is sent | Needs an approved notification provider (Phase 6, owner authorisation for any paid service) |

Recommended next step: Phase 6, commercial readiness:
- a multi-tenant verification suite;
- white-label reports, building on the branding added here;
- plan and usage-limit architecture, without payments;
- integration records with encrypted credentials;
- data retention;
- a deployment guide;
- a production security review.

## 14. Phase 6 report

Delivered:
- **Multi-tenant verification suite** (`tests/security/test_tenant_matrix.py`). It walks
  every route in the OpenAPI schema, creates the resource in one organisation, and calls
  it as an owner of another. It expects 404 with no data change. It also checks that
  platform administrators have no project access and that global routes need an
  administrator. It found one route that returned 422 before its access check; fixed.
- **Plans and usage limits, without payments**:
  - Limits cover projects, members, pages per crawl, crawls a month, AI tasks a day
    and reports a month.
  - They are enforced at every usage point, including scheduled crawls, under a
    per-organisation lock. Blocked requests get a clear message (409
    `plan_limit_reached`).
  - Platform administrators create and assign plans. Owners see their usage under
    Administration.
- **Integration records** for Search Console, Analytics, WordPress, SMTP and webhooks:
  - Settings are validated per provider. Credentials are encrypted with Fernet keys held
    outside the database, are never returned, and can be rotated with a CLI command.
  - Nothing connects to these services, and the screen says so.
- **White-label reports**: a display name and a cover note.
- **Data retention**: off by default and owner-only. It removes page-level data of older
  crawls and deletes old reports. History, scores and the latest analysed crawl are
  always kept. Every run is audit-logged.
- **Platform administration**:
  - a platform-wide audit log, including sign-ins;
  - CLI `reset-password`, which ends the account's sessions;
  - CLI `rotate-secrets`.
- **Deployment guide** (`docs/DEPLOYMENT.md`) for a single Windows machine (for example
  a GPU laptop) and a Linux server with nginx, TLS and systemd. It covers:
  - secrets;
  - Ollama with a GPU;
  - PDF rendering;
  - backups and restore;
  - upgrades;
  - key rotation;
  - operations.
- **Production security review** (`docs/SECURITY_REVIEW.md`). It found 1 high,
  8 medium, 13 low and 4 informational findings. All high and medium findings are fixed,
  and every fix has a regression test. Two items are accepted with documented residual
  risk. Verdict: clear to deploy.

Phase 6 acceptance criteria:

| Criterion | How it is met |
|-----------|---------------|
| Every organisation's data isolated by backend authorisation | Route-walking suite over every API route, plus the module isolation tests |
| Usage-limit architecture extensible, no payments | Plans are data; one `enforce()` hook per usage point; no payment code |
| Credentials never in source or responses | Encrypted with operator-held keys; write-only API; tests read the raw column |
| No paid service or connection without approval | Integrations are records only; the UI and docs say so |
| Deployable by the institute | Deployment guide for Windows and Linux; production start-up checks |
| No known high or medium security issue | Security review with fixes and tests |

| Suite | Result |
|-------|--------|
| Backend unit, integration and security tests (pytest) | 339 passed, including real PDF rendering |
| Backend lint and types (ruff, mypy strict), migration drift check | Clean |
| Frontend lint, types, production build | Clean |
| End-to-end (Playwright): every navigation section, plans and platform audit, integrations, the sign-in redirect and the content security policy | 15 passed |

Found and fixed during Phase 6: see `docs/SECURITY_REVIEW.md`. The most important was
account pre-hijacking across organisations (H1).

### Known limitations after Phase 6

| Limitation | Plan |
|------------|------|
| Invitations, forced first-sign-in password change and email verification need an email provider | After the owner approves a provider |
| Organisation admins can learn that an email has an account | Removed with invitations |
| Integrations are records only; nothing connects to Search Console, Analytics, the CMS or email | Each connection after owner authorisation |
| Login rate limiting is per process | Single API process documented; shared store before scaling out |
| Seeded `starter` and `professional` plans hold example numbers | Owner sets real numbers before commercial use |
| The dashboard's CSP allows inline scripts | A nonce- or hash-based policy later |
| Access tokens stay valid for up to 15 minutes after a password reset | Per-user token version later |
| AI not yet validated against a live Ollama model on the owner's hardware | Owner validation (section 12) on the GPU laptop |
| No profile page for users; notifications are preferences only | Profile page with the interface uplift; notifications need an approved provider |

Recommended next step: the interface uplift the owner asked for:
- interactive screens with tabs, tiles and live thumbnails;
- a new sign-in screen with a high-quality, animated AI-and-SEO visual.

It must keep the same data rules (no invented numbers, honest empty states), keep
accessibility (reduced motion, keyboard, contrast), and keep every test passing.

## 15. Interface uplift (after Phase 6)

Requested by the owner: interactive screens with tabs, tiles and dynamic thumbnails, and
a sign-in screen with a high-quality animation about AI-based SEO.

Delivered:
- **Sign-in**:
  - a split layout with an animated vector scene: a crawler scanning a page, a rules
    check list, a local AI core, and an AI draft awaiting human approval;
  - a show-characters toggle for the password;
  - a mobile layout.
- **Navigation**: the sidebar is grouped into Workspace, Analyse, Improve, Track and
  Manage, with the brand mark and an active-page indicator. The top bar shows the
  person's initials.
- **Overview**:
  - a hero banner with the live overall score ring and quick actions;
  - tiles that link to the screen behind each number;
  - open-issue tiles per severity that open the filtered Issues list for that project;
  - workspace tabs: module launch tiles, the score trend, and recent reports.
- **Pages**:
  - a thumbnail on every row;
  - a Gallery tab of thumbnail cards;
  - a legend that explains how thumbnails are drawn.
- **Page detail**: a thumbnail and a search-result preview. Details are split into
  Overview, Content, Structured data and Links tabs.
- **Projects**: tiles with a per-project colour and the live health score, or a table.

Design rules kept:
- No invented figures. Every number comes from the API, and missing data says so.
- Thumbnails are drawings of crawl data, labelled as such. Pages are never
  screenshotted, because rendering pages in a browser is deferred for SSRF reasons.
- Every image is a local vector, so the Content Security Policy is unchanged.
- The tabs follow the WAI-ARIA pattern. The tiles are real links with visible focus.
  Motion stops under reduced-motion settings.

Assumption A21: the illustration contains no figures or claims, only generic
shapes and the labels Crawl, Analyse, AI draft and Human approval. This way it cannot
misstate the product or the institute.

| Suite | Result |
|-------|--------|
| Frontend lint, types, production build | Clean |
| End-to-end (Playwright), now covering the gallery tab, keyboard tab navigation on page detail, workspace tabs and tiles on the overview, and reduced motion on sign-in | 16 passed |

### Known limitations after the uplift

| Limitation | Plan |
|------------|------|
| Thumbnails are schematic, not screenshots | Real screenshots need browser rendering behind the SSRF guard (deferred) |
| No manual light/dark switch; the theme follows the system setting | Add a toggle if people ask for it |
| No profile page yet | Next interface step |

## 16. Closing the technical gaps (after Phase 6)

The owner asked to close four gaps, all with free and self-hosted means only:

| Gap | Status |
|-----|--------|
| Invitations and password reset by email | Done (16.1) |
| Google Search Console data, using the customer's own free Google client | Pending |
| JavaScript site rendering behind the SSRF guard | Pending |
| Configurable product name and a one-command installer | Pending |

Added by the owner: improve the AI assistant's accuracy and speed with free, local
means. Step 1 (measure) is done (16.2); steps 2 and 3 follow.

### 16.1 Invitations and password reset

Delivered:
- **Invitations** (`modules/invitations/`, migration 0009). Owners and admins invite an
  email address with a role from Administration. The pending list shows each invitation
  with its expiry and a cancel action. A new invitation for the same address replaces the
  old one.
- **Accepting** on the public `/invite` page:
  - a new person creates their account and chooses their own password;
  - someone who already has an account signs in as that account and joins;
  - a different signed-in account is told to sign out.
- **Password reset** from "Forgot password?" on the sign-in page: `/forgot-password`
  sends a link, and `/reset-password` sets the new password and ends every session.
- **Email** (`core/mailer.py`) goes through the operator's own SMTP server. It is
  optional. Without it, the invitation link is shown once to the administrator to share,
  and the forgot-password page says to ask an administrator.
- The direct "add a member" form stays for sites without email. Its account-exists
  message now points to invitations.

Assumption A22: the operator's existing organisational mail server is not a paid
third-party service, so using it needs no further approval. No email provider is
bundled.

| Suite | Result |
|-------|--------|
| Backend (ruff, mypy, pytest, including 10 new invitation and reset tests and invitations in the tenant matrix) | 360 passed |
| Frontend lint, types | Clean |
| End-to-end (Playwright), now covering invite and accept, and reset pages without email | 18 passed |

Known limitations:

| Limitation | Plan |
|------------|------|
| Reset request limits are in-process, like login limits | A shared store before running more than one API process |
| Access tokens stay valid for up to 15 minutes after a reset | Per-user token version (security review recommendation 4) |
| Emails are plain text and English only | HTML templates and languages when needed |

### 16.2 Measuring the AI assistant (AI step 1)

The owner asked how to make the AI agent more accurate and faster. The plan, in order:
1. measure;
2. trim prompts and compute facts in code, add worked examples and more useful retries;
3. fetch data before the model starts, use native tool calling, and add feedback buttons;
4. later, lookup of approved content.

Step 1 delivered:
- **Model kept loaded.** Every request sends `keep_alive` (`AI_KEEP_ALIVE`, default 30
  minutes), so only the first task after a quiet period waits for the model to load.
- **Run metrics.** Each AI task stores what Ollama reported: model calls, load time,
  prompt and output tokens, and model time (migration 0010). They are kept for failed
  tasks too, and a task that failed on invalid replies now records its real number of
  attempts. Results show a "Run details" line.
- **`ai-report`.** Per task type: totals, success, model calls, median seconds,
  average prompt size, cold starts, models used, and the most common failure reasons.
- **`ai-eval`.** Runs a starter test set of 10 cases (management summary, top issue
  explanation, eight questions including two the platform has no data for) like real
  tasks, without saving anything, and scores each one. `--model` compares models and
  `--out` saves the results, including every answer in full and the titles of the issues
  it cites, so people can judge quality and compare runs. Each case also prints a short
  preview of its answer.

First run on the owner's laptop (NIIT website, qwen2.5:7b): 10 of 10 cases passed,
all completed and grounded, median 1.7 s per case, average prompt 3,083 tokens.

Reading the saved answers showed that score was wrong. All eight questions had received
the same reply, "The project data does not contain an answer to this question". The
model had chosen to answer but left the answer text empty, and the agent filled in that
stock sentence. The checks were fooled twice:
- the cited issues satisfied "cites the top issues";
- the stock sentence satisfied "admits missing data".

Fixed:
- `answer` is required in the schema Ollama must follow.
- An answer step without text fails validation, so it goes back to the model with the
  error. A second empty reply fails the task honestly.
- No stock answer is ever substituted.
- The test set gained an `answers` check: questions the data always answers fail on a bare
  "no answer" reply.
- `PROMPT_VERSION` is now 2026-10.1.

On the owner's laptop (RTX 4060, 8 GB), Ollama was also set up with flash attention, a
q8_0 KV cache and a 30-minute keep-alive, and confirmed at 100% GPU.

Assumption A23: the "admits missing data" check matches common phrasings such as "not
available" or "does not have". It confirms the answer admits the gap. The grounding
check separately rejects any number that is not in the data.

| Suite | Result |
|-------|--------|
| Backend (ruff, mypy, pytest with new provider, metrics, report and evaluation tests) | 368 passed |
| Frontend lint, types | Clean |
| End-to-end (Playwright), now checking the run details line | 18 passed |

Known limitations:

| Limitation | Plan |
|------------|------|
| The starter cases are generic; project-specific expectations need a custom cases file | Add NIIT cases once the baseline is known |
| Automatic checks cover structure (completed, grounded, right issues cited, missing data admitted), not how useful the wording is | People read the saved answers; feedback buttons come in step 3 |
| Evaluation runs one case at a time on one model | Enough for a single GPU |
| Run details are not yet shown as a dashboard chart | `ai-report` covers it for now |
