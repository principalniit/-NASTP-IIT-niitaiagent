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

These are defaults. A written and approved plan may override them.

- **Language**: TypeScript with `strict` enabled.
- **Backend**: Node.js. HTTP framework and ORM are chosen in the implementation plan
  and recorded in `CLAUDE.md` once decided.
- **Frontend**: component-based, server-rendered where it helps SEO. Semantic HTML,
  WCAG 2.1 AA, no client-side rendering of primary content.
- **Database**: relational. Schema changes go through versioned migrations. Never
  edit a migration that has been merged.
- **Tests**: colocated `*.test.ts` files. Aim for meaningful coverage of behaviour,
  not a percentage.
- **Style**: Prettier and ESLint using the repository config. Do not disable rules
  inline without a comment explaining why.

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
