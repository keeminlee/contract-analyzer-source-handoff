import { expect, test } from "@playwright/test";

test("Contract Analyzer workbench renders first viewport", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /evidence-first contract workbench/i })).toBeVisible();
  await expect(page.getByLabel(/contract upload/i)).toBeVisible();
  await expect(page.getByLabel(/persistent chat/i)).toBeVisible();
  await page.screenshot({
    path: `test-results/contract-analyzer-${testInfo.project.name}.png`,
    fullPage: true
  });
});
