/**
 * The product's name on every screen. Set NEXT_PUBLIC_PRODUCT_NAME (in frontend/.env.local,
 * or as a build argument in the container install) to rebrand; it is read at build time.
 * Organisations' own names and report branding are data, set in the dashboard.
 */
export const PRODUCT_NAME = process.env.NEXT_PUBLIC_PRODUCT_NAME?.trim() || "AI SEO Agent";
