# NIIT SEO Agent: Implementation Plan

Status: **Draft, awaiting owner approval.** No application code is written until this
plan is approved or amended.

Date: 2026-09-29
Branch: `claude/zen-maxwell-11wg4z`

## 1. What we are building

A TypeScript service that audits NIIT's public web properties for SEO, stores results
over time, and produces prioritised reports and fix pull requests. It has three parts:

1. **Crawler and collectors.** Politely crawl a target site, fetch Lighthouse and
   PageSpeed Insights data, validate structured data, and persist raw observations.
2. **Rules engine and reporting.** Turn observations into findings with severity,
   evidence and a fix, then render the Markdown report described in the
   `seo-audit` skill and a small web dashboard for trends.
3. **Fix workflow.** For findings with a known code fix, open a pull request against
   the website repository with the change and the finding attached.

The `.claude/skills/` folders already define how Claude Code audits, builds and
reviews. This plan covers the software those skills operate.

## 2. Assumptions to confirm

These were made because the master project prompt was not available when this plan
was drafted. Each one changes the design if wrong.

| # | Assumption | If wrong |
|---|------------|----------|
| A1 | Primary target is `https://niit.edu.pk`; staging copies may be added later | Add multi-tenant target config in Phase 1 |
| A2 | The NIIT website source lives in a separate Git repository we can open PRs against | Fix workflow (Phase 4) becomes report-only |
| A3 | A relational database (PostgreSQL, SQLite for local dev) is acceptable | Swap the storage adapter in Phase 1 |
| A4 | Google PageSpeed Insights API and Search Console API access can be provisioned | Fall back to local Lighthouse runs only, no field data or ranking tracking |
| A5 | Reports are consumed by the Principal's office as Markdown and a simple internal dashboard | Adjust Phase 3 output formats |
| A6 | Hosting is a single small VM or container with a scheduled job, not a public SaaS | Add auth, multi-user and hardening scope |

## 3. Proposed stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Language | TypeScript, Node.js 22 LTS, `strict` | Matches CLAUDE.md conventions, one language front to back |
| Backend | Fastify | Small, fast, schema-validated routes, good TypeScript support |
| Crawler | `undici` fetch plus `cheerio` for HTML parsing, `robots-parser`, `p-queue` for concurrency limits | Lightweight, no headless browser needed for most checks |
| Rendering checks | Playwright (Chromium) on demand only | Detects JavaScript-dependent content; expensive, so opt-in per page |
| Performance | Lighthouse CLI locally, PageSpeed Insights API for field data | Lab and field data reported separately per the skill |
| Structured data | `schema-dts` types plus a JSON-LD validator | Typed generation and validation in tests |
| Database | PostgreSQL in production, SQLite locally, via Drizzle ORM with versioned migrations | Simple relational model, easy trend queries |
| Frontend | Astro with server rendering, minimal client JavaScript | Semantic HTML and strong Lighthouse scores by default |
| Tests | Vitest, Playwright for UI smoke tests | Fast, TypeScript native |
| Tooling | pnpm, ESLint, Prettier, Husky pre-commit, GitHub Actions CI | Enforces the working rules automatically |

Alternatives considered: Next.js for the frontend (heavier client bundle for a
read-mostly dashboard), a Python crawler (splits the codebase across two languages).

## 4. Repository layout (target)

```
src/
  config/         target definitions, env loading, .env.example
  crawler/        fetcher, robots handling, queue, HTML extraction
  collectors/     lighthouse, pagespeed, structured-data, headers
  rules/          one file per SEO rule, each exporting check() and metadata
  reports/        Markdown renderer, severity ordering, diff against baseline
  db/             Drizzle schema, migrations, repositories
  api/            Fastify routes for runs, findings, trends
  jobs/           scheduled audit runner
web/              Astro dashboard: run history, findings, CWV trends
scripts/          one-off tooling (seed, backfill, export)
reports/          generated audit reports (committed, per CLAUDE.md)
docs/             this plan, architecture notes, runbooks
```

## 5. Phases and deliverables

Each phase ends in a pull request that passes lint, type-check, tests and a security
review. Estimates assume one developer working with Claude Code.

### Phase 0: Project foundation (1 to 2 days)

- pnpm workspace, TypeScript config, ESLint, Prettier, Vitest, Husky.
- GitHub Actions: install, lint, type-check, test on every PR.
- `.env.example`, `README.md`, `docs/architecture.md` with a Mermaid diagram.
- Branch protection on `main` (owner action).

Done when: an empty test passes in CI and a PR cannot merge with a red check.

### Phase 1: Crawler and storage (3 to 5 days)

- Target configuration: base URL, allowed hosts, max pages, concurrency, user agent.
- Polite fetcher: robots.txt compliance, per-host rate limit, timeouts, redirect cap,
  private IP blocklist (SSRF guard), response size cap.
- HTML extraction: title, meta, headings, links, images, canonical, hreflang, JSON-LD.
- Sitemap and robots parsing; discovered-vs-sitemap URL comparison.
- Drizzle schema: `runs`, `pages`, `observations`, `findings`. Migrations up and down.
- CLI: `pnpm audit:crawl --target niit` writes a run to the database.

Done when: a crawl of a local fixture site produces expected pages and observations
in tests, and a real crawl of the target completes within configured limits.

### Phase 2: Rules engine and collectors (4 to 6 days)

- Rule interface: `id`, `severity`, `category`, `check(page, run) => Finding[]`.
- Initial rule set (about 25 rules) covering: noindex on key pages, missing or
  duplicate titles and descriptions, heading hierarchy, missing alt text, broken
  links, redirect chains, canonical conflicts, mixed content, missing HSTS, sitemap
  gaps, thin content, missing structured data for programmes and events.
- Lighthouse collector (lab CWV) and PageSpeed Insights collector (field CWV) with
  results stored per page per run.
- Structured data validator for `EducationalOrganization`, `Course`, `Event`,
  `BreadcrumbList`, `FAQPage`.

Done when: every rule has a unit test with a passing and a failing fixture, and a run
against the target yields findings with evidence.

### Phase 3: Reporting and dashboard (3 to 4 days)

- Markdown report renderer matching the `seo-audit` skill template, written to
  `reports/<date>-<target>.md`, with a diff section against the previous run.
- Fastify API: list runs, findings by run, CWV trend per URL.
- Astro dashboard: run list, findings table with severity filter, CWV trend charts,
  per-page detail. Server rendered, WCAG 2.1 AA, keyboard accessible.
- Scheduled job (weekly by default) that runs a crawl, collectors, rules and report.

Done when: a scheduled run produces a report and the dashboard shows it, and
Lighthouse accessibility on the dashboard scores at least 95.

### Phase 4: Fix workflow (3 to 5 days, depends on A2)

- Map selected rules to code fixes (for example, add a missing meta description
  template, fix a redirect rule, add `alt` attributes).
- GitHub integration to open a PR on the website repository with the change, the
  finding ID and evidence in the description.
- Guardrails: never push to the default branch, one finding per PR, dry-run mode.

Done when: a finding on a fixture repository produces a reviewable PR end to end.

### Phase 5: Hardening and handover (2 to 3 days)

- Security review of the whole codebase using the `security-review` skill.
- Runbooks in `docs/`: deploy, rotate credentials, add a target, add a rule.
- Backup and retention policy for the database.
- Owner training session and acceptance.

## 6. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Crawler overloads the live site | Default concurrency 2, 1 request per second per host, hard page cap, robots compliance, dedicated user agent with contact address |
| Google API quotas or approval delays | Lighthouse local runs work without any API; field data is additive |
| Website repository not accessible for automated PRs | Phase 4 degrades to report-only with copy-paste patches in the report |
| Scope creep into general marketing analytics | Plan is limited to SEO, CWV and accessibility signals; anything else needs a new plan |
| Network restrictions in the development sandbox | The Claude Code cloud environment currently blocks `niit.edu.pk`; crawls run locally or the environment allowlist is extended by the owner |

## 7. Decisions needed from the owner

1. Confirm or correct assumptions A1 to A6.
2. Approve the stack in section 3, or name preferred alternatives.
3. Confirm where the NIIT website source lives and who can grant PR access.
4. Confirm who will provision Google API credentials.
5. Approve starting Phase 0.

Once approved, work proceeds one phase per pull request using the
`fullstack-development` skill, with a security review before each merge.
