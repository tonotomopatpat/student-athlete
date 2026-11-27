import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SYLLABUS = `COURSE SYLLABUS

Course Code: BIO 101
Course Title: General Biology

Course Outline

Week 1: Cell Structure and Function
Week 2: Photosynthesis
Week 3: Prelim Examination
Week 4: Genetics
`;

const LESSON = `# Cell Structure

The cell membrane controls what enters and leaves the cell.

# Basketball Drills

Passing and dribbling practice for the varsity team.
`;

test("student starts a subject from a syllabus and sorts a lesson", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Lia Santos");
  await page.getByLabel("Email").fill(`lia.${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/today$/);

  await page.goto("/learn");
  await page.getByRole("button", { name: "Start from your syllabus" }).first().click();
  await page.getByLabel("Choose your syllabus file").setInputFiles({ name: "syllabus.txt", mimeType: "text/plain", buffer: Buffer.from(SYLLABUS) });

  const dialog = page.getByRole("dialog", { name: "Check your subject" });
  await expect(dialog.getByLabel("Subject name")).toHaveValue("General Biology");
  await expect(dialog.getByLabel("Topic 1", { exact: true })).toHaveValue("Cell Structure and Function");
  await expect(dialog.getByLabel("Topic 3", { exact: true })).toHaveValue("Genetics");
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(violations.map((v) => v.id)).toEqual([]);
  await dialog.getByRole("button", { name: "Move topic 3 up" }).click();
  await expect(dialog.getByLabel("Topic 2", { exact: true })).toHaveValue("Genetics");
  await dialog.getByRole("button", { name: "Create subject" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "General Biology" })).toBeVisible();
  const topicNames = page.getByRole("region", { name: "Topics" }).locator("li a span.text-2xl");
  await expect(topicNames).toHaveText(["Cell Structure and Function", "Genetics", "Photosynthesis"]);

  await page.getByLabel("Choose a lesson file").setInputFiles({ name: "week1.txt", mimeType: "text/plain", buffer: Buffer.from(LESSON) });
  await expect(page.getByText("Lesson read and sorted into topics")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Needs a topic (1)" })).toBeVisible();
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(axe.violations.map((v) => v.id)).toEqual([]);
  await page.getByLabel("Topic for Basketball Drills").selectOption({ label: "Genetics" });
  await expect(page.getByRole("heading", { name: /Needs a topic/ })).toHaveCount(0);
});
