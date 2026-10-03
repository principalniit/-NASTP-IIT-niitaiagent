# One-command installation

Installs the whole platform in Docker containers, with one command:
- the database;
- the API and the background worker;
- the dashboard, behind a front proxy;
- optionally, the local AI (Ollama).

Everything stays on your machine. Nothing here is a paid service.

## Before you start

- **Docker**: Docker Desktop on Windows or macOS, or Docker Engine with the Compose
  plugin on Linux. On Windows, Docker Desktop needs WSL 2 (`wsl --install`).
- **Disk**: about 4 GB, plus about 5 GB for the AI model.
- **Optional, NVIDIA graphics card for faster AI**: on Windows, the normal NVIDIA driver
  is enough. On Linux, also install the NVIDIA Container Toolkit.
- **This repository**, cloned or downloaded.

## Install

Linux or macOS, from the repository folder:

```
./deploy/install.sh
```

Windows, in PowerShell from the repository folder:

```
powershell -ExecutionPolicy Bypass -File deploy\install.ps1
```

The installer asks for:
- the product name (for example `NIIT AI SEO Agent`);
- the address people will open;
- whether to include the AI assistant;
- the administrator's email and password.

It then generates the secrets, builds and starts everything, downloads the AI model,
and creates the administrator. The first run takes several minutes.

Open the address you gave (by default http://localhost:3000) and sign in.

### Without questions

```
ADMIN_PASSWORD='choose-a-long-password' ./deploy/install.sh --yes \
  --admin-email admin@example.org --product-name "Acme SEO" --url http://localhost:3000 --ai
```

PowerShell takes the same options:

```
$env:ADMIN_PASSWORD = "..."; .\deploy\install.ps1 -Yes -AdminEmail admin@example.org -ProductName "Acme SEO" -AI yes
```

Run `./deploy/install.sh --help` for every option.

## Addresses

| Address you give | What happens |
|------------------|--------------|
| `http://localhost:3000` | Only this computer can open it. |
| `http://<this computer's IP>:3000` | Others on the local network can open it. Use only on a trusted network. |
| `https://seo.example.org` | Ports 80 and 443 are used, and a free certificate is obtained and renewed automatically. The name must point at this server, and both ports must be reachable from the internet. |

## Upgrade

```
git pull
./deploy/install.sh          (Windows: deploy\install.ps1)
```

Running the installer again keeps `deploy/.env` (the secrets and the database
password), rebuilds the images, and upgrades the database when the API starts.

## Everyday commands

Run these from the `deploy` folder:

| Task | Command |
|------|---------|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f api worker` |
| Stop / start | `docker compose stop` / `docker compose start` |
| Another administrator command | `docker compose exec api python -m app.cli reset-password --email someone@example.org` |
| Another AI model | `docker compose exec ollama ollama pull llama3.1:8b`, then set it in the dashboard's organisation settings |
| Database backup | `docker compose exec -T db pg_dump -U seo -Fc seo > backup.dump` |
| Test email | `docker compose exec api python -m app.cli send-test-email --to you@example.org` |

## Email

Add the `SMTP_*` lines from `docs/EMAIL.md` to `deploy/.env`, then run
`docker compose up -d`. Settings you add by hand are kept when the installer runs again.

Back up `deploy/.env` together with the database. Without its
`INTEGRATIONS_ENCRYPTION_KEYS`, stored credentials (for example a Search Console key)
cannot be read.

## Security notes

- **Only the front proxy is published.** The dashboard, API, database and Ollama are
  reachable only inside Docker's private network.
- **Real client addresses.** The front proxy replaces any `X-Forwarded-For` a client
  sends with the real address. The API trusts that header only in this setup, for
  sign-in limits and the audit log.
- **Secrets.** They are random, generated on this machine, and written to `deploy/.env`
  with owner-only permissions.
- **Plain-HTTP addresses** run without secure cookies, because browsers refuse them over
  HTTP. Use an `https://` name for anything beyond one machine or a trusted network.
- **Containers.** They run as non-root users. Chromium, used for PDF reports and
  JavaScript rendering, has no network of its own (see `docs/SECURITY.md`).

## Behind a proxy that inspects TLS

Some organisations' networks replace website certificates. If the build fails with
certificate errors, pass that network's CA certificate:

```
./deploy/install.sh --ca-cert /path/to/company-ca.crt
```

It is used only while building, and is not kept in the images.
