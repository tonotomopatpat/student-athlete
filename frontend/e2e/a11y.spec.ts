import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoViolations(page: Page, label: string) {
  await expect(page.getByRole("heading").first()).toBeVisible();
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const summary = violations.map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(summary, `${label} accessibility violations`).toEqual([]);
}

for (const viewport of [
  { name: "desktop", width: 1280, height: 800 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`no WCAG A/AA violations on key screens (${viewport.name})`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/login");
    await expectNoViolations(page, "login");
    await page.goto("/register");
    await expectNoViolations(page, "register");

    await page.getByLabel("Full name").fill("Ana Lim");
    await page.getByLabel("Email").fill(`ana.${viewport.name}.${Date.now()}@example.com`);
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/today$/);
    await expectNoViolations(page, "today empty");

    await page.goto("/learn");
    const math = page.getByRole("listitem").filter({ hasText: "Mathematics in the Modern World" });
    await math.getByRole("button", { name: "Enroll" }).click();
    await expect(page.getByText(/Enrolled in/)).toBeVisible();
    await expectNoViolations(page, "learn");

    await math.getByRole("link", { name: /Mathematics/ }).click();
    await expectNoViolations(page, "subject");
    await page.getByRole("link", { name: /Patterns and Sequences/ }).click();
    await expectNoViolations(page, "topic");
    await page.getByRole("button", { name: "Add questions" }).first().click();
    await expectNoViolations(page, "add questions dialog");
    await page.keyboard.press("Escape");

    await page.getByRole("link", { name: "Take the starting quiz" }).click();
    await expect(page.getByText(/Question 1 of/)).toBeVisible();
    await expectNoViolations(page, "question");

    for (const path of ["/today", "/plan", "/progress", "/notifications", "/me"]) {
      await page.goto(path);
      await expectNoViolations(page, path);
    }
    await page.goto("/plan");
    await page.getByRole("button", { name: "Add commitment" }).click();
    await expectNoViolations(page, "commitment dialog");
  });
}
