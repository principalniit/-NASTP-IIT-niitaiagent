# Error handling

How the platform reports failures: to API clients, on screen, in background jobs and in
logs. It describes the code as it is; `docs/SECURITY.md` section 6 and
`docs/ARCHITECTURE.md` section 12 give the security rules this follows.

## 1. Principles

- **Generic messages for people, details in logs.** Users see a short message that says
  what happened and, where possible, what to do. Stack traces, SQL and exception details
  go to the server logs only.
- **Every API response carries a request ID.** It is in the `X-Request-ID` header and in
  every error body, and the dashboard shows it as "Reference". The same ID is on the log
  lines and audit entries for that request.
- **No secrets in errors or logs.** Passwords, tokens, integration credentials and SMTP
  credentials are never returned or logged. A mail failure is logged by exception type
  only. Google's error bodies are neither shown nor logged; people see a fixed
  explanation per status.
- **Background failures are stored, not raised.** A failed crawl, analysis, AI task,
  report or Search Console import is marked `failed` with a safe message that the
  dashboard shows.
- **Missing data is shown as missing.** When data is unavailable (no analysed crawl, no
  Search Console connection, AI off), screens show an empty state that says so. Nothing
  is estimated or filled in.
- **The core works without AI.** AI being off or unreachable never fails a crawl,
  analysis or report.

## 2. API error format

Every error from the API has this JSON body (`backend/app/core/errors.py`):

```json
{
  "error": {"code": "not_found", "message": "Project not found", "details": null},
  "request_id": "3f2c9a…"
}
```

- `code` is a stable, machine-readable string (section 3).
- `message` is safe to show to the user.
- `details` is `null` or, for validation errors, a list of
  `{"loc": [...], "msg": "...", "type": "..."}` entries. Service-level validation errors
  use the same `loc` and `msg` keys without `type`.
- `request_id` matches the `X-Request-ID` response header.

The request ID middleware (`backend/app/main.py`) accepts an incoming `X-Request-ID` only
if it matches `^[A-Za-z0-9-]{8,64}$`; otherwise it generates a new one. A 401 response
also carries `WWW-Authenticate: Bearer`.

Exception handlers, registered in `register_error_handlers`:

| Exception | Status | Code |
|-----------|--------|------|
| `AppError` and subclasses | the class's status | the class's code, or the `code=` passed |
| `RequestValidationError` (body, query or path fails Pydantic) | 422 | `validation_error` |
| Starlette `HTTPException` (unknown route, wrong method) | 404 / 405 / other | `not_found` / `method_not_allowed` / `http_error` |
| Any other exception | 500 | `internal_error`, message "An unexpected error occurred"; traceback logged |

### HTTP status mapping

| Status | Meaning here | Raised by |
|--------|--------------|-----------|
| 400 | The request is understood but cannot be done as asked | `AppError` (default code `bad_request`, or a specific code) |
| 401 | Not signed in, or the token or session expired | `UnauthorizedError` |
| 403 | Signed in, member of the organisation, but the role does not permit it | `ForbiddenError` |
| 404 | Not found, or belongs to another organisation | `NotFoundError`, unknown routes |
| 405 | Wrong method for the route | Starlette |
| 409 | Conflicts with the current state, a plan limit or a missing prerequisite | `ConflictError`, `PlanLimitError`, `EncryptionUnavailableError` |
| 422 | Request schema validation failed | FastAPI |
| 429 | Too many attempts or too many queued jobs | `RateLimitedError` |
| 500 | Unhandled error | catch-all handler |

The API never returns 503. `/api/v1/health` always answers 200 and reports
`"status": "degraded"` with `"database": "unavailable"` when PostgreSQL cannot be reached;
AI being off or unreachable does not degrade it.

### Tenant isolation: 404, not 403

The shared permission dependencies (`backend/app/modules/organisations/dependencies.py`)
return 404 for anything outside the caller's organisations: an organisation they are not a
member of, a project, crawl, issue, draft, AI analysis, recommendation, report or
integration of another organisation, a deleted project, or an inactive organisation. This
avoids confirming that a foreign resource exists. A 403 ("Your role does not permit this
action") is returned only to a member of the same organisation whose role lacks the
permission. Platform administrators get no implicit access to project data.

`tests/security/test_tenant_matrix.py` walks every scoped route as an owner of another
organisation and requires 404 from each, with no data changed.

## 3. Error code reference

Only codes that exist in the code. Messages are quoted where they are fixed.

| Code | Status | When | What the user sees |
|------|--------|------|--------------------|
| `bad_request` | 400 | Default for `AppError` without a code, e.g. an unknown draft action | "Unsupported action" |
| `validation_error` | 422 | Request body, query or path fails schema validation | "Request validation failed"; form fields marked from `details` |
| `validation_error` | 422 | Service checks (`ValidationAppError`): `name` or `root_url` set to null; crawl settings above the organisation's caps; invalid integration settings; draft page address not on the project's site; issues from another project; unsetting the default plan | The message, e.g. "Crawl settings exceed organisation limits", with per-field `details` |
| `unauthorized` | 401 | No token, invalid or expired token, wrong login, expired or reused refresh token | "Authentication required", "Invalid or expired access token", "Invalid email or password", "Session expired" |
| `forbidden` | 403 | Role lacks the permission; platform-admin-only action; missing `X-Requested-With` on refresh or logout; invitation for another email; an author approving their own draft; non-owner changing the owner role or data retention | The message; the dashboard's `ErrorState` replaces it with "Your role does not allow access to this information." |
| `not_found` | 404 | Missing or foreign resource; unknown route; invalid or expired reset or invitation link | e.g. "Project not found", "This reset link is not valid or has expired", "This invitation is not valid or has expired" |
| `method_not_allowed` | 405 | Wrong HTTP method | "Method Not Allowed" |
| `http_error` | other | Any other Starlette HTTP exception | Starlette's text |
| `conflict` | 409 | State conflicts: crawl already queued or running; analysis already queued; only the latest completed crawl can be analysed; page data pruned by retention; duplicate project domain or organisation slug; already a member; last owner; draft in the wrong state; verified source required for official information; unchanged content; report still generating; sync already running | The specific message |
| `rate_limited` | 429 | Too many failed logins (per email and per address); too many queued AI tasks (`AI_MAX_ACTIVE_JOBS_PER_ORG`, default 3); three reports already generating for the organisation | "Too many failed login attempts. Try again later.", "Too many AI tasks are already queued for this organisation. Try again shortly.", "Several reports are already being generated. Try again shortly." |
| `internal_error` | 500 | Unhandled exception | "An unexpected error occurred" and the reference |
| `plan_limit_reached` | 409 | One more project, member, crawl, AI task or report would exceed the organisation's plan | "The {plan} plan allows {n} {things}, and this organisation has reached it. A platform administrator can change the plan." |
| `encryption_key_missing` | 409 | Saving an integration credential with no `INTEGRATIONS_ENCRYPTION_KEYS` | "Credentials cannot be stored until the server operator sets INTEGRATIONS_ENCRYPTION_KEYS." |
| `invalid_password` | 400 | Change password with a wrong current password | "Current password is incorrect" |
| `password_unchanged` | 400 | New password equals the current one | "New password must differ from the current one" |
| `account_exists` | 409 | Adding an existing account directly to an organisation; accepting an invitation as a new account when one exists | "This email already has an account. Send an invitation instead…" / "An account already exists for this email. Sign in to accept the invitation." |
| `account_details_required` | 400 | Platform admin adds a member with no account and no name or password | "No account exists for this email. Provide full_name and an initial password." |
| `ai_disabled` | 409 | AI requested while off for the platform or organisation, or no model configured | "AI is disabled on this platform.", "AI is turned off in organisation settings.", "No Ollama model is configured." |
| `not_analysed` | 409 | AI task or report requested before any analysed crawl | "Crawl and analyse this project before using the AI assistant" / "…before generating a report" |
| `not_enough_crawls` | 400 | Crawl comparison without an earlier analysed crawl | "At least two analysed crawls are needed for a comparison" |
| `not_ready` | 409 | HTML of a report that has not completed | "This report is not ready yet" |
| `pdf_not_ready` | 409 | PDF requested while pending, unavailable or failed | The stored `pdf_error`, or "The PDF for this report is not ready" |
| `invalid_credential` | 400 | Search Console key rejected when saved | e.g. "The JSON key must be a Google service account key." |
| `wrong_provider` | 400 | Search Console action on another integration type | "This integration is not Google Search Console" |
| `no_credential` | 409 | Test or sync before a key is saved | "Save the service account JSON key for this integration first." |
| `credential_unreadable` | 409 | The stored key cannot be decrypted with the configured keys, or is no longer a valid service account key | "The stored secret cannot be decrypted with the configured keys", or the key check's message, such as "The credential is not a JSON key file." |
| `search_console_error` | 400 | *Test connection* fails | The fixed explanation from section 7 |

Frontend-only codes, set by `frontend/src/lib/api.ts` when the response is not JSON:

| Code | When | Message |
|------|------|---------|
| `api_unreachable` | A non-JSON 5xx, which comes from the dashboard's proxy when the API is down | "The API server is not responding. Check that it is running (and that the database is upgraded), then try again." |
| `http_error` | Any other non-JSON error | The HTTP status text, or "Request failed" |

## 4. Background jobs

The worker (`backend/app/worker.py`) claims queued work from PostgreSQL with
`FOR UPDATE SKIP LOCKED`, so several workers can run safely. Each kind of job catches its
own failures; an unexpected exception is logged with its traceback and the job is marked
failed with a fixed message. The loop itself also catches and logs errors ("Worker loop
error") and keeps running.

| Job | Expected failure (message shown) | Unexpected failure (message shown) |
|-----|----------------------------------|-----------------------------------|
| Crawl | Crawl completes with notes (section 5) | "The crawl failed because of an internal error. See worker logs." |
| SEO analysis | `AnalysisError`, e.g. "Only completed crawls can be analysed", "This crawl's page data was removed under the retention policy", "A newer crawl of this project has already been analysed" | "The analysis failed because of an internal error. See worker logs." |
| AI task | `AIError` or tool error (section 6) | "The AI task failed because of an internal error. See worker logs." |
| Report | `AppError` while building, e.g. "The project no longer exists." | "The report failed because of an internal error. See worker logs." |
| Search Console import | `SearchConsoleError` or credential conflict (section 7) | "The sync failed because of an internal error. See worker logs." |

Where the message appears: crawl `error_message`, crawl `analysis_error` (shown as
"Failed: …" on the crawl page), AI analysis `error`, report `error` and `pdf_error`, and
Search Console sync `error`.

### Heartbeats and stale jobs

- A running crawl writes progress and `heartbeat_at` about once a second. Three
  consecutive failed writes stop the crawl, which is then marked failed rather than
  completed. A page that cannot be stored stops it the same way.
- `recover_stale_jobs` runs when the worker starts and then every 60 seconds. It marks as
  failed:

| Job | Considered stale when | Message |
|-----|----------------------|---------|
| Crawl (running or cancelling) | No heartbeat for `WORKER_STALE_AFTER_SECONDS` (default 300) | "The worker running this crawl stopped unexpectedly." |
| SEO analysis | Running and not updated for `WORKER_STALE_AFTER_SECONDS` | "The worker running this analysis stopped unexpectedly." |
| AI task | Running longer than `AI_TIMEOUT_SECONDS` × 16 (48 minutes at the default 180) | "The worker running this AI task stopped unexpectedly." |
| Report | Running longer than 30 minutes | "The worker generating this report stopped unexpectedly." |
| Search Console import | Running longer than 30 minutes | "The worker running this sync stopped unexpectedly." |

### Retries

Failed jobs are not retried automatically. The user starts a new crawl, analysis, AI task,
report or import. The only automatic retries are inside an AI task (section 6). Jobs that
stay *Queued* mean no worker is running.

### Start-up checks

The API and the worker both check the database schema at start-up and refuse to start
with "The database schema is out of date (database: …; this version needs: …). Run
`uv run alembic upgrade head` in the backend folder, then start again."

## 5. Crawler

### Page fetch statuses

Each crawled address gets a `fetch_status` (`backend/app/modules/crawler/models.py`):

| Status | Meaning |
|--------|---------|
| `fetched` | A response was received. HTTP 4xx and 5xx pages are `fetched` with their status code, so the rules engine can report them |
| `not_modified` | The server answered 304; data is copied from the previous crawl |
| `blocked_by_robots` | robots.txt does not allow this crawler |
| `blocked_destination` | The SSRF guard refused the address, e.g. "Destination resolves to a non-public address", "Port 22 is not allowed" |
| `redirect_out_of_scope` | Redirects to a host outside the project |
| `skipped_content_type` | A 2xx response that is not HTML |
| `too_large` | Body above the size limit |
| `error` | No usable response; the page's `error` says why |

### Plain-language fetch errors

`describe_error` in `fetcher.py` turns network exceptions into short explanations used in
page errors and crawl notes:

| Cause | Text |
|-------|------|
| Certificate verification failed | "The site's security certificate could not be verified (…)", adding "the server does not send its full certificate chain" for a missing intermediate |
| Other TLS failure | "The secure (TLS) connection to the server failed" |
| DNS | "The site's name could not be found (DNS)" |
| Connection refused | "The server refused the connection" |
| Connection reset | "The server closed the connection" |
| Invalid or empty response | "The server sent an invalid or empty response" |
| Other connection failure | "Could not connect to the server" |
| Anything else | "Request failed: {exception type}" |

The fetcher adds "Request timed out", "More than N redirects" and "Redirect to an
unsupported or invalid URL". An exception while processing one page is logged and the page
is recorded as `error` with "Internal error while processing this page"; the crawl goes on.

### robots.txt

Following RFC 9309: a 2xx robots.txt is parsed; a 4xx means there is none and everything is
allowed; a redirect to another host is ignored with a note. Anything else (5xx, timeout,
connection failure) makes the host unreachable: no pages on it are crawled, and the note
reads "robots.txt on {host} could not be fetched ({reason}); as required by RFC 9309 no
pages on this host were crawled." The crawl's `robots_status` is `found`, `not_found` or
`unreachable`.

### Crawl notes and start-page diagnostics

A crawl that runs but finds little still completes. The reason is stored in its `warnings`
and shown under "Notes about this crawl". When the start page is the problem, that note
comes first:

| Situation | Note (shortened) |
|-----------|------------------|
| Start page blocked by robots.txt | "robots.txt on {host} does not allow this crawler ({agent}) to fetch the start page… Only the site owner can allow it." |
| Start page answers 4xx or 5xx | "The start page answered HTTP {code}, so no links could be followed…" |
| Start page cannot be fetched | "The start page could not be fetched ({reason}). Check the address and that the site is up…" |
| Start address is private or reserved | "…the crawler refuses for safety. Only public websites can be crawled." |
| Start page too large, or not HTML | "The start page is larger than the crawler's size limit…" / "The start page is not an HTML page ({type})…" |
| Start address redirects off-site | "The start address redirects to {url}, which is outside this project's site… add its host to the allowed extra hosts" |
| Fewer than three links and at most three pages found | Suggests turning on JavaScript rendering, or (with rendering on) adding a sitemap |
| Links are #-addresses (`#/about`) | Explains that search engines see one page and that the site needs real addresses and server-side rendering |

Other notes: the page limit was reached (orphan pages are then not identified); the crawl
stopped at the maximum duration; only the first N sitemap files were read; JavaScript
rendering was unavailable or failed on some pages.

Each sitemap gets an entry in the crawl's `sitemaps` list with `status` `ok`, `not_found`,
`error` or `skipped` and an `error` text, for example "HTTP 500", a parse error, "Sitemap
is on a host outside the crawl scope", or, when it returns HTML, "The sitemap address
returns a web page, not a sitemap…".

### JavaScript rendering failures

Rendering never fails a crawl. If Chromium is missing, the crawl adds "JavaScript rendering
was requested but is not available: …" with the install commands, and analyses pages as
served. If single pages fail, it adds "{n} page(s) could not be rendered with JavaScript
and were analysed as served. First reason: …". Reasons: "The page could not be rendered in
time", "The rendered page is too large", "The page's scripts tried to open another page
({url})", "The renderer is not running".

### Diagnosing a crawl

`uv run python -m app.cli crawl-check --url <site> [--render]` fetches robots.txt and the
start page with the crawler's own guarded client and prints each step and where it stops.

## 6. AI

AI runs only in the worker (`backend/app/modules/ai/runner.py`). `AIError` messages are
written to be shown.

| Failure | Message | Behaviour |
|---------|---------|-----------|
| AI off or no model | `ai_disabled` at request time (section 3) | Request refused with 409 |
| Ollama not reachable | "The AI service (Ollama) is not reachable." | Task failed |
| No reply within `AI_TIMEOUT_SECONDS` (default 180) | "The AI model did not respond in time." | Task failed |
| Model not pulled (HTTP 404) | "Model '{model}' is not installed in Ollama." | Task failed |
| Other HTTP status | "The AI service returned HTTP {code}." | Task failed |
| Reply is not Ollama's JSON | "The AI service returned an unexpected response." | Task failed |
| Reply does not match the JSON schema | "The AI reply was not valid after 2 attempts ({errors})." | Retried once with the validation errors, then failed |
| Reply not grounded in the evidence | "The AI reply included claims not supported by the project data, so it was not used." (questions: "The answer included claims not supported by the project data.") | Retried once with the grounding report, then failed |
| Question needs too many steps | "The assistant did not reach an answer within the allowed number of steps." | Task failed |
| Project deleted meanwhile | "The project no longer exists." | Task failed |

For every task, finished or failed, the record keeps the status, `error`, attempts, usage
metrics, the evidence and the grounding report. Output that fails grounding is never
stored, so no screen or API can show it.

AI status is reported by `/api/v1/health` and `/api/v1/organisations/{id}/ai/status`. When
Ollama is down the dashboard shows "The AI assistant is unavailable" with "The AI service
is not responding (Ollama is not reachable). Requests will fail until it is back." When AI
is off it says so and that crawling, analysis, scores and issues work without it.

## 7. Integrations and email

### Search Console

`google.py` raises `SearchConsoleError` with fixed messages. Google's response bodies are
never shown or logged; a refused sign-in is logged with its status code only.

| Situation | Message |
|-----------|---------|
| Not a JSON file, not a service account key, no valid email, no private key | "The credential is not a JSON key file." and similar, at save time (`invalid_credential`) |
| Private key cannot sign | "The private key in the JSON key file is not valid." |
| Google refuses the key (400 or 401 at sign-in) | "Google rejected the service account key. Create a new key and save it again." |
| 403, or no permission level | "The service account has no access to this Search Console property. Add its email as a user of the property in Search Console, then try again." |
| 404 | "Search Console has no property with this address. Use the exact property…" |
| 429 | "Google's daily request quota is used up. Try again later." |
| Other status | "Search Console could not be reached (HTTP {code})." |
| Network failure | "Google could not be reached to sign in." / "Search Console could not be reached." |
| Integration deleted before the import ran | "The integration no longer exists." |

*Test connection* returns these as `search_console_error`. An import stores them in the
sync's `error` with status `failed`, together with `no_credential`, `credential_unreadable`
and `encryption_key_missing` failures. Without a connection, Search Console screens show
"Search Console is not connected" and no figures. See `docs/SEARCH_CONSOLE.md`.

### Email

`backend/app/core/mailer.py` sends through the operator's SMTP server. With `SMTP_HOST` or
`SMTP_FROM` empty, email is off and nothing is sent. A send failure is logged as "Email
could not be sent" with the exception type only, and never fails the request:

- An invitation still returns its link, with `email_sent: false`, so an administrator can
  share it by hand.
- A password reset request always answers 202 with the same message. The email is sent
  after the response, so neither a failure nor its timing reveals whether an account
  exists.

`uv run python -m app.cli send-test-email --to <address>` sends one message and, on
failure, prints "Not sent ({type}). " followed by a hint from `failure_hint`: wrong
username or password (with Gmail, use an app password), sender refused, recipient refused,
TLS failure (use 587 with STARTTLS or 465), or mail server unreachable. The hint never
contains credentials. See `docs/EMAIL.md`.

## 8. Frontend handling

- `frontend/src/lib/api.ts` turns every failed response into an `ApiError` with `status`,
  `code`, `message`, `details` and `requestId` (from the body, or else the `X-Request-ID`
  header, so errors that are not JSON keep their reference too). A 401 triggers one session
  refresh and a retry; if the refresh fails, the session is cleared with its cached data
  and the dashboard returns to the sign-in state.
- A non-JSON 5xx becomes `api_unreachable` (section 3). It has a request ID only when the
  response carried the header; when the API is down there is none.
- Sign-in (and signing in from an invitation) shows the server's message for 401, 429 and
  `api_unreachable` (`signInErrorText` in `lib/api.ts`), and "Sign-in is unavailable right
  now. Please try again." otherwise.
- TanStack Query does not retry `ApiError`s below 500; other failures are retried up to
  twice (`components/providers.tsx`).
- `ErrorState` (`components/app/states.tsx`) shows "Could not load data", the message (or
  a fixed role message for 403), "Reference: {request ID}" and a *Retry* button when the
  view passes `onRetry`. Non-API errors show "Something went wrong while loading this
  information."
- Detail views show an `EmptyState` such as "Report not found" for a 404 instead of an
  error. `EmptyState` is also used wherever data does not exist yet, for example "No
  analysed crawl yet".
- Forms use `applyApiErrors` (`lib/form-errors.ts`): each `details` entry is attached to
  its field by `loc`, and anything unmatched goes into the form's alert. Some views use a
  local `errorText` helper that shows the message, plus field details for integrations.
- Sign-in shows the API message only for 401 and 429. Anything else shows "Sign-in is
  unavailable right now. Please try again."
- Specific codes change the flow: `account_exists` when accepting an invitation, and
  `account_details_required` when an administrator adds a member.

## 9. Logging and troubleshooting

The API and the worker log JSON lines to standard output (`backend/app/core/logging.py`),
at `LOG_LEVEL` (default `INFO`). Fields: `ts`, `level`, `logger`, `msg`, `request_id`
(inside a request), any extra fields such as `crawl_job_id`, `ai_analysis_id`,
`report_id`, `sync_id` or `status`, and `exc` with the traceback. Uvicorn's access log is
limited to warnings.

Where to look:

- Development: the API window (`uv run uvicorn app.main:app --reload`) for request
  errors, the worker window (`uv run python -m app.worker`) for jobs. Search for the
  "Reference" shown on screen to find the request.
- Containers: `docker compose logs -f api worker` in `deploy/`.
- "See worker logs" in a job message means the traceback is in the worker's output.

Common operator errors (more in `README.md` under Troubleshooting):

| Symptom | Fix |
|---------|-----|
| `connection refused` on port 5432 (Windows: `WinError 1225`) | Start PostgreSQL: `docker compose up -d db` |
| "The database schema is out of date" | `uv run alembic upgrade head` in `backend`, then restart the API and worker |
| "The API server is not responding" | Start the API, check `API_ORIGIN`, and check its window for the schema message |
| A crawl, AI task, report or import stays *Queued* | Start the worker |
| "The AI service (Ollama) is not reachable." or "The AI assistant is unavailable" | Start Ollama; `OLLAMA_BASE_URL` defaults to `http://127.0.0.1:11434`; check the model with `ollama list` |
| "The AI model did not respond in time." | Set `AI_TIMEOUT_SECONDS=600` and restart, or use a smaller model or a GPU |
| A crawl stops after one page | Read the crawl notes, then run `uv run python -m app.cli crawl-check --url <site> [--render]` |
| "The stored secret cannot be decrypted with the configured keys" | Keep a single `INTEGRATIONS_ENCRYPTION_KEYS` line in `backend/.env`, restart the API and worker, then save the credential again |
| "Credentials cannot be stored until the server operator sets INTEGRATIONS_ENCRYPTION_KEYS." | Generate a Fernet key and set it (`docs/DEPLOYMENT.md`) |
| Report PDF says it is not installed | `uv run playwright install chromium` in `backend`, then restart the worker |
| `send-test-email` prints "Not sent (SMTPAuthenticationError)" | Use an app password for Gmail or Google Workspace (`docs/EMAIL.md`) |

## 10. Testing

Error paths are covered by the backend suites. Examples:

| Test | Covers |
|------|--------|
| `tests/integration/test_platform.py::test_error_envelope_and_request_id` | Error body, `not_found`, request ID echo and rejection of an unsafe `X-Request-ID` |
| `tests/security/test_tenant_matrix.py::test_every_scoped_route_refuses_other_organisations` | 404 for every scoped route from another organisation |
| `tests/integration/test_auth.py::test_login_is_rate_limited` | 429 after failed logins |
| `tests/integration/test_plans.py::test_crawls_ai_and_reports_are_limited` | `plan_limit_reached` |
| `tests/integration/test_integrations.py::test_no_key_means_no_stored_secrets` | `encryption_key_missing` |
| `tests/integration/test_crawl_api.py::test_stale_and_crashing_jobs_are_failed` | Stale crawl recovery and crash handling |
| `tests/integration/test_crawl_engine.py::test_unreachable_robots_blocks_everything` | RFC 9309 behaviour |
| `tests/integration/test_crawl_engine.py::test_a_start_page_that_answers_an_error_is_explained` and the other start-page tests | Start-page diagnostics |
| `tests/integration/test_crawl_engine.py::test_storage_failure_fails_the_crawl_instead_of_completing` | Storage failure marks the crawl failed |
| `tests/unit/test_fetch_errors.py` | Plain-language fetch errors |
| `tests/security/test_js_rendering.py::test_a_script_that_opens_another_page_is_refused_and_named` | Render failure reason |
| `tests/unit/test_ai_provider.py::test_unreachable_ollama`, `test_invalid_output_twice_fails` | AI provider failures |
| `tests/integration/test_ai_api.py::test_ungrounded_reply_is_retried_then_rejected`, `test_ai_failures_are_reported_not_raised`, `test_worker_contains_crashes_and_recovers_stale_tasks` | AI failures stored, grounding retry, stale AI tasks |
| `tests/integration/test_search_console.py::test_sync_failures_are_explained` | Search Console messages |
| `tests/integration/test_invitations.py::test_a_mail_server_failure_still_gives_the_link` | Email failure does not break invitations or resets |
| `tests/unit/test_send_test_email.py::test_failures_are_explained` | `failure_hint` output |
| `tests/integration/test_schema_check.py::test_an_outdated_database_is_refused_with_the_fix` | Start-up schema check |
