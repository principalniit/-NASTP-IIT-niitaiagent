import { expect, test, type Page } from "@playwright/test";

// Runs after crawl.spec.ts, which crawls and analyses the fixture site. The AI replies come
// from a scripted stand-in for Ollama (backend/tests/fixtures/fake_ollama.py): these tests
// check the workflow and the safeguards, not the quality of any real model.

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@e2e.example.org";
const REVIEWER_EMAIL = process.env.E2E_REVIEWER_EMAIL ?? "reviewer@e2e.example.org";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "e2e-admin-password";
const FIXTURE = "Fixture site (127.0.0.1)";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
}

function nav(page: Page, name: string) {
  return page.getByRole("navigation", { name: "Main" }).getByRole("link", { name });
}

test("AI drafts go through review by a second person and are never published automatically", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page, ADMIN_EMAIL);

  // AI starts switched off for the organisation, and the page says why.
  await nav(page, "AI Recommendations").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await expect(page.getByText("The AI assistant is off")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Generate summary" })).toBeDisabled();

  await nav(page, "Settings").click();
  await page.getByLabel("Provider").selectOption("ollama");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved")).toBeVisible();

  await nav(page, "AI Recommendations").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await expect(page.getByText("The AI assistant is off")).toHaveCount(0);
  await page.getByRole("button", { name: "Generate summary" }).click();
  const summary = page.getByTestId("ai-result").first();
  await expect(summary.getByRole("heading", { name: "Key findings" })).toBeVisible({ timeout: 60_000 });
  await expect(summary.getByText("AI-generated")).toBeVisible();
  await expect(summary.getByText("checked for unsupported numbers and claims")).toBeVisible();

  await page.getByPlaceholder("Which pages should we fix first?").fill("What should we fix first?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText("The most important open issue is")).toBeVisible({ timeout: 60_000 });

  // Draft a title and description for a crawled page.
  await nav(page, "Pages").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await page.getByRole("link", { name: "/about", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "/about" })).toBeVisible();
  await page.getByRole("button", { name: "Draft title and description" }).click();
  await expect(page.getByRole("heading", { name: "Proposed title" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Nothing is published automatically")).toBeVisible();
  // The page's own draft list refreshes once the AI task has created the drafts.
  await expect(page.getByRole("heading", { name: "Drafts for this page" })).toBeVisible();
  await page.getByRole("link", { name: "open draft 1" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Page title" })).toBeVisible();
  await expect(page.getByText("AI draft")).toBeVisible();
  await expect(page.getByText("Current (original)")).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByText("Pending review").first()).toBeVisible();
  // The person who submitted a version cannot approve it.
  await expect(page.getByText("You wrote or submitted this version")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
  const draftUrl = page.url();

  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, REVIEWER_EMAIL);
  await nav(page, "Approvals").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await expect(page.getByRole("link", { name: "Page title" })).toBeVisible();
  await page.goto(draftUrl);
  await page.getByLabel("Comment (optional)").fill("Matches the page heading.");
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved.", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("This platform does not change the website itself.")).toBeVisible();
  await page.getByLabel("Where and when it was changed (optional)").fill("Updated in the CMS by the web team.");
  await page.getByRole("button", { name: "Mark as published" }).click();
  await expect(page.getByRole("button", { name: "Record rollback" })).toBeVisible();

  const trail = page.getByRole("list", { name: "Approval trail" });
  for (const step of ["Created", "Submitted for review", "Approved", "Marked as published"]) {
    await expect(trail.getByText(step, { exact: true })).toBeVisible();
  }
  await expect(trail.getByText("“Matches the page heading.”")).toBeVisible();
});

test("people can propose changes, and official facts need a verified source", async ({ page }) => {
  await signIn(page, REVIEWER_EMAIL);
  await nav(page, "Approvals").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await page.getByRole("button", { name: "New draft" }).click();
  await page.getByLabel("What to change").selectOption("meta_description");
  await page.getByLabel("Proposed content").fill("Apply by 30 June 2026. Tuition fee: Rs. 95,000.");
  await page.getByLabel("Reason for the change").fill("Admissions office asked for the deadline.");
  await page.getByRole("button", { name: "Save draft" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Meta description" })).toBeVisible();
  await expect(page.getByText("This draft touches official information")).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByText("You wrote or submitted this version")).toBeVisible();
  const draftUrl = page.url();

  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, ADMIN_EMAIL);
  await page.goto(draftUrl);
  const approve = page.getByRole("button", { name: "Approve" });
  await expect(approve).toBeDisabled();
  await page.getByLabel("Verified source (required)").fill("Admissions notice AO-2026-07");
  await approve.click();
  await expect(page.getByText("Verified source: Admissions notice AO-2026-07")).toBeVisible();
});

test("management reports, crawl-to-crawl monitoring and schedules", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page, ADMIN_EMAIL);

  await nav(page, "Reports").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await page.getByLabel("Title (optional)").fill("Quarterly SEO review");
  await page.getByRole("button", { name: "Generate report" }).click();
  const link = page.getByRole("link", { name: "Quarterly SEO review" });
  await expect(link).toBeVisible({ timeout: 60_000 });
  await link.click();

  const report = page.frameLocator("iframe[title='Quarterly SEO review']");
  await expect(report.getByRole("heading", { name: "1.Executive summary" })).toBeVisible();
  await expect(report.getByRole("heading", { name: "13.Methodology and limitations" })).toBeVisible();
  await expect(report.getByText("not a search ranking").first()).toBeVisible();
  await expect(report.getByText("/missing").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Download HTML" })).toBeVisible();

  // A second crawl gives Monitoring something to compare.
  await nav(page, "Crawl Explorer").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await page.getByRole("button", { name: "Start crawl" }).click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("link", { name: "Completed · view SEO audit" })).toBeVisible({ timeout: 60_000 });

  await nav(page, "Monitoring").click();
  await page.getByLabel("Project", { exact: true }).selectOption({ label: FIXTURE });
  await expect(page.getByRole("img", { name: /Overall score over 2 crawls/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Compare two crawls" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /New issues/ })).toBeVisible();
  await expect(page.getByText("Status code changes")).toBeVisible();

  await nav(page, "Projects").click();
  await page.getByRole("link", { name: "Fixture site" }).click();
  await expect(page.getByText("Scheduling is switched off on this server")).toBeVisible();
  await page.getByLabel("Crawl on a schedule").check();
  await page.getByLabel("How often").selectOption("monthly");
  await page.getByRole("button", { name: "Save schedule" }).click();
  await expect(page.getByText("Schedule saved")).toBeVisible();
  await expect(page.getByText(/Next crawl:/)).toBeVisible();
});
