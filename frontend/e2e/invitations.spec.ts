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

test("an invited person creates their own account and joins", async ({ page, browser }) => {
  await signIn(page);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Administration" }).click();
  const form = page.getByRole("form", { name: "Invite a member" });
  await form.getByLabel("Email to invite").fill("new.member@e2e.example.org");
  await form.getByLabel("Role").selectOption("editor");
  await form.getByRole("button", { name: "Send invitation" }).click();

  // Email is off in this environment, so the link is shown for sharing by hand.
  await expect(page.getByRole("status").filter({ hasText: "Email is not set up" })).toBeVisible();
  const link = await page.getByLabel("Invitation link").inputValue();
  expect(link).toMatch(/\/invite#token=[\w-]+$/);
  const pending = page.getByRole("table", { name: "Pending invitations" });
  await expect(pending.getByRole("cell", { name: "new.member@e2e.example.org", exact: true })).toBeVisible();

  const invitee = await browser.newPage();
  await invitee.goto(`/invite${new URL(link).hash}`);
  await expect(invitee.getByRole("heading", { name: "You're invited" })).toBeVisible();
  await expect(invitee.getByText("NASTP Institute of Information Technology")).toBeVisible();
  await invitee.getByLabel("Your name").fill("New Member");
  await invitee.getByLabel("New password").fill("short");
  await invitee.getByRole("button", { name: "Create account and join" }).click();
  await expect(invitee.getByText("At least 12 characters").first()).toBeVisible();
  await invitee.getByLabel("New password").fill("a-long-member-password");
  await invitee.getByLabel("Confirm password").fill("a-long-member-password");
  await invitee.getByRole("button", { name: "Create account and join" }).click();
  await expect(invitee.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await expect(invitee.getByLabel("Current organisation").locator("option:checked")).toHaveText(
    "NASTP Institute of Information Technology",
  );

  // The link works once.
  const again = await browser.newPage();
  await again.goto(`/invite${new URL(link).hash}`);
  await expect(again.getByText("This invitation is not valid or has expired")).toBeVisible();

  await page.reload();
  await expect(page.getByText("No pending invitations.")).toBeVisible();
  await expect(page.getByRole("cell", { name: "New Member", exact: true })).toBeVisible();
});

test("password reset explains itself when the server has no email", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page.getByRole("heading", { name: "Forgot your password?" })).toBeVisible();
  await expect(page.getByText("Email is not set up on this server")).toBeVisible();

  await page.goto("/reset-password");
  await expect(page.getByText("This page needs the link from your reset email.")).toBeVisible();
  await page.goto("/reset-password#token=not-a-real-token-but-long-enough");
  await page.getByLabel("New password").fill("a-long-new-password");
  await page.getByLabel("Confirm password").fill("a-long-new-password");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByText("This reset link is not valid or has expired.")).toBeVisible();
});
