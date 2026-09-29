---
name: security-review
description: Review a branch, pull request or set of files for security defects before merge. Use when asked to security-review, threat-model or harden code, or before merging changes that touch authentication, authorisation, input handling, file or network access, secrets, dependencies or deployment configuration.
---

# Security Review

Find and report exploitable weaknesses in the changes under review, ranked by
severity, each with a concrete fix. Verify findings against the actual code. Do not
pad the report with theoretical issues that the code does not exhibit.

## Scope

Default scope is the diff between the current branch and `main`. The user may widen
it to specific directories or the whole repository. State the scope at the top of the
report.

## Procedure

1. **Map the change**
   - List the files changed and classify each: entry point (HTTP, CLI, job),
     business logic, data access, configuration, dependency manifest, infrastructure.
   - Identify trust boundaries crossed: user input, third-party APIs, crawled web
     content, environment variables, database.

2. **Check each category**

   **Input handling and injection**
   - SQL, NoSQL, command, LDAP and template injection. Parameterised queries only.
   - Path traversal in any file read or write derived from input.
   - Server-side request forgery in crawlers and URL fetchers: enforce allowlists,
     block private IP ranges, cap redirects, set timeouts.
   - Deserialisation of untrusted data.

   **Web application**
   - Cross-site scripting: output encoding, unsafe HTML rendering, DOM sinks.
   - Cross-site request forgery on state-changing routes.
   - Security headers: Content-Security-Policy, HSTS, X-Content-Type-Options,
     Referrer-Policy, frame protections.
   - Open redirects, especially in SEO redirect rules.

   **Authentication and authorisation**
   - Session handling, token storage, cookie flags (`HttpOnly`, `Secure`, `SameSite`).
   - Missing or inconsistent authorisation checks. Insecure direct object references.
   - Password and secret handling: hashing algorithm, rate limiting, lockout.

   **Secrets and configuration**
   - Hard-coded keys, tokens or credentials anywhere in the diff or history.
   - Secrets in logs, error messages or client bundles.
   - Debug modes, verbose errors or default credentials reaching production config.

   **Data protection**
   - Personal data of students, staff or applicants: minimise collection, encrypt in
     transit and at rest, define retention.
   - Logging of personal or sensitive data.

   **Dependencies and supply chain**
   - New or updated packages: known vulnerabilities, maintenance status, licence,
     install scripts, typosquatting risk. Lockfile present and updated.

   **Crawler and external-call safety**
   - Respect for `robots.txt`, rate limits and per-host concurrency caps.
   - Handling of oversized, malformed or malicious responses from crawled pages.
   - Resource exhaustion: unbounded queues, missing timeouts, recursion on redirects.

   **Infrastructure and CI**
   - Over-privileged tokens in workflows, unpinned actions, secrets exposed to pull
     requests from forks, containers running as root.

3. **Verify**
   - For each suspected issue, read the surrounding code and confirm the path is
     actually reachable and exploitable. Where practical, write a failing test or a
     reproduction command.
   - Drop findings that turn out to be mitigated elsewhere, and say so briefly in the
     "Checked and clear" section so reviewers know they were considered.

## Severity

| Level | Meaning |
|-------|---------|
| Critical | Remote code execution, authentication bypass, exposure of secrets or bulk personal data |
| High | Injection, SSRF, privilege escalation, stored XSS |
| Medium | Reflected XSS, CSRF, missing security headers, weak crypto, verbose errors |
| Low | Hardening gaps with no direct exploit path |

## Output

Report in chat, and when asked also write to `reports/security-<yyyy-mm-dd>-<branch>.md`:

```
# Security Review: <branch or PR>  (<date>)

Scope: <what was reviewed>
Verdict: Block / Fix before merge / Merge with follow-ups / Clear

## Findings
### [Severity] Title
- Location: file:line
- Issue: what is wrong and how it can be abused
- Evidence: the code or a reproduction
- Fix: specific change, with a snippet where helpful

## Checked and clear
Categories examined with no issue found.

## Recommendations
Non-blocking hardening, ordered by value.
```

## Rules

- Never weaken a control, skip a test or disable a check to make a review pass.
- Prefer the safer fix when two are available.
- Treat crawled web content and third-party API responses as hostile input.
- Do not include real secrets in the report. Redact and reference the location only.
- A critical or high finding blocks merge until fixed or explicitly accepted by the
  project owner in writing.
