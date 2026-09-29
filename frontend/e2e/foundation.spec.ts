import { expect, test, type Page } from "@playwright/test";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@e2e.example.org";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
}

test("unauthenticated visitors are sent to sign in", async ({ page }) => {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login\?next=%2Foverview/);
  await expect(page.getByRole("heading", { name: "NIIT AI SEO Agent" })).toBeVisible();
});

test("wrong password shows an error and does not sign in", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Invalid email or password" })).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("overview shows real counts and honest empty states", async ({ page }) => {
  await signIn(page);
  await expect(page.getByLabel("Current organisation").locator("option:checked")).toHaveText(
    "NASTP Institute of Information Technology",
  );
  // Seeded tenant: the NIIT website and the local fixture site, and one member.
  await expect(page.getByRole("group", { name: "Projects" })).toContainText("2");
  await expect(page.getByRole("group", { name: "Members" })).toContainText("1");
  // Score tiles show either a real score or an explicit "not scored" state, never a placeholder.
  await expect(page.getByRole("group", { name: "Overall SEO health score" })).toBeVisible();
  await expect(page.getByText("Disabled", { exact: true })).toBeVisible();
});

test("create a project, validate input and save crawl settings", async ({ page }) => {
  await signIn(page);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Projects" }).click();
  await expect(page.getByRole("link", { name: "NIIT website" })).toBeVisible();
  await page.getByRole("link", { name: "New project" }).click();

  await page.getByLabel("Project name").fill("Admissions portal");
  await page.getByLabel("Website address").fill("http://localhost:8080");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByText("Local and internal hostnames are not allowed")).toBeVisible();

  await page.getByLabel("Website address").fill("https://admissions.example.org");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Admissions portal" })).toBeVisible();
  await expect(page.getByLabel("Maximum pages")).toHaveValue("100");
  await expect(page.getByLabel("Maximum depth")).toHaveValue("5");

  // The organisation cap (500) is enforced by the server.
  await page.getByLabel("Maximum pages").fill("5000");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Exceeds organisation limit of 500")).toBeVisible();

  await page.getByLabel("Maximum pages").fill("50");
  await page.getByLabel("Excluded paths").fill("/wp-admin/*");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Maximum pages")).toHaveValue("50");
  await expect(page.getByLabel("Excluded paths")).toHaveValue("/wp-admin/*");
});

test("unbuilt sections say so instead of showing sample data", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: /Approvals/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();
  await expect(page.getByText("Not available yet")).toBeVisible();
  await expect(page.getByText("Phase 4", { exact: true }).last()).toBeVisible();
});

test("administration lists members and the audit trail", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Administration" }).click();
  await expect(page.getByRole("cell", { name: ADMIN_EMAIL })).toBeVisible();
  // Organisation audit entries (sign-in events are account-level and not listed here).
  await expect(page.getByRole("cell", { name: "project.created" }).first()).toBeVisible();
});

test("signing out ends the session", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login/);
});
