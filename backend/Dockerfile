# syntax=docker/dockerfile:1.7
# The API and the worker share this image: `api`, `worker` or `cli <command>`.
# Built by deploy/install.sh; see deploy/README.md.
FROM python:3.12-slim-bookworm

ARG WITH_CHROMIUM=1
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

# A network with a TLS-inspecting proxy can pass its CA certificate as a build secret:
#   docker build --secret id=ca,src=/path/to/ca.crt ...
# uv comes from PyPI (pinned), so the build needs no other registry.
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir uv==0.8.17

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv sync --frozen --no-dev --extra pdf --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv sync --frozen --no-dev --extra pdf

# Chromium for PDF reports and JavaScript rendering (optional: WITH_CHROMIUM=0 skips it,
# and both features then say they are unavailable). Package sources use HTTPS; a build CA
# is used only during this step and not kept in the image.
RUN --mount=type=secret,id=ca,required=false \
    if [ "$WITH_CHROMIUM" = "1" ]; then \
      sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; \
      if [ -s /run/secrets/ca ]; then \
        export NODE_EXTRA_CA_CERTS=/run/secrets/ca; \
        echo 'Acquire::https::CaInfo "/run/secrets/ca";' > /etc/apt/apt.conf.d/99-build-ca; \
      fi; \
      playwright install --with-deps chromium; status=$?; \
      rm -f /etc/apt/apt.conf.d/99-build-ca; rm -rf /var/lib/apt/lists/*; \
      exit $status; \
    fi

RUN useradd --create-home --uid 10001 app && chmod +x scripts/docker-entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["api"]
