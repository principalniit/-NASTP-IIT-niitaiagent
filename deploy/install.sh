#!/usr/bin/env bash
# One-command installer and upgrader for Linux and macOS (Windows: install.ps1).
#
#   ./deploy/install.sh                      asks a few questions, then installs
#   ./deploy/install.sh --yes --admin-email you@example.org --product-name "Acme SEO"
#
# Running it again upgrades: secrets in deploy/.env are kept, images are rebuilt and the
# database schema is upgraded when the API starts. See deploy/README.md.
set -euo pipefail
cd "$(dirname "$0")"

PRODUCT_NAME="" ADMIN_EMAIL="" ADMIN_NAME="Administrator" PUBLIC_URL="" AI="" MODEL=""
GPU="" CA_CERT="" ASSUME_YES=0 WITH_CHROMIUM=1

usage() {
  cat <<'TEXT'
Options:
  --product-name NAME    name shown on every screen (default: AI SEO Agent)
  --admin-email EMAIL    first platform administrator (asked if missing)
  --admin-name NAME      their display name (default: Administrator)
  --url URL              address people will open (default: http://localhost:3000)
  --ai | --no-ai         include the local AI assistant (Ollama); default: ask
  --model NAME           Ollama model to download (default: qwen2.5:7b)
  --gpu | --no-gpu       let Ollama use an NVIDIA GPU (default: when nvidia-smi works)
  --ca-cert FILE         CA certificate for a TLS-inspecting proxy, used while building
  --no-chromium          skip Chromium (PDF reports and JavaScript rendering)
  --yes                  do not ask; use the options and defaults
The administrator's password is asked for, or read from ADMIN_PASSWORD.
TEXT
}

while [ $# -gt 0 ]; do
  case "$1" in
    --product-name) PRODUCT_NAME="$2"; shift 2 ;;
    --admin-email) ADMIN_EMAIL="$2"; shift 2 ;;
    --admin-name) ADMIN_NAME="$2"; shift 2 ;;
    --url) PUBLIC_URL="$2"; shift 2 ;;
    --ai) AI=yes; shift ;;
    --no-ai) AI=no; shift ;;
    --model) MODEL="$2"; shift 2 ;;
    --gpu) GPU=yes; shift ;;
    --no-gpu) GPU=no; shift ;;
    --ca-cert) CA_CERT="$2"; shift 2 ;;
    --no-chromium) WITH_CHROMIUM=0; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
ask() {  # ask VAR "Question" "default"
  local reply
  if [ "$ASSUME_YES" = 1 ]; then printf -v "$1" '%s' "$3"; return; fi
  read -r -p "$2 [$3]: " reply
  printf -v "$1" '%s' "${reply:-$3}"
}
random() {  # random LENGTH -> letters and digits only
  # Reads fixed-size chunks; a pipe closed early would end the script (pipefail).
  local s=""
  while [ "${#s}" -lt "$1" ]; do s+="$(head -c 64 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9')"; done
  printf '%s' "${s:0:$1}"
}
fernet_key() {  # 32 random bytes, url-safe base64, as the encryption key format requires
  head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n'
}
env_get() { [ -f .env ] && sed -n "s/^$1=\"\{0,1\}\([^\"]*\)\"\{0,1\}$/\1/p" .env | tail -n 1 || true; }

command -v docker >/dev/null || die "Docker is not installed. Install Docker Engine or Docker Desktop first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing ('docker compose')."
docker info >/dev/null 2>&1 || die "Docker is not running. Start Docker, then run this again."

if [ -f .env ]; then
  say "Existing installation found: upgrading it (secrets in deploy/.env are kept)"
  PRODUCT_NAME="${PRODUCT_NAME:-$(env_get PRODUCT_NAME)}"
  PUBLIC_URL="${PUBLIC_URL:-$(env_get PUBLIC_BASE_URL)}"
  [ -n "$AI" ] || { [ "$(env_get AI_PROVIDER)" = ollama ] && AI=yes || AI=no; }
  MODEL="${MODEL:-$(env_get OLLAMA_DEFAULT_MODEL)}"
  [ -n "$GPU" ] || { case "$(env_get COMPOSE_FILE)" in *gpu*) GPU=yes ;; *) GPU=no ;; esac; }
  CA_CERT="${CA_CERT:-$(env_get CA_CERT_FILE)}"
  JWT_SECRET="$(env_get JWT_SECRET)"
  ENC_KEYS="$(env_get INTEGRATIONS_ENCRYPTION_KEYS)"
  DB_PASSWORD="$(env_get DB_PASSWORD)"
  FIRST_INSTALL=0
else
  FIRST_INSTALL=1
  [ -n "$PRODUCT_NAME" ] || ask PRODUCT_NAME "Product name shown on every screen" "AI SEO Agent"
  [ -n "$PUBLIC_URL" ] || ask PUBLIC_URL "Address people will open" "http://localhost:3000"
  [ -n "$AI" ] || ask AI "Include the local AI assistant (needs about 5 GB of disk)? yes/no" "yes"
  JWT_SECRET="$(random 64)"
  ENC_KEYS="$(fernet_key)"
  DB_PASSWORD="$(random 32)"
fi
PRODUCT_NAME="${PRODUCT_NAME:-AI SEO Agent}"
PUBLIC_URL="${PUBLIC_URL:-http://localhost:3000}"
PUBLIC_URL="${PUBLIC_URL%/}"
MODEL="${MODEL:-qwen2.5:7b}"
case "$AI" in y|Y|yes|YES) AI=yes ;; *) AI=no ;; esac
if [ -z "$GPU" ]; then
  if [ "$AI" = yes ] && command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then GPU=yes; else GPU=no; fi
fi
case "$PUBLIC_URL" in http://*|https://*) ;; *) die "--url must start with http:// or https://" ;; esac
case "$PRODUCT_NAME" in *'"'*|*'$'*|*'`'*) die "The product name cannot contain \" \$ or \`" ;; esac

# Port and bind address from the public address. A localhost address is only reachable
# from this machine; any other address listens on the network.
hostport="${PUBLIC_URL#*://}"; hostport="${hostport%%/*}"
host="${hostport%%:*}"
WEB_PORT=3000
WEB_BIND=0.0.0.0
case "$host" in localhost|127.0.0.1) WEB_BIND=127.0.0.1; [ "$hostport" != "$host" ] && WEB_PORT="${hostport##*:}" ;; esac

if [ "${PUBLIC_URL%%://*}" = https ]; then
  # A public name: the front proxy listens on 80 and 443 and gets a free certificate.
  [ "$hostport" = "$host" ] || die "Use an https:// address without a port, for example https://seo.example.org"
  case "$host" in localhost|127.*|*[!a-zA-Z0-9.-]*) die "HTTPS needs a public domain name that points at this server" ;; esac
  ENVIRONMENT=production COOKIE_SECURE=true
  SITE_ADDRESS="$host" PORTS_FILE=compose.https.yaml
else
  SITE_ADDRESS="http://:$WEB_PORT" PORTS_FILE=compose.http.yaml
  # Without HTTPS, browsers refuse secure cookies, so production safety checks that
  # require them are not applied. Put the dashboard behind HTTPS for real use.
  ENVIRONMENT=development COOKIE_SECURE=false
fi

COMPOSE_FILE="compose.yaml:$PORTS_FILE"
[ "$GPU" = yes ] && COMPOSE_FILE="$COMPOSE_FILE:compose.gpu.yaml"
COMPOSE_PROFILES=""
[ "$AI" = yes ] && COMPOSE_PROFILES=ai
[ "$CA_CERT" = ./no-extra-ca.crt ] && CA_CERT=""  # the empty placeholder from a previous run
if [ -n "$CA_CERT" ]; then
  [ -s "$CA_CERT" ] || die "CA certificate not found: $CA_CERT"
  CA_CERT="$(cd "$(dirname "$CA_CERT")" && pwd)/$(basename "$CA_CERT")"
fi

# Settings added by hand (for example SMTP_* for email) are kept on upgrade.
WRITTEN='COMPOSE_FILE|COMPOSE_PROFILES|PRODUCT_NAME|PUBLIC_BASE_URL|CORS_ORIGINS|WEB_PORT|WEB_BIND|SITE_ADDRESS|ENVIRONMENT|COOKIE_SECURE|JWT_SECRET|INTEGRATIONS_ENCRYPTION_KEYS|DB_PASSWORD|AI_PROVIDER|OLLAMA_DEFAULT_MODEL|WITH_CHROMIUM|CA_CERT_FILE'
KEPT=""
if [ -f .env ]; then
  KEPT="$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env | grep -vE "^($WRITTEN)=" || true)"
fi

say "Writing deploy/.env"
umask 077
cat > .env <<ENV
# Written by install.sh. Keep this file private and back it up with the database:
# without INTEGRATIONS_ENCRYPTION_KEYS, stored credentials cannot be read.
COMPOSE_FILE=$COMPOSE_FILE
COMPOSE_PROFILES=$COMPOSE_PROFILES
PRODUCT_NAME="$PRODUCT_NAME"
PUBLIC_BASE_URL=$PUBLIC_URL
CORS_ORIGINS=$PUBLIC_URL
WEB_PORT=$WEB_PORT
WEB_BIND=$WEB_BIND
SITE_ADDRESS=$SITE_ADDRESS
ENVIRONMENT=$ENVIRONMENT
COOKIE_SECURE=$COOKIE_SECURE
JWT_SECRET=$JWT_SECRET
INTEGRATIONS_ENCRYPTION_KEYS=$ENC_KEYS
DB_PASSWORD=$DB_PASSWORD
AI_PROVIDER=$([ "$AI" = yes ] && echo ollama || echo none)
OLLAMA_DEFAULT_MODEL=$([ "$AI" = yes ] && echo "$MODEL")
WITH_CHROMIUM=$WITH_CHROMIUM
CA_CERT_FILE=${CA_CERT:-./no-extra-ca.crt}
ENV
if [ -n "$KEPT" ]; then
  printf '\n# Your own settings, kept when the installer runs again.\n%s\n' "$KEPT" >> .env
fi
umask 022

say "Building and starting the containers (the first build takes several minutes)"
docker compose build
docker compose up -d --wait --wait-timeout 600

if [ "$AI" = yes ]; then
  say "Downloading the AI model $MODEL (several GB; skipped when already present)"
  docker compose exec -T ollama ollama pull "$MODEL"
fi

if [ "$FIRST_INSTALL" = 1 ]; then
  [ -n "$ADMIN_EMAIL" ] || ask ADMIN_EMAIL "Administrator email" ""
  [ -n "$ADMIN_EMAIL" ] || die "An administrator email is needed (--admin-email)."
  say "Creating the platform administrator $ADMIN_EMAIL"
  if [ -n "${ADMIN_PASSWORD:-}" ]; then
    docker compose exec -T -e ADMIN_PASSWORD api python -m app.cli create-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
  else
    docker compose exec api python -m app.cli create-admin --email "$ADMIN_EMAIL" --name "$ADMIN_NAME"
  fi
fi

say "Done. Open $PUBLIC_URL and sign in."
cat <<TEXT
  Status:    (cd deploy && docker compose ps)
  Logs:      (cd deploy && docker compose logs -f api worker)
  Upgrade:   git pull && ./deploy/install.sh
  Stop:      (cd deploy && docker compose stop)
TEXT
