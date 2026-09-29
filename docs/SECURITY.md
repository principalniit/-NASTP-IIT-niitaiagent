# Security

Security design and operating notes. Report suspected vulnerabilities privately to
the project owner (principal@niit.edu.pk). Do not open public issues for them.

## 1. Threat model summary

| Asset | Threat | Primary controls |
|-------|--------|------------------|
| Tenant data | Cross-organisation access by ID tampering | Backend membership check on every request; `organisation_id` on every tenant row; 404 for foreign resources; isolation tests |
| User accounts | Credential stuffing, token theft | Argon2id hashing, login rate limiting, short-lived access tokens, rotating refresh tokens with reuse detection, `HttpOnly` cookies |
| Internal network | SSRF through the crawler | Scheme and port allowlist, DNS resolution and IP blocklist, IP pinning, per-redirect revalidation, domain scope |
| Target websites | Being overloaded by our crawler | robots.txt, delay, low concurrency, page and depth caps |
| Institutional reputation | AI-fabricated claims | Grounded prompts, output validation, human approval, no automatic publishing |
| Secrets | Leakage in code, logs, errors | `.env` only, `.env.example` placeholders, redacted logs, generic error bodies |
| Supply chain | Malicious or vulnerable packages | Minimal dependencies, lockfiles, `pip-audit` and `pnpm audit` in CI |

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
- Deactivated users cannot log in or refresh.

## 3. Authorisation

- Roles: platform administrator (user flag), and per organisation: owner, admin,
  SEO manager, editor, viewer.
- All permissions are declared in one map and checked by a shared FastAPI
  dependency. The frontend hides actions a role cannot perform, but the backend is
  the only enforcement point.
- An organisation must always keep at least one owner. Only owners can grant or
  remove the owner role.

## 4. SSRF protection (crawler, Phase 2)

Blocked destinations: loopback, RFC 1918 private ranges, link-local (including
`169.254.169.254` and other metadata endpoints), CGNAT `100.64.0.0/10`, multicast,
reserved and unspecified addresses, IPv6 equivalents including unique-local and
IPv4-mapped forms. Only `http` and `https` on ports 80 and 443 (plus explicitly
configured ports) are allowed. Every hostname is resolved, every resolved address
is checked, and the connection is made to the checked address so DNS rebinding
cannot swap it. Redirects are followed manually with the same checks on each hop.
The crawler only fetches hosts in the project's scope.

## 5. Input, output and errors

- Pydantic validates every request body, query parameter and configuration blob.
- SQLAlchemy parameterised queries only; no raw SQL built from input.
- Error responses never include stack traces, SQL or secrets. A request ID links the
  user-visible error to server logs.
- CORS allows only origins listed in `CORS_ORIGINS`.
- Security headers on API responses: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, and a restrictive `Content-Security-Policy` for docs pages.

## 6. Audit logging

Append-only `audit_logs` records: login success and failure, logout, token reuse
detection, organisation, member, project and settings changes, and (later) crawls,
approvals and publications. Records include actor, organisation, action, target,
IP and a small metadata object. Passwords and tokens are never logged.

## 7. Secrets and configuration

- All secrets come from environment variables. `.env` is git-ignored.
- `.env.example` contains placeholders only.
- The application refuses to start in production mode with the development
  default `JWT_SECRET` or with `COOKIE_SECURE=false`.

## 8. Known limitations

- Login rate limiting is in-process. It does not coordinate across multiple API
  instances. Replace with a shared store before horizontal scaling.
- Row-level security in PostgreSQL is not enabled. Isolation is enforced in the
  application layer and covered by tests.
- Integration credentials (Phase 6) will need encryption at rest with a key held
  outside the database.
