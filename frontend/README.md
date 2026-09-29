# Frontend

Next.js 16 dashboard for the NIIT AI SEO Agent. See the root `README.md` for full setup.

```
pnpm install
pnpm dev              # http://localhost:3000, proxies /api/v1 to API_ORIGIN
pnpm lint
pnpm typecheck
pnpm build
pnpm test:e2e         # starts a fresh E2E API and a production build; needs PostgreSQL
```

`API_ORIGIN` (default `http://127.0.0.1:8000`) is read at build time. Rebuild after changing it.

Next.js 16 differs from earlier versions. Read `AGENTS.md` and the bundled docs in
`node_modules/next/dist/docs/` before changing framework-level code.
