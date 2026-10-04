# Phases

The platform was built in seven phases, 0 to 6, each shippable on its own. After
Phase 6, an interface uplift and a set of owner requests closed the main technical
gaps. This page is a short overview. The detailed record, with assumptions, test
results, defects found and every known limitation, is
[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

The rule from `CLAUDE.md`: implement one phase at a time, and finish it before
starting the next.

## Summary

| Phase | Name | Goal | Status | Key deliverables | Main modules and folders | Migrations |
|-------|------|------|--------|------------------|--------------------------|------------|
| 0 | Discovery and architecture | Agree the design before any code | Complete | Architecture, plan, security and NIIT documents | `docs/` | None |
| 1 | Foundation | Prove tenancy and security first | Complete | Auth, organisations, projects, RBAC, dashboard shell | `core/`, `auth`, `users`, `organisations`, `projects`, `audit_logs`, `providers/` | 0001 |
| 2 | Crawler | Collect site data safely | Complete | SSRF-guarded crawler, worker, Crawl Explorer | `crawler`, `worker.py` | 0002 |
| 3 | SEO engine | Turn crawl data into evidenced issues | Complete | 50 rules, scoring, issue lifecycle, SEO pages | `seo` | 0003 |
| 4 | AI agent | Optional grounded explanations and drafts | Complete | Ollama provider, agent tools, drafts and approvals | `ai`, `drafts` | 0004 |
| 5 | Reports and monitoring | Reports and change over time | Complete | 13-section reports, PDF, score history, schedules | `reports`, `monitoring` | 0005 |
| 6 | Commercial readiness | Ready for several organisations | Complete | Tenant suite, plans, integrations, retention, security review | `plans`, `integrations`, `monitoring/retention.py` | 0006, 0007, 0008 |

Module names are folders under `backend/app/modules/` unless a path is given. Later
work added migrations 0009 to 0013 (see [After Phase 6](#after-phase-6)).

## Phase 0: Discovery and architecture

Goal: inspect the repository, settle the stack and record assumptions.

Delivered:
- `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/SECURITY.md` and
  `docs/NIIT_CONFIGURATION.md`.
- An updated `CLAUDE.md` and skills. A superseded draft plan with a TypeScript backend
  was removed in favour of FastAPI.
- The assumptions table (A1 onwards), kept current in the plan.

Still open: none specific to this phase.

Detail: plan sections 1 to 6, starting at
[Repository inspection](IMPLEMENTATION_PLAN.md#1-repository-inspection-phase-0).

## Phase 1: Foundation

Goal: a running, secure multi-tenant shell before any crawl data exists.

Delivered:
- FastAPI app with settings, JSON logging, request IDs, error handling and health check.
- Authentication with Argon2id, rotating refresh tokens with reuse detection, and login
  rate limiting.
- Organisations, members, projects and project settings, with RBAC and 404 on
  cross-tenant access.
- Audit log entries for auth events and every change.
- Provider interface stubs for every integration in the brief.
- CLI `create-admin` and `seed-niit`.
- Next.js dashboard shell, CI, Docker Compose for PostgreSQL, Playwright tests.

Still open:
- Login rate limiting is per process. A shared store is needed before running several
  API instances.
- No profile page for users beyond the change-password API.
- `API_ORIGIN` is fixed at frontend build time; rebuild when it changes.
- Logos are referenced by HTTPS URL; there is no upload (none needed so far).

Detail: [Phase 1](IMPLEMENTATION_PLAN.md#phase-1-foundation-complete),
[known limitations](IMPLEMENTATION_PLAN.md#8-known-limitations-after-phase-1) and
[report](IMPLEMENTATION_PLAN.md#9-phase-1-report) (sections 4, 8 and 9).

## Phase 2: Crawler

Goal: crawl a site without risk to internal networks or the site itself.

Delivered:
- SSRF guard with IP pinning and checks on every redirect hop.
- robots.txt (RFC 9309), sitemaps and sitemap indexes, including gzip.
- Breadth-first crawling with page, depth, concurrency, delay, timeout and size limits.
- HTML extraction, content hashing, redirect chains, broken internal links, orphans.
- A PostgreSQL-backed worker with cancellation and recovery.
- Crawl Explorer, crawl results and the Pages browser.

Still open:
- External links are recorded but not checked.
- Plain-text sitemaps are not read.
- By design: pages found only in a sitemap are crawled but their links are not
  followed, and orphans are not identified when a crawl hits its page limit.

Closed later: JavaScript rendering (16.6) and cleanup of old crawl data (Phase 6).

Detail: [Phase 2 report](IMPLEMENTATION_PLAN.md#10-phase-2-report) (section 10).

## Phase 3: SEO engine

Goal: deterministic rules that work without AI, with evidence for every issue.

Delivered:
- 50 rules across technical, on-page, content, internal linking and structured data.
- Near-duplicate detection and contextual internal-link suggestions.
- Explained scoring and prioritisation, presented as health indicators, not rankings.
- Issue lifecycle across crawls: verified resolution, recurrence, ignore and reopen.
- SEO Audit, Issues, Internal Linking and Structured Data pages.

Still open:
- Structured data checks cover common types only; microdata properties are not checked.
- Response-time checks use one sample from the crawler's location, not Core Web Vitals.
- Link suggestions need an exact mention of the target's H1 or title (deliberate).
- Changing thresholds and re-running analysis can resolve issues a stricter rule raised.

Closed later: score history charts (Phase 5).

Detail: [Phase 3 report](IMPLEMENTATION_PLAN.md#11-phase-3-report) (section 11).

## Phase 4: AI agent

Goal: an optional AI layer that explains and drafts, grounded in stored data, and
never publishes.

Delivered:
- `AIProvider` interface and an Ollama provider with schema-constrained JSON and retry.
- Platform and organisation switches; NIIT starts with AI off.
- Nine typed, read-only, project-scoped agent tools and a bounded question loop.
- Five tasks: management summary, issue explanation, page improvement plan, title and
  description drafts, content outline.
- Grounding checks that reject invented numbers and claims.
- Drafts with version history, a six-state approval workflow, two-person approval and
  protected-fact detection.

Still open:
- Grounding checks are pattern-based and English-oriented. Human approval stays
  mandatory.
- Protected-fact detection is keyword-based and English-only.
- AI tasks run one at a time per worker.
- By design, a one-person organisation cannot approve drafts.

Since Phase 4, the AI has been run against a real local model on the owner's laptop
with `ai-eval` (sections 16.2 and 16.3).

Detail: [Phase 4 report](IMPLEMENTATION_PLAN.md#12-phase-4-report) (section 12).

## Phase 5: Reports and monitoring

Goal: management reports and a view of change between crawls.

Delivered:
- Reports with the 13 sections of the brief, complete with AI off.
- Organisation branding: colour, footer and a logo fetched through the SSRF guard.
- PDF export through optional Chromium, printed offline with every request refused.
- Monitoring page: score history and comparison of any two analysed crawls.
- Scheduled crawl foundation, off on both the server and the project by default.

Still open:
- PDF export needs Chromium on the server; HTML reports work without it.
- Notifications are preferences only; nothing is sent.
- Scheduled runs can start about a minute late, and are skipped while a crawl is active.

Closed later: retention of old crawls and reports (Phase 6).

Detail: [Phase 5 report](IMPLEMENTATION_PLAN.md#13-phase-5-report) (section 13).

## Phase 6: Commercial readiness

Goal: make the platform safe and manageable for several organisations, without
payments.

Delivered:
- A route-walking tenant verification suite (`tests/security/test_tenant_matrix.py`).
- Plans and usage limits, enforced at every usage point. No payment code.
- Integration records with credentials encrypted by operator-held keys.
- White-label reports, data retention, a platform audit log, and CLI `reset-password`
  and `rotate-secrets`.
- `docs/DEPLOYMENT.md` and `docs/SECURITY_REVIEW.md`. All high and medium findings fixed.

Still open:
- Analytics, CMS and webhook integrations are records only.
- Seeded `starter` and `professional` plans hold example numbers.
- The dashboard's CSP allows inline scripts.
- Access tokens stay valid for up to 15 minutes after a password reset.
- No profile page; notifications are preferences only.

Closed later: invitations (16.1), Search Console connection (16.5).

Detail: [Phase 6 report](IMPLEMENTATION_PLAN.md#14-phase-6-report) (section 14).

## After Phase 6

### Interface uplift (section 15)

Animated sign-in, grouped navigation, overview tiles and tabs, page thumbnails drawn
from crawl data, search-result previews and project tiles. No new figures; motion
stops under reduced-motion settings.
[Section 15](IMPLEMENTATION_PLAN.md#15-interface-uplift-after-phase-6).

### Technical gaps and owner requests (section 16)

| Item | Summary | Migration | Section |
|------|---------|-----------|---------|
| Invitations and password reset | Invite by email with a role; people choose their own password; reset by link. Email through the operator's own SMTP server, optional | 0009 | [16.1](IMPLEMENTATION_PLAN.md#161-invitations-and-password-reset) |
| Email test command | `send-test-email` explains SMTP failures without showing secrets; `docs/EMAIL.md` | None | 16.1a |
| AI measurement (AI step 1) | Model kept loaded, run metrics per task, `ai-report` and `ai-eval` | 0010 | [16.2](IMPLEMENTATION_PLAN.md#162-measuring-the-ai-assistant-ai-step-1) |
| Relevant data first (AI step 3) | Topic detection in code puts matching issues in the evidence; missing data is said first | None | [16.3](IMPLEMENTATION_PLAN.md#163-relevant-data-first-ai-step-3) |
| Feedback and NIIT test sets | "Was this helpful?" on AI results, `ai-feedback-cases`, test sets in `backend/evals/` | 0011 | [16.4](IMPLEMENTATION_PLAN.md#164-feedback-on-ai-results-and-organisation-test-sets) |
| Google Search Console | Service-account connection, daily imports, Search Performance page, figures for the AI | 0012 | [16.5](IMPLEMENTATION_PLAN.md#165-google-search-console) |
| Click opportunities | First-page pages whose click-through rate is below the site's own rate at similar positions | None | 16.5a |
| Crawl diagnostics | www twin in scope, start-page notes, IPv4-first fallback, `crawl-check`, single-page sites | None | [16.5b](IMPLEMENTATION_PLAN.md#165b-crawls-that-stopped-after-one-or-two-pages) |
| JavaScript rendering | Per-project Chromium rendering; every browser request goes through the guarded crawler | 0013 | [16.6](IMPLEMENTATION_PLAN.md#166-javascript-rendering-behind-the-ssrf-guard) |
| Product name and installer | `PRODUCT_NAME`, container images, `deploy/install.sh` and `install.ps1` | None | [16.7](IMPLEMENTATION_PLAN.md#167-configurable-product-name-and-one-command-installer) |

Crawl diagnostics in more detail (16.5b, three rounds):
- The bare and `www.` names of a host are one site, each with its own robots.txt.
- The crawl notes explain a stop at the start page: robots.txt, an error status, a
  redirect to another site, a fetch failure, or too few links in the HTML.
- The guarded client tries every checked address, IPv4 first, and gives plain error
  messages.
- `app.cli crawl-check --url <site> [--render]` shows where a crawl would stop.
- Single-page sites now render, and `#/…` addresses are explained in the crawl notes.

## What comes next

The plan does not set a further numbered phase. These items are stated as open in it:

| Area | Open item | Source |
|------|-----------|--------|
| AI | Steps 2 and 4 of the AI plan: trim prompts and compute facts in code, worked examples, native tool calling, and later lookup of approved content | 16.2 |
| AI | Run details are not shown as a dashboard chart; `ai-report` covers it | 16.2 |
| Security | Per-user token version so access tokens end at password reset | 14, 16.1 |
| Security | Nonce- or hash-based CSP for the dashboard | 14 |
| Scaling | Shared store for login and reset rate limits before several API processes | 8, 14, 16.1 |
| Interface | Profile page; light/dark toggle if people ask | 15 |
| Interface | Thumbnails are drawings, not screenshots; the renderer could be reused | 15, 16.6 |
| Crawler | Per-project allowed script hosts (CDNs) for rendering, if needed | 16.6 |
| Crawler | External link checks; plain-text sitemaps | 10 |
| Search data | Google Analytics connection, same service-account pattern, if the owner wants it | 16.5 |
| Search data | Per-country and per-device breakdowns | 16.5 |
| Email | HTML templates and other languages | 16.1 |
| Notifications | Sending needs an approved provider | 13, 14 |
| Plans | Owner sets real numbers for `starter` and `professional` before commercial use | 14 |
| Installer | Not verified in development: the Chromium step, the Windows installer, and an AI model download inside the stack | 16.7 |

Two rules apply to anything added here:
- Payment processing is not implemented until the owner authorises it.
- No paid API or service is used without explicit approval from the project owner.

Each connection to an outside service (CMS, analytics, notifications) waits for owner
authorisation. Publishing website changes always needs explicit human approval.

## How a phase is run

From `CLAUDE.md`:
1. Read the architecture, plan, security and NIIT configuration documents.
2. Inspect existing code and extend existing modules rather than duplicating them.
3. Implement the phase in small, reviewable commits, one concern each, on a branch.
   Never commit to `main`.
4. Write tests for new functionality. They use local fixtures and never contact live
   NIIT infrastructure.
5. Run lint, type checks and tests after every change, and fix errors before going on:

   ```
   # backend/
   uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
   # frontend/
   pnpm lint && pnpm typecheck && pnpm build && pnpm test:e2e
   ```

6. Update `README.md` and `docs/IMPLEMENTATION_PLAN.md`, including the feature status
   table, and record unfinished work and known limitations.
7. End with a phase report in the plan: files changed, features done, tests run and
   results, run commands, known limitations, and the next step.
