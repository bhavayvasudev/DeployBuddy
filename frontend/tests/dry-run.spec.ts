import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // The browser may contact only our local frontend. Backend tests deny outbound sockets too.
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1" || url.port !== "3100") {
      throw new Error("Unexpected external browser request");
    }
    await route.continue();
  });
  await page.goto("/");
});

async function preview(page: import("@playwright/test").Page) {
  await page.getByLabel("GitHub repository URL").fill("https://github.com/example/service");
  await page.getByLabel("Service name", { exact: true }).fill("browser-service");
  await page.getByRole("button", { name: "Preview dry-run" }).click();
  await expect(page.getByRole("heading", { name: "2. Review and explicitly confirm" })).toBeVisible();
}

test("confirmed plan persists through the actual API and can be reloaded", async ({ page }) => {
  await preview(page);
  const save = page.getByRole("button", { name: "Save confirmed dry-run" });
  await expect(save).toBeDisabled();
  await page.getByRole("checkbox").check();
  const response = page.waitForResponse((result) => result.url().endsWith("/api/requests") && result.request().method() === "POST");
  await save.click();
  expect((await response).status()).toBe(201);
  await expect(page.getByRole("heading", { name: "Saved request: planned" })).toBeVisible();
  await expect(page.getByText("Explicitly confirmed dry-run request accepted locally.")).toBeVisible();
  const id = await page.getByLabel("Request ID", { exact: true }).inputValue();
  expect(id).toMatch(/^[a-f0-9-]{36}$/);
  // Same proposal and key: a second explicitly confirmed save is an idempotent retry.
  await page.getByRole("checkbox").check();
  const duplicate = page.waitForResponse((result) => result.url().endsWith("/api/requests") && result.request().method() === "POST");
  await save.click();
  expect((await duplicate).status()).toBe(200);
  await expect(page.getByLabel("Request ID", { exact: true })).toHaveValue(id);
  await page.reload();
  await page.getByLabel("Request ID", { exact: true }).fill(id);
  await page.getByRole("button", { name: "Load request status" }).click();
  await expect(page.getByRole("heading", { name: "Saved request: planned" })).toBeVisible();
  await expect(page.locator(".saved li")).toHaveCount(2);
});

test("editing a proposal removes the confirmation and requires another preview", async ({ page }) => {
  await preview(page);
  await page.getByRole("checkbox").check();
  await page.getByLabel("Service name", { exact: true }).fill("changed-service");
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await page.getByRole("button", { name: "Preview dry-run" }).click();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Save confirmed dry-run" })).toBeDisabled();
});

test("backend rejects unsupported repository hosts in the real form", async ({ page }) => {
  await page.getByLabel("GitHub repository URL").fill("https://evil.test/owner/repo");
  await page.getByLabel("Service name", { exact: true }).fill("browser-service");
  await page.getByRole("button", { name: "Preview dry-run" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Check the GitHub URL" })).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
});
