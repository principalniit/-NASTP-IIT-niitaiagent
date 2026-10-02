# Security

Security design and operating notes. Report suspected vulnerabilities privately to
the project owner (principal@niit.edu.pk). Do not open public issues for them.

## 1. Threat model summary

| Asset | Threat | Primary controls |
|-------|--------|------------------|
| Tenant data | Cross-organisation access by ID tampering | Backend membership check on every request; `organisation_id` on every tenant row; 404 for foreign resources; isolation tests per module and a suite that walks every API route (`tests/security/test_tenant_matrix.py`) |
| User accounts | Credential stuffing, token theft | Argon2id hashing, login rate limiting, short-lived access tokens, rotating refresh tokens with reuse detection, `HttpOnly` cookies |
| Internal network | SSRF through the crawler | Connection-time address checks with pinning, port allowlist, per-redirect revalidation, host scope, proxies ignored |
| Target websites | Being overloaded by our crawler | robots.txt, delay, low concurrency, page and depth caps |
| Institutional reputation | AI-fabricated claims | Grounded prompts, output validation, human approval, no automatic publishing |
| Secrets | Leakage in code, logs, errors | `.env` only, `.env.example` placeholders, redacted logs, generic error bodies; integration credentials encrypted with keys held outside the database |
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
  (default 20 per 5 minutes). A successful login clears only that email's counter. When
  proxy headers are not trusted, sign-ins through the dashboard all come from its
  loopback address, so only the per-email limit applies; otherwise a few wrong passwords
  would lock every user out. Production runs behind nginx with `TRUST_PROXY_HEADERS=true`
  (see `docs/DEPLOYMENT.md`), where per-address limits work.
- `JWT_SECRET` must be 32 or more random characters. In production the API refuses to
  start without one. Elsewhere a missing or placeholder value is replaced by a random
  secret for the life of the process, so no published value ever signs tokens.
- Deactivated users cannot log in or refresh.

### Invitations and password resets

- Invitation and reset tokens are 256-bit random values. Only their SHA-256 hash is
  stored; each works once and expires (7 days and 60 minutes by default).
- Links carry the token in the URL fragment (`#token=`), which browsers never send to a
  server or in a `Referer` header. The dashboard sends it only in request bodies, so it
  stays out of access logs.
- Accepting with a new account is refused when the address already has one; the owner
  of that account must sign in as it to accept. Nobody can attach or take over an
  account they do not control. A signed-in account can accept only an invitation for
  its own address.
- Inviting follows the member rules: `members:manage` is needed, only owners can invite
  owners, and the plan's member limit is checked when the invitation is created and
  again when it is accepted. A new invitation for the same address replaces the old one.
- The reset request always answers 202 with the same message, and the email is sent
  after the response, so neither content nor timing reveals whether an account exists.
  Requests are limited to 3 per address and 20 per client address in 15 minutes. Only
  the newest link works. Confirming a reset ends every session of the account.
- Email uses the operator's own SMTP server with TLS. Credentials stay in the
  environment and are never logged; a mail failure is logged by type only and never
  breaks the request.

## 3. Authorisation

- Roles: platform administrator (user flag), and per organisation: owner, admin,
  SEO manager, editor, viewer.
- All permissions are declared in one map and checked by a shared FastAPI
  dependency. The frontend hides actions a role cannot perform, but the backend is
  the only enforcement point.
- An organisation must always keep at least one owner. Only owners can grant or
  remove the owner role.
- Platform administrators can manage any organisation's profile and memberships but
  have no implicit access to its projects, SEO data or integrations. To support a tenant
  they add themselves as a member, which is audit-logged.
- Emails are not verified, so only platform administrators can add an account that
  already exists to an organisation. Organisation administrators can create new accounts
  (with an initial password) but cannot attach existing ones, because such an account may
  have been created by another organisation with a password it knows. Promoting an
  existing account with `create-admin` always sets a new password and ends its sessions.
- Only owners can change the data retention policy, because it deletes data permanently.

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
- **JavaScript rendering** (optional per project, `crawler/renderer.py`).
  - The browser never uses the network itself. Every request it makes is intercepted.
    Only GET requests for scripts and data (fetch and XMLHttpRequest) are considered.
    They are fetched by the crawler's guarded client under the SSRF check, crawl scope,
    exclusions, robots.txt, the politeness delay and a 3 MB cap, and everything else is
    refused. The page itself is the response the crawler already fetched.
  - Defence in depth: Chromium starts with every hostname mapped to "not found" and a
    proxy that refuses connections. A request interception cannot see, such as a
    WebSocket, reaches nothing.
  - A security test shows the WebSocket reaching an outside server without these flags
    and not with them.
  - Service workers are blocked. Each page gets a fresh context with no cookies.
  - At most 40 sub-requests and 20 seconds per page are allowed. Pages that fail are
    analysed as served, and the crawl says how many.

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
- **Grounding evidence.** Answers are checked against what the tools returned, never
  against the tool arguments the model chose. Output that fails grounding is not stored.
  Page facts in prompts are capped so a hostile page cannot push out the instructions.
- **Approvals.** Only the defined state transitions are allowed, and each locks the
  draft row. Nobody who created a draft, requested it from the assistant, wrote any
  version, or submitted the current version can approve it; edits that change nothing
  are refused. Drafts touching fees, dates, eligibility and similar official facts need
  a verified source reference: a page on one of the project's approved sources, or an
  official document cited by name and reference. Protected facts are detected against
  the crawled value, never against an "original" typed by the author. Every transition
  is audit-logged with the actor. "Published" is a record of a human action; the platform
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
  fetched once through the crawler's SSRF guard (HTTPS, image types only, uncompressed,
  512 KB and 10 seconds at most, signature checked) and embedded. The PDF renderer runs
  with JavaScript disabled, offline, and refuses every request; a security test checks
  that no request reaches a local server. Chromium uses its own sandbox whenever the
  worker does not run as root.
- **Access.** Generating and deleting reports needs the reports permission (owner,
  admin, SEO manager); every organisation member can read them. Report ids from other
  organisations return 404. Requests and deletions are audit-logged.
- **Load.** At most 3 reports per organisation can be queued or running.
- **Schedules** start crawls without a person pressing a button, so two switches must
  be on: `SCHEDULER_ENABLED` on the server and the project's schedule. Scheduled crawls
  use the same limits, robots.txt handling and SSRF guard as manual ones, and are
  audit-logged as `crawl.scheduled`.

## 5c. Plans, integrations and retention (Phase 6)

- **Plans and usage limits.** Limits are enforced in the backend at every point where
  usage grows: projects, members, crawls (manual and scheduled), pages per crawl, AI
  tasks and reports. Checks take a per-organisation lock until the transaction commits,
  so concurrent requests cannot overshoot. Report usage is counted from the audit log,
  so deleting reports does not give quota back. Only platform administrators create,
  change or assign plans. No payment processing exists.
- **Integration credentials** are encrypted with Fernet (`INTEGRATIONS_ENCRYPTION_KEYS`,
  kept outside the database). They are write-only: the API never returns or logs them,
  and only long credentials show their last four characters. Without a key, credentials
  cannot be saved. Keys rotate with `app.cli rotate-secrets`. Integration records are
  for owners and administrators who are members; the platform makes no connection to
  these services.
- **Retention** is off by default and only owners can turn it on. It removes page-level
  data of older crawls and deletes old reports, never the newest completed crawl, the
  latest analysed crawl, or a crawl under analysis. A crawl whose pages were removed
  cannot be analysed again, so no result is computed from missing data. Every run is
  audit-logged, with the policy change recorded by whom and from what to what.
- **Platform audit log.** Platform administrators can read every audit entry, including
  sign-ins, which belong to no organisation.

## 5d. Google Search Console

- The only outbound connections are to two fixed Google addresses held in server settings
  (`GOOGLE_TOKEN_URL`, `GOOGLE_SEARCH_CONSOLE_URL`). The `token_uri` inside a key file is
  ignored, so a tampered key cannot direct the server elsewhere. Redirects are not
  followed and proxy settings from the environment are not used.
- The scope is `webmasters.readonly`. The platform cannot change anything in Search
  Console.
- The JSON key is validated when saved, stored encrypted like other credentials, and never
  returned. Only the service account's email, which is not secret, is shown so that it can
  be added to the property.
- Only owners and administrators can test, import or change the connection. Any member can
  read the imported figures of their organisation's projects.
- Google's error bodies are neither shown nor logged; people see a fixed explanation per
  status, and logs record the status code only.
- Imported figures are scoped by `organisation_id` and matched to projects by host. The
  tenant suite covers the new routes.
- The AI may state traffic or position figures only when Search Console data is in its
  evidence, every number comes from it, and the sentence reports rather than predicts.

## 6. Input, output and errors

- Pydantic validates every request body, query parameter and configuration blob.
- SQLAlchemy parameterised queries only; no raw SQL built from input.
- Error responses never include stack traces, SQL or secrets. A request ID links the
  user-visible error to server logs.
- CORS allows only origins listed in `CORS_ORIGINS`.
- Security headers on API responses: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, and `Content-Security-Policy: default-src 'none'`. The interactive
  API docs are not served in production.
- The dashboard sends a Content Security Policy (self only, no framing, no plugins),
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and
  `Permissions-Policy`. HSTS is set by the TLS terminator.
- After sign-in the dashboard only follows `next=` paths on its own origin.

## 7. Audit logging

Append-only `audit_logs` records: login success and failure, logout, token reuse
detection, organisation, member, project and settings changes, and (later) crawls,
approvals and publication records. Records include actor, organisation, action, target,
IP and a small metadata object. Passwords and tokens are never logged. Phase 4 adds
`ai.requested`, `recommendation.updated` and `draft.<action>` for every draft
transition. Phase 5 adds `report.requested`, `report.deleted`, `schedule.updated` and
`crawl.scheduled`. Phase 6 adds `organisation.plan_changed`, `plan.created`,
`plan.updated`, `integration.created|updated|deleted`, `integration.secrets_rotated`,
`retention.applied`, `user.password_reset` and `admin.platform_admin_granted`, and a
platform-wide view for platform administrators (`GET /api/v1/admin/audit-logs`).

## 8. Secrets and configuration

- All secrets come from environment variables. `.env` is git-ignored.
- `.env.example` contains placeholders only.
- The application refuses to start in production mode with a missing, placeholder or
  short `JWT_SECRET`, or with `COOKIE_SECURE=false`.
- `INTEGRATIONS_ENCRYPTION_KEYS` is validated at start-up. Back it up separately from
  the database. `docs/DEPLOYMENT.md` covers rotation and backups.

## 9. Known limitations

The latest review is `docs/SECURITY_REVIEW.md`; its accepted residual risks are listed
here too.

- Login rate limiting is in-process. Run a single API process, or replace it with a
  shared store before horizontal scaling.
- Organisation administrators can still learn that an email already has an account
  through the direct "add a member" form (they cannot see whose). Invitations avoid this
  and let people choose their own passwords; the direct form remains for sites without
  email.
- When email is off, an invitation link shown to the administrator proves only that the
  invitee received it from them, not that they control the address.
- Access tokens stay valid for up to 15 minutes after a password reset.
- The dashboard's policy allows inline scripts (Next.js needs them without nonces).
- Row-level security in PostgreSQL is not enabled. Isolation is enforced in the
  application layer and covered by tests, including a suite that walks every route.
- JavaScript rendering is limited to the crawl scope: scripts on CDNs or other hosts are
  not fetched, so pages that need them render without them.
- Grounding checks are pattern-based. They catch invented numbers, unknown issue ids and
  the listed claim types, but cannot prove that every sentence is true. That is why AI
  output is labelled, drafts need human approval, and protected facts need a source.
- Source references to official documents that are not online are the reviewer's
  attestation, recorded under their name in the approval trail.
- Protected-fact detection is keyword and pattern based, in English. It errs toward
  flagging; content in other languages needs reviewer attention.
- A single-person organisation cannot approve drafts, by design. It needs a second
  member with an approving role.
