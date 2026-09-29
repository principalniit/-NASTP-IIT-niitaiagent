import { expect, test } from "@playwright/test";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@e2e.example.org";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password";

test("start a crawl, follow progress and review results", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Crawl Explorer" }).click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: "Fixture site (127.0.0.1)" });
  await page.getByRole("button", { name: "Start crawl" }).click();

  // Lands on the crawl page, which polls until the worker finishes.
  await expect(page.getByRole("heading", { level: 1, name: "Crawl of Fixture site" })).toBeVisible();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("Found and applied")).toBeVisible();

  await expect(page.getByRole("group", { name: "Client errors (4xx)" })).toContainText("1");
  await expect(page.getByRole("group", { name: "Server errors (5xx)" })).toContainText("1");
  await expect(page.getByRole("group", { name: "Broken internal links" })).toContainText("2");
  await expect(page.getByRole("group", { name: "Orphan pages" })).toContainText("1");
  await expect(page.getByText("2 pages share the same content")).toBeVisible();

  await page.getByLabel("Filter pages").selectOption("4xx");
  const missing = page.getByRole("link", { name: "/missing", exact: true }).first();
  await expect(missing).toBeVisible();
  await missing.click();

  await expect(page.getByRole("heading", { level: 1, name: "/missing" })).toBeVisible();
  await expect(page.getByText("404").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Incoming internal links" })).toBeVisible();

  await page.getByRole("link", { name: "Back to crawl" }).click();
  await expect(page.getByRole("heading", { name: "Broken internal links" })).toBeVisible();

  // The Pages section shows the latest completed crawl for the chosen project.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Pages" }).click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: "Fixture site (127.0.0.1)" });
  await expect(page.getByRole("link", { name: "/about", exact: true })).toBeVisible();

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Overview" }).click();
  await expect(page.getByRole("group", { name: "Crawl status" })).toContainText("Completed");
  await expect(page.getByRole("group", { name: "Pages crawled" })).not.toContainText("No crawl data yet");
});
