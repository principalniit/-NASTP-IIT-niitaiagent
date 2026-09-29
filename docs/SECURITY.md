# Security

Security design and operating notes. Report suspected vulnerabilities privately to
the project owner (principal@niit.edu.pk). Do not open public issues for them.

## 1. Threat model summary

| Asset | Threat | Primary controls |
|-------|--------|------------------|
| Tenant data | Cross-organisation access by ID tampering | Backend membership check on every request (organisations, projects, crawls, pages, issues, SEO results); `organisation_id` on every tenant row; 404 for foreign resources; isolation tests per module |
| User accounts | Credential stuffing, token theft | Argon2id hashing, login rate limiting, short-lived access tokens, rotating refresh tokens with reuse detection, `HttpOnly` cookies |
| Internal network | SSRF through the crawler | Connection-time address checks with pinning, port allowlist, per-redirect revalidation, host scope, proxies ignored |
| Target websites | Being overloaded by our crawler | robots.txt, delay, low concurrency, page and depth caps |
| Institutional reputation | AI-fabricated claims | Grounded prompts, output validation, human approval, no automatic publishing |
| Secrets | Leakage in code, logs, errors | `.env` only, `.env.example` placeholders, redacted logs, generic error bodies |
| Supply chain | Malicious or vulnerable packages | Minimal dependencies, lockfiles, `pip-audit` and `pnpm audit` in CI, GitHub Actions pinned to commit SHAs with read-only token permissions |

## 2. Authentication and sessions

- Argon2id via `argon2-cffi` with library defaults; hashes are re-computed on login
  when parameters change.
- Access tokens are JWTs signed with HS256 using `JWT_SECRET`, lifetime 15 minutes,
  audience and issuer checked, `exp`, `iat`, `sub` and `jti` required.
- Refresh tokens are opaque random values. Only their SHA-256 hash is stored. They
  rotate on every refresh. Presenting a revoked token revokes its whole family.
- Refresh cookie: `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Secure` when
  `COOKIE_SECURE=true` (required in production).
- The refresh and logout endpoints also require the `X-Requested-With` header, which
  cross-site forms cannot set.
- Login responses are identical for unknown email and wrong password.
- Failed logins are limited per email (default 5 per 5 minutes) and per client address
  (default 20 per 5 minutes). A successful login clears only that email's counter.
- Deactivated users cannot log in or refresh.

## 3. Authorisation

- Roles: platform administrator (user flag), and per organisation: owner, admin,
  SEO manager, editor, viewer.
- All permissions are declared in one map and checked by a shared FastAPI
  dependency. The frontend hides actions a role cannot perform, but the backend is
  the only enforcement point.
- An organisation must always keep at least one owner. Only owners can grant or
  remove the owner role.
- Platform administrators can manage any organisation's profile and memberships but
  have no implicit access to its projects or SEO data. To support a tenant they add
  themselves as a member, which is audit-logged.

## 4. SSRF protection (crawler)

The crawler fetches URLs chosen by tenants and by the websites it crawls, so it must
never reach the platform's own network. Controls, all covered by
`backend/tests/security/test_ssrf.py` and `tests/integration/test_crawl_engine.py`:

- **Connection-time checks.** The check runs inside the HTTP client's network backend,
  not before the request, so no code path can skip it. Every resolved address is
  checked; if any is not public the connection is refused.
- **Address pinning.** The socket is opened to the address that was checked. A second
  DNS answer (DNS rebinding) is never used. TLS still verifies the original hostname.
- **Blocked ranges.** Loopback, RFC 1918, link-local (including `169.254.169.254`
  metadata), CGNAT `100.64.0.0/10`, multicast, reserved, unspecified, benchmarking
  `198.18.0.0/15`, IPv6 loopback, link-local, unique-local, and IPv4-mapped forms of
  all of these.
- **Ports.** 80 and 443, plus the explicit port of the project's root URL.
- **Redirects** are followed manually, one hop at a time, each scope-checked and
  SSRF-checked. Redirects to hosts outside the project scope are recorded, not followed.
- **Scope.** Only the project's host and hosts an authorised user added to the project
  are fetched. Sitemaps on other hosts are skipped.
- **Proxies.** Environment proxy variables are ignored by the crawler, because a proxy
  would make the connected address differ from the checked one.
- **Explicit exceptions.** `CRAWLER_ALLOWED_PRIVATE_NETWORKS` can allow specific
  private ranges (for example an on-premises staging server). It is empty by default,
  and production refuses loopback or link-local ranges in it.
- **Resource limits.** Response bodies are capped at `CRAWLER_MAX_RESPONSE_BYTES`
  after decompression; sitemaps at 50 MB; sitemap XML is parsed with entity
  resolution, DTD loading and network access disabled; crawls stop at
  `CRAWLER_MAX_DURATION_SECONDS`.
- **Politeness.** robots.txt is always respected, an unreachable robots.txt blocks the
  host, and requests to one host are spaced by the larger of the project delay and the
  site's `Crawl-delay`.

## 5. Client addresses behind proxies

The browser reaches the API through the Next.js server's `/api/v1` rewrite. Testing
showed that Next.js forwards the client's `X-Forwarded-For` header unchanged and does not
append the real address, so the header alone can be forged.

- Development and any deployment without a trusted reverse proxy: keep
  `TRUST_PROXY_HEADERS=false`. The API then sees the Next.js server's address for every
  user, which is why the per-address login limit is higher than the per-email limit.
- Production: put nginx (or equivalent) in front of Next.js, make it overwrite the
  header with the real address, and set `TRUST_PROXY_HEADERS=true`. The API uses the
  right-most entry. Example nginx directive:

  ```
  proxy_set_header X-Forwarded-For $remote_addr;
  ```

- Always bind the API to `127.0.0.1` or a private network so clients cannot reach it
  directly and supply their own header.

## 5a. AI assistant and approvals

AI is an untrusted component: its output is text to be checked, never an instruction
the platform acts on.

- **Off by default.** `AI_PROVIDER=none` disables it for the whole platform, and each
  organisation must also turn it on. The Ollama address comes only from operator
  configuration (`OLLAMA_BASE_URL`), so a tenant cannot point the server at another
  host. Requests to Ollama ignore proxy environment variables.
- **No free actions.** The model can only request one of nine read-only tools with
  validated arguments. Each tool is bound to the one project the requester is
  authorised for and filters by project and organisation. There is no SQL, shell,
  file or network tool, and at most four tool calls per question.
- **Prompt injection.** Crawled page text reaches the model as evidence. It could
  contain instructions, but the model has nothing dangerous to call, its output is
  schema-validated and grounding-checked, and results are stored as recommendations or
  drafts that a person must review. Nothing an AI writes changes a website.
- **Grounding.** Outputs with numbers not present in the evidence, unknown issue ids,
  or claims about rankings, traffic, search volumes, backlinks or guaranteed results
  are rejected after one retry, and nothing is saved.
- **Approvals.** Only the defined state transitions are allowed. The author or
  submitter of a version cannot approve it. Drafts touching fees, dates, eligibility
  and similar official facts need a verified source reference. Every transition is
  audit-logged with the actor. "Published" is a record of a human action; the platform
  has no write access to any website.
- **Load.** AI tasks run in the worker with a per-request timeout
  (`AI_TIMEOUT_SECONDS`), and each organisation may have at most
  `AI_MAX_ACTIVE_JOBS_PER_ORG` queued or running.
- **Stored data.** Evidence and output are stored with each analysis for traceability.
  They contain crawled public page text and issue data, no credentials.

## 5b. Reports and scheduled crawls

- **Crawled content in reports** is untrusted. The report template autoescapes every
  value. The document carries its own content security policy (no scripts, no remote
  loading), and the dashboard shows it in an iframe sandboxed with no permissions.
- **No fetching during rendering.** The logo is the only external resource. It is
  fetched once through the crawler's SSRF guard (HTTPS, image types only, size-capped)
  and embedded. The PDF renderer runs with JavaScript disabled, offline, and refuses
  every request; a security test checks that no request reaches a local server.
- **Access.** Generating and deleting reports needs the reports permission (owner,
  admin, SEO manager); every organisation member can read them. Report ids from other
  organisations return 404. Requests and deletions are audit-logged.
- **Load.** At most 3 reports per organisation can be queued or running.
- **Schedules** start crawls without a person pressing a button, so two switches must
  be on: `SCHEDULER_ENABLED` on the server and the project's schedule. Scheduled crawls
  use the same limits, robots.txt handling and SSRF guard as manual ones, and are
  audit-logged as `crawl.scheduled`.

## 6. Input, output and errors

- Pydantic validates every request body, query parameter and configuration blob.
- SQLAlchemy parameterised queries only; no raw SQL built from input.
- Error responses never include stack traces, SQL or secrets. A request ID links the
  user-visible error to server logs.
- CORS allows only origins listed in `CORS_ORIGINS`.
- Security headers on API responses: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, and a restrictive `Content-Security-Policy` for docs pages.

## 7. Audit logging

Append-only `audit_logs` records: login success and failure, logout, token reuse
detection, organisation, member, project and settings changes, and (later) crawls,
approvals and publication records. Records include actor, organisation, action, target,
IP and a small metadata object. Passwords and tokens are never logged. Phase 4 adds
`ai.requested`, `recommendation.updated` and `draft.<action>` for every draft
transition. Phase 5 adds `report.requested`, `report.deleted`, `schedule.updated` and
`crawl.scheduled`.

## 8. Secrets and configuration

- All secrets come from environment variables. `.env` is git-ignored.
- `.env.example` contains placeholders only.
- The application refuses to start in production mode with the development
  default `JWT_SECRET` or with `COOKIE_SECURE=false`.

## 9. Known limitations

- Login rate limiting is in-process. It does not coordinate across multiple API
  instances. Replace with a shared store before horizontal scaling.
- Sign-in events are recorded without an organisation, so they appear in the database
  audit log but not in any organisation's audit view. A platform-level audit view is
  planned for Phase 6.
- Organisation administrators can add an existing account to their organisation by
  email and can create accounts with an initial password. Invitations that the invited
  person must accept, and forced password change on first sign-in, are planned for
  Phase 6.
- Row-level security in PostgreSQL is not enabled. Isolation is enforced in the
  application layer and covered by tests.
- Integration credentials (Phase 6) will need encryption at rest with a key held
  outside the database.
- JavaScript rendering is not enabled because browser sub-requests would bypass the
  connection-level SSRF guard. It needs request interception and a dedicated review.
- Crawl data volume is bounded by the organisation's page cap and 2,000 stored links
  per page. Automatic retention and cleanup of old crawls and reports is not built
  yet; it is planned for Phase 6.
- Grounding checks are pattern-based. They catch invented numbers, unknown issue ids and
  the listed claim types, but cannot prove that every sentence is true. That is why AI
  output is labelled, drafts need human approval, and protected facts need a source.
- Protected-fact detection is keyword and pattern based, in English. It errs toward
  flagging; content in other languages needs reviewer attention.
- A single-person organisation cannot approve drafts, by design. It needs a second
  member with an approving role.
