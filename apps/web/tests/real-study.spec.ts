import { expect, test } from "@playwright/test";

test("saved IDEAS evidence supports comparison and aggregate export", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Experiments", exact: true }).click();
  await page
    .getByRole("button", { name: "IDEAS II results", exact: true })
    .click();
  await expect(
    page.getByText("No useful discrimination in this baseline."),
  ).toBeVisible();
  await expect(page.locator(".real-cohort-flow")).toContainText("182");
  await page.getByLabel("Real study metric").selectOption("brier");
  await expect(
    page.getByRole("button", { name: "Inspect real model A" }),
  ).toContainText("0.277");
  await page.getByRole("button", { name: "Inspect real model C" }).click();
  await expect(
    page.getByRole("heading", { name: "Model C inputs" }),
  ).toBeVisible();
  const href = await page
    .getByRole("link", { name: "Export aggregate report" })
    .getAttribute("href");
  const report = await (await page.request.get(href!)).json();
  expect(report.synthetic).toBe(false);
  expect(report.predictions).toBeUndefined();
  await page.screenshot({
    path: "../../artifacts/real-study-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      ),
    )
    .toBeLessThanOrEqual(0);
  await page.screenshot({
    path: "../../artifacts/real-study-mobile.png",
    fullPage: true,
  });
});

test("real study fetch failure can be retried", async ({ page }) => {
  await page.route(
    "**/api/v1/research-studies/ideas-year1-baseline-v1",
    (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error: { message: "Study temporarily unavailable" },
        }),
      }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Experiments", exact: true }).click();
  await page
    .getByRole("button", { name: "IDEAS II results", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Real study unavailable" }),
  ).toBeVisible();
  await page.unroute("**/api/v1/research-studies/ideas-year1-baseline-v1");
  await page.getByRole("button", { name: "Retry real study" }).click();
  await expect(
    page.getByText("No useful discrimination in this baseline."),
  ).toBeVisible();
});
