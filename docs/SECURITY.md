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

## 4. SSRF protection (crawler, Phase 2)

Blocked destinations: loopback, RFC 1918 private ranges, link-local (including
`169.254.169.254` and other metadata endpoints), CGNAT `100.64.0.0/10`, multicast,
reserved and unspecified addresses, IPv6 equivalents including unique-local and
IPv4-mapped forms. Only `http` and `https` on ports 80 and 443 (plus explicitly
configured ports) are allowed. Every hostname is resolved, every resolved address
is checked, and the connection is made to the checked address so DNS rebinding
cannot swap it. Redirects are followed manually with the same checks on each hop.
The crawler only fetches hosts in the project's scope.

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
approvals and publications. Records include actor, organisation, action, target,
IP and a small metadata object. Passwords and tokens are never logged.

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
