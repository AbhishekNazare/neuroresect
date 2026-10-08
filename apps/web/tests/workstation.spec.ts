import { expect, test } from "@playwright/test";

test("simulation, editing, provenance and patient switching use real results", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByLabel("Research patient")).toHaveValue("DEMO-001");
  await expect(page.locator("canvas")).toBeVisible();
  await page
    .getByRole("button", { name: "Simulate resection", exact: true })
    .click();
  await expect(
    page.getByText("Metrics computed by neurocore", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Before and after resection transition"),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Estimate synthetic outcome", exact: true })
    .click();
  await expect(page.locator(".prediction-value")).toBeVisible({
    timeout: 90_000,
  });
  await expect(page.locator(".interval-labels")).toContainText("95% interval");
  const exportUrl = await page
    .getByRole("link", { name: "Export scenario", exact: true })
    .getAttribute("href");
  const exported = await (await page.request.get(exportUrl!)).json();
  expect(exported.simulation.provenance.scenario_id).toBe(exported.scenario.id);
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(
    page.getByLabel("Before and after resection transition"),
  ).toBeDisabled();
  await expect(page.locator(".prediction-value")).toHaveCount(0);
  await page.getByLabel("Research patient").selectOption("DEMO-002");
  await expect(page.locator(".scene-meta")).toContainText("DEMO-002");
  await expect(page.locator(".metric-value").first()).toHaveText("—");
  expect(errors).toEqual([]);
});

test("sensitivity, constrained alternatives and patient-separated experiment", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Simulate resection", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Scenarios", exact: true }).click();
  await page
    .getByRole("button", { name: "Test resection boundaries", exact: true })
    .click();
  await expect(page.locator(".bar-row")).toHaveCount(5);
  await page
    .getByRole("button", { name: "Find alternatives", exact: true })
    .click();
  await expect(page.locator(".candidate-list article").first()).toBeVisible();
  await page.getByRole("button", { name: "Experiments", exact: true }).click();
  await page.getByLabel("Synthetic patients", { exact: true }).fill("24");
  await page
    .getByRole("button", { name: "Run A/B/C experiment", exact: true })
    .click();
  await expect(page.locator(".experiment-bars .model-letter")).toHaveText(
    ["A", "B", "C"],
    { timeout: 90_000 },
  );
  await expect(page.locator(".table-scroll").first()).toContainText("roc auc");
});

test("mobile, keyboard guide and explicit API failure state", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Understand the network/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel("Open workstation guide").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByLabel("Open workstation guide")).toBeFocused();
  await page.route("**/api/v1/patients", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { message: "Test engine offline" } },
    }),
  );
  await page.reload();
  await expect(page.getByRole("alert").filter({ hasText: "Test engine offline" })).toContainText("Test engine offline");
  await expect(
    page.getByLabel("Before and after resection transition"),
  ).toBeDisabled();
});
