# Deployment guide

This guide covers two supported shapes:

1. **Single Windows machine** (for example a laptop or desktop with an NVIDIA GPU) used by
   a small team on the institute network.
2. **Linux server** behind nginx with HTTPS, managed by systemd. This is the recommended
   production shape.

Both run the same four processes:

| Process | Command (from `backend/` or `frontend/`) | Listens on |
|---------|-------------------------------------------|------------|
| PostgreSQL 16+ | service or Docker container | 127.0.0.1:5432 (or another port) |
| API | `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000` | 127.0.0.1:8000 |
| Worker | `uv run python -m app.worker` | no port |
| Dashboard | `pnpm start` (after `pnpm build`) | 127.0.0.1:3000 |

Ollama (optional) listens on 127.0.0.1:11434. Only the dashboard, and only through the
HTTPS reverse proxy, should be reachable from other machines. The browser never talks to
the API directly: Next.js proxies `/api/v1/*` to `API_ORIGIN`.

The platform works fully without AI. Keep `AI_PROVIDER=none` until Ollama is installed and
tested.

## 1. Secrets and environment

All configuration comes from environment variables or `backend/.env` (never committed).
Start from `backend/.env.example`. The values below are the ones that matter for
production:

| Variable | Production value | Notes |
|----------|------------------|-------|
| `ENVIRONMENT` | `production` | Enables the start-up safety checks below. |
| `DATABASE_URL` | `postgresql+asyncpg://<user>:<password>@127.0.0.1:5432/niit_seo` | Use a dedicated database user with a strong password. |
| `JWT_SECRET` | 48+ random characters | `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The API refuses to start with the development value or fewer than 32 characters. Changing it signs everyone out. |
| `COOKIE_SECURE` | `true` | Required in production; the API refuses to start otherwise. Needs HTTPS. |
| `CORS_ORIGINS` | the public dashboard origin, e.g. `https://seo.niit.edu.pk` | The browser uses the Next.js proxy, so this is a defence-in-depth list. |
| `TRUST_PROXY_HEADERS` | `true` **only** behind nginx configured as in section 3 | Otherwise `false`. Controls the address used for login rate limits and audit logs. |
| `INTEGRATIONS_ENCRYPTION_KEYS` | one Fernet key | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Without it, integration credentials cannot be stored (other integration settings still can). Back it up separately from the database: losing it makes stored credentials unreadable. |
| `CRAWLER_ALLOWED_PRIVATE_NETWORKS` | empty | Only list a private range you own. Loopback and link-local ranges are refused in production. |
| `AI_PROVIDER` | `none` or `ollama` | Each organisation must also turn AI on in its settings. |
| `OLLAMA_DEFAULT_MODEL` | e.g. `llama3.1:8b` | |
| `AI_TIMEOUT_SECONDS` | `180` with a GPU, `600` on CPU | |
| `REPORT_PDF_BROWSER_PATH` | empty, or a Chromium path | Empty uses the browser installed by `uv run playwright install chromium`. |
| `SCHEDULER_ENABLED` | `false` until schedules are wanted | Scheduled crawls run only when this and the project's schedule are both on. |
| `PUBLIC_BASE_URL` | the public dashboard address, e.g. `https://seo.niit.edu.pk` | Used in invitation and password reset links. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | your organisation's mail server and a sending account, e.g. `noreply@niit.edu.pk` | Optional. Use the SMTP service of the email you already have; no third-party service is needed. Port 465 uses TLS directly; 587 uses STARTTLS. Without it, invitation links are shared by hand and resets go through `app.cli reset-password`. |

Protect the file: on Linux `chmod 600 backend/.env` and own it by the service user; on
Windows keep it in a folder only the operator account can read.

The dashboard needs one build-time variable: `API_ORIGIN` (default
`http://127.0.0.1:8000`). It is baked in at `pnpm build`, so rebuild after changing it.

## 2. Single Windows machine

Suitable for one institute team on a trusted network. Tested with Windows 11 and
PowerShell.

### Prerequisites

- Git, Python 3.12 (via `uv`), Node.js 20+ with `pnpm`
  (`npm install -g pnpm`), `uv` (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`).
- PostgreSQL 16+: either Docker Desktop (`docker compose up -d db`) or a native install.
- Optional: Ollama for Windows. With an NVIDIA GPU (for example an RTX 4060 8 GB), install
  the current NVIDIA driver; Ollama uses the GPU automatically. `ollama ps` shows
  `100% GPU` when the model fits in video memory. An 8B model at 4-bit quantisation
  (`llama3.1:8b`) fits in 8 GB; `AI_TIMEOUT_SECONDS=180` is then ample.

### First install

```powershell
git clone <repository-url> niit-seo; cd niit-seo
docker compose up -d db                       # or use a native PostgreSQL

cd backend
Copy-Item .env.example .env                   # then edit .env (section 1)
uv sync --python 3.12
uv run alembic upgrade head
uv run playwright install chromium            # PDF reports (optional)
uv run python -m app.cli create-admin --email principal@niit.edu.pk --name "Principal"
uv run python -m app.cli seed-niit --owner-email principal@niit.edu.pk

cd ..\frontend
pnpm install
pnpm build
```

### Running

Open three PowerShell windows:

```powershell
# 1  (backend\)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
# 2  (backend\)
uv run python -m app.worker
# 3  (frontend\)
pnpm start
```

Then open http://localhost:3000.

To let colleagues on the network use it, put a reverse proxy with HTTPS in front of port
3000 (for example Caddy or nginx for Windows, configured as in section 3) and set
`COOKIE_SECURE=true`. Without HTTPS, keep use on the machine itself: sign-in cookies
would travel unencrypted on the network.

To start everything at logon, create Task Scheduler tasks ("At log on", "Run whether user
is logged on or not") for the three commands, each with the correct "Start in" folder.
Alternatively use a service wrapper such as NSSM.

### Common Windows problems

| Symptom | Fix |
|---------|-----|
| `port is already allocated` or `address already in use` for 5432 | Another PostgreSQL is running. Change the published port in `docker-compose.yml` (e.g. `127.0.0.1:55432:5432`) and `DATABASE_URL` to match. |
| `password authentication failed` | `DATABASE_URL` points at a different PostgreSQL than the one you created. Check the port. |
| `Unknown IANA time zone` | Run `uv sync` again; the `tzdata` package supplies the zone database on Windows. |
| Crawls stay "Queued" | The worker (window 2) is not running. |
| AI tasks time out | Raise `AI_TIMEOUT_SECONDS`, or check `ollama ps` shows the GPU is in use. |

### Moving to another machine

Code comes from Git. Data lives in PostgreSQL, so move it with a backup (section 5):
`pg_dump` on the old machine, `pg_restore` on the new one, then copy `backend/.env`
(including `JWT_SECRET` and `INTEGRATIONS_ENCRYPTION_KEYS`) securely. Ollama models are
downloaded again with `ollama pull`.

## 3. Linux server (recommended production)

Example for Ubuntu 24.04 LTS. Adjust paths as needed.

### Packages and user

```bash
sudo apt install -y postgresql nginx git curl
sudo useradd --system --create-home --home-dir /opt/niit-seo --shell /usr/sbin/nologin niitseo
sudo -u niitseo git clone <repository-url> /opt/niit-seo/app
# Install uv and Node.js 20+ with pnpm for the niitseo user.
```

### Database

```bash
sudo -u postgres createuser --pwprompt niit_seo
sudo -u postgres createdb --owner niit_seo niit_seo
```

PostgreSQL listens on localhost only by default. Keep it that way.

### Application

```bash
cd /opt/niit-seo/app/backend
sudo -u niitseo cp .env.example .env && sudo -u niitseo chmod 600 .env   # edit per section 1
sudo -u niitseo uv sync --frozen
sudo -u niitseo uv run alembic upgrade head
sudo -u niitseo uv run playwright install --with-deps chromium          # PDF reports
sudo -u niitseo uv run python -m app.cli create-admin --email principal@niit.edu.pk --name "Principal"

cd ../frontend
sudo -u niitseo pnpm install --frozen-lockfile
sudo -u niitseo pnpm build
```

### systemd units

`/etc/systemd/system/niit-seo-api.service`:

```ini
[Unit]
Description=NIIT SEO API
After=network.target postgresql.service

[Service]
User=niitseo
WorkingDirectory=/opt/niit-seo/app/backend
ExecStart=/opt/niit-seo/.local/bin/uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/niit-seo
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Run the API as a single process (no `--workers`): the login rate limiter keeps its state
in memory, so several API processes would each allow the full number of attempts.

`niit-seo-worker.service` is the same with
`ExecStart=/opt/niit-seo/.local/bin/uv run --frozen python -m app.worker`,
`KillSignal=SIGTERM` and `TimeoutStopSec=3900`. The worker finishes its current crawl
before exiting (a crawl is capped by `CRAWLER_MAX_DURATION_SECONDS`, 3600 by default).
More than one worker may run; jobs are claimed with row locks.

`niit-seo-web.service` runs `pnpm start` in `/opt/niit-seo/app/frontend` with
`Environment=PORT=3000 HOSTNAME=127.0.0.1`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now niit-seo-api niit-seo-worker niit-seo-web
```

### nginx with HTTPS

Obtain a certificate (for example with certbot), then:

```nginx
server {
    listen 443 ssl http2;
    server_name seo.niit.edu.pk;

    ssl_certificate     /etc/letsencrypt/live/seo.niit.edu.pk/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seo.niit.edu.pk/privkey.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    client_max_body_size 2m;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        # Overwrite, never append the client's own value. Required for TRUST_PROXY_HEADERS=true.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 120s;
    }
}

server {
    listen 80;
    server_name seo.niit.edu.pk;
    return 301 https://$host$request_uri;
}
```

With this in place set `TRUST_PROXY_HEADERS=true` and `COOKIE_SECURE=true`, and restart
the API. The firewall should allow only 80 and 443 (and SSH from administrators):
`sudo ufw allow 'Nginx Full' && sudo ufw allow OpenSSH && sudo ufw enable`.

### Ollama with a GPU (optional)

Install the NVIDIA driver and Ollama (`curl -fsSL https://ollama.com/install.sh | sh`),
then `ollama pull llama3.1:8b`. Ollama binds to 127.0.0.1:11434 by default; keep it there.
Set `AI_PROVIDER=ollama` and `OLLAMA_DEFAULT_MODEL`, restart the API and worker, and turn
AI on per organisation in Settings.

## 4. First sign-in checklist

1. Sign in as the platform administrator created with `create-admin`.
2. Administration: confirm the organisation, its plan (the default `internal` plan has no
   limits), and invite members with the least role they need. With email set up, send a
   test invitation to yourself first.
3. Settings: time zone, report branding, data retention (off by default).
4. Projects: confirm the domain, crawl limits and robots.txt respect.
5. Run a first crawl and check the worker log.
6. Generate a report and open the PDF; if the PDF is unavailable, check
   `REPORT_PDF_BROWSER_PATH` or run `uv run playwright install chromium`.

## 5. Backups and restore

Everything the platform stores is in PostgreSQL. Back it up daily and keep copies off
the server.

```bash
# Backup (custom format, compressed)
pg_dump --format=custom --file=niit_seo-$(date +%F).dump "postgresql://niit_seo@127.0.0.1/niit_seo"

# Restore into an empty database
createdb --owner niit_seo niit_seo
pg_restore --no-owner --role=niit_seo --dbname=niit_seo niit_seo-2026-09-29.dump
```

On Windows with Docker: `docker compose exec db pg_dump -U niit -Fc niit_seo > backup.dump`.

Back up `backend/.env` separately and securely. It holds `JWT_SECRET` and
`INTEGRATIONS_ENCRYPTION_KEYS`; a database restored without the matching encryption key
keeps everything except stored integration credentials, which must then be entered again.
Test a restore at least once a quarter.

## 6. Upgrades

```bash
cd /opt/niit-seo/app
sudo -u niitseo git pull
cd backend && sudo -u niitseo uv sync --frozen
sudo systemctl stop niit-seo-worker          # waits for the current crawl
sudo -u niitseo uv run alembic upgrade head  # take a backup first
cd ../frontend && sudo -u niitseo pnpm install --frozen-lockfile && sudo -u niitseo pnpm build
sudo systemctl restart niit-seo-api niit-seo-web && sudo systemctl start niit-seo-worker
```

Read the release notes in `docs/IMPLEMENTATION_PLAN.md` before upgrading. To roll back,
restore the backup taken before the migration and check out the previous version.

## 7. Operations

- **Logs.** `journalctl -u niit-seo-api -u niit-seo-worker -f`. Logs never contain
  passwords, tokens or integration credentials. Error details stay in logs; users see
  generic messages.
- **Audit log.** Organisation owners see their organisation's log; platform administrators
  also see sign-ins and platform events under Administration.
- **Password reset.** `uv run python -m app.cli reset-password --email <email>` (reads
  `ADMIN_PASSWORD` or prompts). It also signs the user out everywhere.
- **Encryption key rotation.** Generate a new key and put it first:
  `INTEGRATIONS_ENCRYPTION_KEYS=<new>,<old>`. Restart, run
  `uv run python -m app.cli rotate-secrets`, then remove the old key and restart again.
- **JWT secret rotation.** Change `JWT_SECRET` and restart. Everyone signs in again.
- **Stuck jobs.** A crawl or task whose worker died is marked failed automatically after
  `WORKER_STALE_AFTER_SECONDS`.
- **Disk use.** Page data grows with every crawl. Turn on data retention per organisation
  in Settings to prune page data from older crawls (history and the latest analysed crawl
  are kept) and delete old reports.

## 8. Security reminders

- Never publish the API port, PostgreSQL or Ollama to the network.
- Keep `ENVIRONMENT=production`; it enforces secure cookies and a strong JWT secret.
- The platform never changes the website. Drafts need human approval and are applied by
  a person outside the platform.
- Integrations are records only; connecting a service, and any paid service, needs the
  project owner's authorisation.
- See `docs/SECURITY.md` for the full control list and `docs/SECURITY_REVIEW.md` for the
  latest review.
