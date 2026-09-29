# NIIT SEO Agent

AI-assisted SEO agent for the National Institute of Information Technology (NIIT), a
constituent institute of the National Aerospace Science and Technology Park (NASTP).
The agent audits NIIT's public web presence, proposes and implements improvements,
and reports on search visibility for programmes, admissions and research pages.

This file is read by Claude Code at the start of every session started from this
directory. Keep it short, factual and current. Detailed procedures live in skills
under `.claude/skills/`.

## Project goals

1. Audit `niit.edu.pk` (and any staging copies) for technical, on-page and content SEO.
2. Ship fixes as reviewable pull requests, never as direct edits to production.
3. Track rankings and Core Web Vitals over time and surface regressions early.
4. Keep every change secure, accessible and compliant with institutional policy.

## Repository layout

```
CLAUDE.md                       Project memory for Claude Code (this file)
.claude/skills/                 Custom skills, one folder per skill
  seo-audit/SKILL.md            How to run and report an SEO audit
  fullstack-development/SKILL.md  How to build features in this codebase
  security-review/SKILL.md      How to review changes for security issues
```

Application code is added under `src/` (backend), `web/` (frontend) and `scripts/`
(one-off tooling) as the implementation plan is approved. Update this section when
the layout changes.

## Working rules

- **Plan before building.** For any non-trivial request, inspect the repository,
  write an implementation plan, and wait for approval before writing code.
- **Small, reviewable changes.** One concern per commit. Commit messages use the
  imperative mood and explain why, not just what.
- **Branching.** Never commit directly to `main`. Work on a feature branch and open a
  pull request. Do not force-push shared branches.
- **Secrets.** Never commit API keys, tokens, credentials or `.env` files. Read them
  from environment variables and document required variables in `.env.example`.
- **External calls.** Crawling and API calls against live NIIT properties must respect
  `robots.txt`, rate limits and the institute's acceptable-use rules.
- **Tests.** Every behaviour change ships with a test. Run the project's lint,
  type-check and test commands before committing.
- **Accessibility.** Frontend changes must meet WCAG 2.1 AA. SEO work never trades
  accessibility for ranking.
- **No fabricated data.** Audit findings, ranking numbers and performance scores must
  come from an actual tool run. If a measurement was not taken, say so.

## Skills

Invoke a skill with its slash command or describe the task and let Claude pick it.

| Skill | Use when |
|-------|----------|
| `/seo-audit` | Auditing a site, page or sitemap and producing a prioritised findings report |
| `/fullstack-development` | Adding or changing backend, frontend or database code |
| `/security-review` | Reviewing a branch or pull request for security defects before merge |

## Conventions

- Language: TypeScript for application code unless a plan says otherwise.
- Formatting and linting: Prettier and ESLint with the repository config once added.
- Documentation: Markdown in `docs/`. Diagrams as Mermaid in Markdown.
- Reports: audit output is written to `reports/<yyyy-mm-dd>-<target>.md`.

## Contacts and ownership

Project owner: Office of the Principal, NIIT (principal@niit.edu.pk).
Direct questions about scope, priorities or institutional policy to the owner.
