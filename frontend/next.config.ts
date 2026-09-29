import type { NextConfig } from "next";

// The browser talks only to this Next.js server. API calls under /api/v1 are proxied to
// FastAPI so cookies stay first-party and no CORS is needed in the browser.
// API_ORIGIN is read at build time and baked into the route manifest.
const apiOrigin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

// Content Security Policy without nonces, as the Next.js guide describes, so pages stay
// static. Inline scripts are Next.js's own hydration data; nothing loads from other sites,
// and no page can be framed. Development also needs eval for fast refresh.
const isDev = process.env.NODE_ENV === "development";
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  // Lets end-to-end tests build into a separate folder without touching the dev build.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
