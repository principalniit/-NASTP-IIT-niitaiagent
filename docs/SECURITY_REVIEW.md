# Security Review: claude/zen-maxwell-11wg4z  (2026-09-29)

Scope: the whole repository before the first production deployment (end of Phase 6). The
review looked closely at the Phase 4 to 6 additions:
- the AI layer (prompt injection, grounding, tools);
- drafts and approvals;
- reports (HTML and PDF rendering, logo fetch);
- schedules;
- plans and usage limits;
- integrations and credential encryption;
- retention;
- the platform audit log;
- the CLI.

It also re-checked authentication, sessions, tenant isolation, SSRF, configuration
defaults, security headers, the frontend, CI and dependencies. Three independent
read-only reviews produced the candidate findings. Each finding was then confirmed
against the code before it was fixed. Every fix has a regression test.

Verdict: **Clear to deploy.** Every Critical, High and Medium finding is fixed.
Two items are accepted with a documented residual risk (M8 and L13).

| Severity | Found | Fixed | Accepted |
|----------|-------|-------|----------|
| Critical | 0 | 0 | 0 |
| High | 1 | 1 | 0 |
| Medium | 8 | 7 | 1 (partly fixed) |
| Low | 13 | 12 | 1 (partly fixed) |
| Info | 4 | 2 | 2 |

Tests added: `backend/tests/security/test_accounts_and_login.py`,
`test_drafts_review.py` and `test_reports_review.py`, plus assertions in the existing
AI, plan and end-to-end suites.

## Findings

### [High] H1. Account pre-hijacking across organisations, up to platform-admin takeover
- Location: `backend/app/modules/organisations/service.py` (`add_member`), `backend/app/cli.py` (`create-admin`)
- Issue: an organisation administrator could create an account for any email address
  with a password of their choosing. Emails are not verified. When another
  organisation later added that address, the existing account was attached silently,
  and the first administrator could sign in and read the second organisation's data.
  `create-admin` on an existing address promoted it without changing the password,
  which could turn a planted account into a platform administrator.
- Fix:
  - Only platform administrators can add an existing account to an organisation.
    Others get `409 account_exists`, with no name or id disclosed.
  - `create-admin` on an existing account now sets a new password and signs out every
    session of that account.
  - Test: `test_an_admin_cannot_attach_an_account_another_organisation_created`,
    `test_promoting_an_existing_account_resets_its_password`.

### [Medium] M1. A typed "original" could hide new official facts from review
- Location: `backend/app/modules/drafts/service.py` (`create`), `drafts/protected.py`
- Issue: the check for protected facts (fees, dates, deadlines) compares the proposal
  with the original text. The API took the original from the author, so an editor could
  put the new facts into the "original" as well. The draft was then not protected, and
  approval needed no verified source. The reviewer also saw the forged text as the
  current content.
- Fix:
  - For titles, meta descriptions and H1s, the original is now the value from the latest
    analysed crawl, and the author's text is ignored.
  - Where no crawled value exists (content sections, or pages not crawled), the author's
    text is kept for reference only. Every fact in the proposal then counts as new.
  - The draft records `original_from_crawl`.
  - Test: `test_a_typed_original_cannot_hide_new_facts`.

### [Medium] M2. Separation of duties could be bypassed
- Location: `drafts/service.py` (`transition`, `edit`)
- Issue: only the current version's author and the latest submitter were barred from
  approving. This allowed two bypasses:
  - A no-op edit by an editor made the editor the author of the current version. The
    original author could then approve their own text.
  - After a reject and a reopen, an earlier submitter of the same version could approve.
- Fix:
  - Approval is refused to everyone who created the draft, requested it from the AI
    assistant, wrote any of its versions, or submitted the current version.
  - Edits that change nothing are refused.
  - The dashboard applies the same rule when deciding what to show.
  - Test: `test_nobody_who_wrote_or_submitted_a_draft_approves_it`.

### [Medium] M3. Open redirect after sign-in
- Location: `frontend/src/components/views/login-view.tsx` (`safeNext`)
- Issue: `/login?next=/%5Cevil.com` passed the "starts with one slash" check. Browsers
  read `/\evil.com` as `//evil.com`, so a person could be sent to a phishing page right
  after signing in. `/..//evil.com` was a second variant.
- Fix:
  - Values with backslashes or control characters are refused.
  - The value is resolved the way a browser resolves it. It is used only when the result
    stays on the same origin and is not protocol-relative.
  - End-to-end test: "a sign-in link cannot send people to another site".

### [Medium] M4. Anyone could lock every user out of sign-in
- Location: `backend/app/modules/auth/service.py`, `backend/app/core/request_context.py`
- Issue: with the default `TRUST_PROXY_HEADERS=false`, every sign-in reaches the API
  from the dashboard's loopback address. The per-address limit (20 failures in 5
  minutes) was therefore one counter shared by all users, administrators included. The
  limiter also kept a key for every email ever tried.
- Fix:
  - When proxy headers are not trusted and the address is loopback, only the per-email
    limit applies.
  - Behind nginx with `TRUST_PROXY_HEADERS=true`, per-address limits work as designed.
    `docs/DEPLOYMENT.md` makes this the production set-up.
  - Expired keys are removed.
  - Tests: `test_failed_sign_ins_through_the_dashboard_do_not_lock_everyone_out`,
    `test_direct_clients_are_still_limited_per_address`,
    `test_limiter_forgets_expired_keys`.

### [Medium] M5. A published JWT secret was used when `ENVIRONMENT` was not set
- Location: `backend/app/core/config.py`
- Issue: the production checks ran only when `ENVIRONMENT=production`. Otherwise the API
  signed tokens with a development secret that is published in the source code, or with
  the `.env.example` placeholder. Anyone who knew a user id could forge access tokens.
- Fix:
  - The fixed secret is removed.
  - In production, a missing, placeholder or short secret stops the API from starting.
  - In any other environment, such a secret is replaced by a random secret for the life
    of the process, with a warning. Sign-ins survive restarts through refresh tokens.
  - Test: `test_weak_jwt_secrets_never_sign_tokens`.

### [Medium] M6. A slow logo server could stall the worker for every organisation
- Location: `backend/app/modules/reports/render.py` (`fetch_logo`)
- Issue: the 5-second timeout applied to each read, not to the whole download. A server
  sending one byte every few seconds could hold the single worker loop for weeks. That
  loop runs every organisation's crawls, analyses, reports, schedules and retention.
  Compressed responses could also decompress well past the 512 KB cap.
- Fix:
  - The whole download has a 10-second limit.
  - Only uncompressed responses are accepted, requested with `Accept-Encoding: identity`.
  - The file's signature must match its declared image type.
  - Tests: `test_a_slow_logo_server_cannot_hold_the_worker`,
    `test_logo_must_be_uncompressed_and_a_real_image`.

### [Medium] M7. Retention could remove data a pending analysis needed, and the analysis then invented results
- Location: `backend/app/modules/monitoring/retention.py`, `seo/service.py`, `seo/analysis.py`
- Issue: failed and cancelled crawls counted towards `keep_crawls`, and only the latest
  crawl with a completed analysis was protected. By cancelling a few crawls, someone
  could push the newest completed crawl out of the kept set. Its pages were then
  deleted, and a later analysis ran on zero pages. That analysis marked every issue as
  resolved and inflated the score, which breaks the rule against fabricated metrics.
- Fix:
  - Only completed crawls count towards `keep_crawls`.
  - The newest completed crawl, the latest analysed crawl, and any crawl with an
    analysis queued or running are never pruned.
  - Analysis refuses a crawl whose page data was removed, both in the API and in the
    worker.
  - Tests: `test_cancelled_crawls_cannot_push_data_out`,
    `test_a_pruned_crawl_cannot_be_analysed`.

### [Medium] M8. Organisation admins could look up accounts across organisations (partly fixed, accepted)
- Location: `organisations/service.py` (`add_member`)
- Issue: adding a member by email showed whether an account existed and returned its
  name and id, whatever organisation it belonged to.
- Fix: after H1, organisation administrators get only `account_exists`, with no name,
  id or membership details.
- Accepted residual: an organisation administrator can still learn that an email has an
  account. Hiding that too needs invitation emails, and email delivery is not connected.
  Invitations are planned (see `docs/IMPLEMENTATION_PLAN.md`).
- Update (October 2026): invitations are now in place (`modules/invitations/`). Existing
  accounts join by signing in and accepting, and new people choose their own password.
  The direct add form keeps the residual for sites without email.

### [Low] L1. The Q&A agent could ground answers on its own tool arguments
- Location: `backend/app/modules/ai/agent.py`
- Issue: the arguments the model sent to tools, including calls to unknown tools, were
  stored in the evidence. Grounding checks then treated numbers and issue ids in those
  arguments as facts, so an invented number could pass.
- Fix:
  - Grounding uses only what the tools returned. Tool arguments and error messages are
    excluded.
  - Stored arguments are capped at 2,000 characters.
  - Test: `test_answers_are_grounded_on_tool_results_not_tool_arguments`.

### [Low] L2. Administrators could turn on destructive retention
- Location: `organisations/service.py` (`update`)
- Issue: the retention policy deletes data permanently, and it was documented as
  owner-only. In practice any holder of `org:update` could set it, and the audit entry
  did not record the change.
- Fix:
  - Only owners (and platform administrators acting as owners) can change the policy.
  - The audit entry records the old and new policy.
  - The Settings page disables the fields for everyone else.
  - Test: `test_only_owners_change_data_retention`.

### [Low] L3. Platform administrators could read integrations of organisations they are not members of
- Location: `backend/app/modules/integrations/router.py`
- Issue: integrations used `org:update`, which platform administrators hold for every
  organisation. Integration records contain account details (hosts, usernames,
  credential hints).
- Fix:
  - A new permission, `integrations:manage`, is held by owners and admins only.
  - Non-members get 404.
  - Test: `test_platform_admins_do_not_see_integrations_of_other_organisations`.

### [Low] L4. The dashboard sent no Content Security Policy
- Location: `frontend/next.config.ts`
- Fix:
  - A CSP following the Next.js guide for pages without nonces:
    - `default-src 'self'`
    - no remote scripts, styles, fonts or connections
    - `object-src 'none'`
    - `frame-ancestors 'none'`
    - `base-uri` and `form-action` limited to self
  - HSTS is set at the TLS terminator; see the nginx example in `docs/DEPLOYMENT.md`.
  - End-to-end test: "pages are served with a content security policy".
- Residual: `script-src` allows inline scripts, which Next.js needs for static pages
  without nonces. A nonce- or hash-based policy is a recommendation below.

### [Low] L5. API documentation was public in production
- Location: `backend/app/main.py`
- Fix: `/api/v1/docs` and `/api/v1/openapi.json` are not served when
  `ENVIRONMENT=production`. Test: `test_api_docs_are_not_published_in_production`.

### [Low] L6. Two owners could remove each other at the same time
- Location: `organisations/service.py` (`_owner_count`)
- Fix: the owner rows are locked while they are counted, so the last-owner rule holds
  when requests run concurrently.

### [Low] L7. Draft state changes did not lock the draft
- Location: `drafts/service.py`
- Issue: an edit racing with an approval could leave unreviewed content in an approved
  draft.
- Fix: edits and transitions lock the draft row (`SELECT … FOR UPDATE`) and re-check its
  state after acquiring the lock.

### [Low] L8. Prompt evidence was not bounded
- Location: `backend/app/modules/ai/tools.py`
- Issue: every H1 of a page went into prompts and stored evidence. A hostile page could
  inflate prompts until the model truncated the instructions.
- Fix: at most 10 H1s are included. The other lists were already capped.

### [Low] L9. Usage limits could be exceeded by concurrent requests
- Location: `backend/app/modules/plans/service.py` (`enforce`), `ai/service.py`
- Fix: limit checks take a per-organisation advisory lock that is held until the
  transaction commits. The AI queue cap is checked under the same lock.

### [Low] L10. The monthly report limit could be reset by deleting reports
- Location: `plans/service.py`
- Fix: report usage is counted from the append-only audit log (`report.requested`), so
  deleting reports, or retention removing them, does not give quota back. Test:
  addition to `test_crawls_ai_and_reports_are_limited`.

### [Low] L11. The PDF renderer ran without Chromium's sandbox
- Location: `backend/app/modules/reports/pdf.py`
- Issue: Chromium decodes the tenant's logo inside the worker process, which holds the
  database credentials and keys.
- Fix:
  - Chromium's sandbox is used whenever the worker does not run as root. When a host
    cannot start the sandbox, the renderer falls back with a logged warning.
  - JavaScript remains off and every request remains blocked.
  - Logos must match their image signature (M6).
  - The deployment guide runs the worker as an unprivileged user.

### [Low] L12. Credential hints revealed part of short passwords
- Location: `backend/app/modules/integrations/service.py`
- Fix: only credentials of 24 characters or more (API keys, tokens) show their last four
  characters. Shorter ones show "set".

### [Low] L13. Any text was accepted as a verified source (partly fixed, accepted)
- Location: `drafts/service.py` (`_check_source`)
- Issue: approving a protected draft accepted any non-empty source reference.
- Fix:
  - A web address must now be an HTTPS page on one of the project's approved sources,
    at or below the source's path.
  - Test: `test_source_addresses_must_be_on_an_approved_source`.
- Accepted: official documents that are not online, such as a signed notice, are still
  cited by name and reference number. The reviewer attests to them in the append-only
  approval trail, under their own name. Two-person approval stays mandatory.

### [Info] I1. AI output that failed grounding was still returned by the API
- Fix: output that fails grounding is no longer stored. Only the list of violations is
  kept, for diagnosis.

### [Info] I2. CI checkout kept its token in the workspace
- Fix: `persist-credentials: false` on every checkout. The workflow token is already
  read-only.

### [Info] I3. Access tokens outlive a password reset by up to 15 minutes (accepted)
- A reset revokes every refresh token. Deactivated users are refused on every request.
  A stolen access token can still be used until it expires, 15 minutes at most.

### [Info] I4. Queued AI tasks do not re-check the requester's membership (accepted)
- A task queued by a member who is then removed still runs. Its output is visible only
  to current members, and drafts still need approval.

## Checked and clear

- **Tenant isolation.** Every tenant-owned route returns 404 for another
  organisation, and the data is left unchanged. This is checked by the route-walking
  suite `tests/security/test_tenant_matrix.py`. Every AI tool query is scoped by project
  and organisation.
- **Authentication and sessions:**
  - JWT: the algorithm is pinned, and issuer, audience, expiry and type are checked.
  - Refresh tokens: random, stored hashed, rotated under a lock, with reuse detection
    that revokes the whole family.
  - Cookies: HttpOnly, SameSite=Strict, scoped to `/api/v1/auth`, Secure in production.
  - Passwords: Argon2id with rehash on sign-in.
  - Sign-in: dummy-hash timing and generic errors.
- **CSRF.** Refresh and logout require `X-Requested-With`. Every other route uses
  bearer tokens.
- **XSS:**
  - React escapes all output, and `dangerouslySetInnerHTML` is never used.
  - The report template autoescapes, with no `|safe`.
  - Reports are shown in `iframe sandbox=""` and carry their own restrictive CSP.
  - The PDF footer is escaped.
- **SSRF:**
  - The crawler, sitemaps and logo fetch all go through the guarded transport. It checks
    every hop and every DNS answer, and connects to the checked IP.
  - Environment proxies are ignored.
  - Reports never contact the network from Chromium.
- **Secrets:**
  - Integration credentials are encrypted with Fernet and MultiFernet, in a deferred
    column that is never returned or logged.
  - Keys are validated at start-up, and rotation is tested.
  - No secrets are in the repository.
- **Injection.** Queries go through the SQLAlchemy ORM with bound parameters. No shell
  commands take user input. `Content-Disposition` filenames are restricted to safe
  characters.
- **Errors.** Error responses are generic with a request id. Details go to the logs.
- **Dependencies.** `pip-audit` and `pnpm audit --prod` report no known vulnerabilities.
  CI actions are pinned to commit SHAs, and the workflow token is read-only.

## Recommendations

Non-blocking, ordered by value.

1. **Invitations with acceptance.** Done in October 2026, using the operator's own SMTP
   server (see M8).
2. **A nonce- or hash-based CSP** for the dashboard, removing `'unsafe-inline'` from
   `script-src`. The cost is that pages are rendered dynamically.
3. **A shared rate-limit store** (PostgreSQL or Redis) before running more than one API
   process. Until then, run a single API process, as the deployment guide says.
4. **Invalidate access tokens on password change**, with a per-user token version that
   is checked on each request.
5. **Pin the Ollama image** in `docker-compose.yml` to a tested version.
6. **Render PDFs in a separate low-privilege process or container** that has no database
   credentials.
