---
name: fullstack-development
description: Build and change backend, frontend and database code in the NIIT SEO Agent repository following its conventions. Use when implementing features, fixing bugs, adding API endpoints, UI components, data models, jobs or tests.
---

# Fullstack Development

Deliver working, tested, reviewable code that follows the repository's conventions in
`CLAUDE.md`. Plan first, implement in small steps, verify before committing.

## Workflow

1. **Understand the request**
   - Restate the goal in one or two sentences. Identify the user-facing behaviour
     and the acceptance criteria.
   - Read the relevant code before proposing changes. Do not guess at file contents.

2. **Plan**
   - For anything beyond a one-file fix, write a short plan: files to touch, data
     model or API changes, migration needs, test strategy, rollout risks.
   - Present the plan and wait for approval when the request is ambiguous or the
     change is architecturally significant. Otherwise proceed and state assumptions.

3. **Implement**
   - Work on a feature branch. Never commit to `main`.
   - Follow existing patterns in the codebase over personal preference.
   - Keep functions small and named for what they do. Prefer explicit types.
   - Validate all external input at the boundary (HTTP handlers, CLI args, queue
     messages). Return structured errors.
   - Read configuration and secrets from environment variables. Update
     `.env.example` when adding a variable.
   - Add or update tests alongside the code: unit tests for logic, integration tests
     for endpoints and database access, a smoke test for new UI routes.

4. **Verify**
   - Run the project's formatter, linter, type-checker and test suite. Fix everything
     they report before committing.
   - For UI changes, load the page and confirm the change renders and is keyboard
     accessible. Check console for errors.
   - For database changes, run the migration up and down on a scratch database.

5. **Commit and hand off**
   - One logical change per commit. Message: imperative subject line under 72
     characters, blank line, then the reason and any trade-offs.
   - Summarise what changed, how it was verified, and anything left for follow-up.
   - Run `/security-review` before opening a pull request that touches auth, input
     handling, file access, external calls or dependencies.

## Stack conventions

The stack is fixed by the project brief and recorded in `CLAUDE.md`.

- **Backend**: Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy 2, Alembic.
  Each module in `backend/app/modules/<name>/` owns `models.py`, `schemas.py`,
  `service.py` and `router.py`. Routers call services; services take an
  `AsyncSession` and an authorised context. Never query tenant data without an
  `organisation_id` filter.
- **Authorisation**: declare the needed permission on the route using the shared
  dependency in `organisations`. Never rely on the frontend to enforce access.
- **Database**: every schema change is a new Alembic migration, tested with upgrade
  and downgrade. Never edit a merged migration. UUID keys, foreign keys, indexes.
- **Frontend**: Next.js App Router, strict TypeScript, Tailwind, shadcn/ui,
  TanStack Query for server state, React Hook Form with Zod for forms. Every data
  view has loading, empty, error and retry states. Never render placeholder numbers.
- **Tests**: pytest for backend (unit, integration against PostgreSQL, security),
  Playwright for end-to-end flows. Use local fixtures, never live NIIT pages.
- **Quality gates**: `ruff check`, `ruff format --check`, `mypy app`, `pytest`,
  `pnpm lint`, `pnpm typecheck`, `pnpm build`.

## SEO-specific requirements for frontend work

- Every page has a unique `<title>` and `<meta name="description">`.
- One `<h1>` per page. Headings form a logical outline.
- Images have descriptive `alt` text, explicit dimensions and lazy loading below the
  fold only.
- Canonical URLs, Open Graph and Twitter Card tags are emitted from a single
  metadata helper, not hand-written per page.
- Structured data is generated from typed data and validated in tests.
- Do not ship anything that regresses Lighthouse performance or accessibility scores
  on the affected routes.

## Things to avoid

- Committing generated files, build output, `.env` files or credentials.
- Adding a dependency without checking licence, maintenance status and size.
- Large refactors mixed into feature commits.
- Silent catch blocks. Log with context or rethrow.
- Skipping or disabling a test to make CI pass.
