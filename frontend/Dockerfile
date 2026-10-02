# syntax=docker/dockerfile:1.7
# The dashboard. Built by deploy/install.sh; see deploy/README.md.
FROM node:22-bookworm-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# A network with a TLS-inspecting proxy can pass its CA certificate as a build secret.
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; fi; \
    pnpm install --frozen-lockfile
COPY . .
# Both are read at build time: where /api/v1 is forwarded, and the product's name.
ARG API_ORIGIN=http://api:8000
ARG NEXT_PUBLIC_PRODUCT_NAME="AI SEO Agent"
ENV API_ORIGIN=$API_ORIGIN NEXT_PUBLIC_PRODUCT_NAME=$NEXT_PUBLIC_PRODUCT_NAME NEXT_OUTPUT=standalone
RUN pnpm build

FROM node:22-bookworm-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
