import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "correct-horse-battery";

async function register(page: Page, name: string) {
  const email = `${name.toLowerCase().replace(/\s+/g, ".")}.${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/today$/);
  return email;
}

async function answerAll(page: Page) {
  await expect(page.getByText(/Question \d+ of \d+/)).toBeVisible();
  for (let guard = 0; guard < 20; guard += 1) {
    await page.getByRole("radio").first().check();
    const submit = page.getByRole("button", { name: "Submit answers" });
    if (await submit.isVisible()) {
      await submit.click();
      break;
    }
    await page.getByRole("button", { name: "Next" }).click();
  }
  await expect(page.getByRole("heading", { name: /\d+ of \d+ correct/ })).toBeVisible();
}

test("student sets up, assesses, gets a plan, and manages own content", async ({ page }) => {
  await register(page, "Juan Dela Cruz");
  await expect(page.getByRole("link", { name: "Choose subjects" })).toBeVisible();

  await page.getByRole("link", { name: "Choose subjects" }).click();
  const math = page.getByRole("listitem").filter({ hasText: "Mathematics in the Modern World" });
  await math.getByRole("button", { name: "Enroll" }).click();
  await expect(page.getByText("Enrolled in Mathematics in the Modern World (sample)")).toBeVisible();

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Today" }).click();
  await expect(page.getByText("Starting quizzes")).toBeVisible();
  for (let i = 0; i < 3; i += 1) {
    await page.getByRole("link", { name: "Take quiz" }).first().click();
    await answerAll(page);
    await page.getByRole("link", { name: "Back to today" }).click();
  }
  await expect(page.getByText("Starting quizzes")).toHaveCount(0);

  await page.getByRole("button", { name: "Get my next activity" }).click();
  await expect(page.getByText("Next up")).toBeVisible();
  await expect(page.getByRole("button", { name: "Get my next activity" })).toHaveCount(0);
  await page.getByRole("link", { name: /^(Start|Continue)$/ }).click();
  await expect(page).toHaveURL(/\/activity\/\d+$/);
  const review = page.getByRole("button", { name: "I have finished reviewing" });
  if (await review.isVisible()) {
    await review.click();
    await expect(page).toHaveURL(/\/today$/);
  } else {
    await answerAll(page);
    await page.getByRole("link", { name: "Back to today" }).click();
  }

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Progress" }).click();
  await expect(page.getByText(/of 3 topics mastered/)).toBeVisible();

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Plan" }).click();
  await page.getByRole("button", { name: "Add commitment" }).click();
  await page.getByLabel("Title").fill("Basketball practice");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Commitment added")).toBeVisible();
  await expect(page.getByText("Basketball practice").first()).toBeVisible();

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Learn" }).click();
  await page.getByRole("button", { name: "New subject" }).click();
  await page.getByLabel("Subject name").fill("Biology Basics");
  await page.getByRole("button", { name: "Create subject" }).click();
  await expect(page.getByRole("heading", { name: "Biology Basics", level: 1 })).toBeVisible();
  await page.getByLabel("Add a topic").fill("Cells");
  await page.getByRole("button", { name: "Add topic" }).click();
  await page.getByRole("link", { name: /^Cells/ }).click();
  await expect(page.getByRole("heading", { name: "Cells", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "Add questions" }).click();
  await page.getByLabel("How").selectOption("paste");
  const block = (n: number) => `What is ${n} + ${n}?\nA) ${n}\nB) ${n * 2}\nC) ${n * 3}\nAnswer: B`;
  await page.getByLabel("Paste questions").fill([1, 2, 3, 4, 5].map(block).join("\n\n"));
  await page.getByRole("dialog").getByRole("button", { name: "Add questions" }).click();
  await expect(page.getByText("5 questions added")).toBeVisible();
  await expect(page.getByRole("link", { name: "Take the starting quiz" })).toBeVisible();

  await page.getByRole("link", { name: "Take the starting quiz" }).click();
  await answerAll(page);
});

test("settings save and sign out", async ({ page }) => {
  await register(page, "Maria Santos");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Me" }).click();
  await page.getByLabel(/Gap around commitments/).fill("20");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/today");
  await expect(page).toHaveURL(/\/login$/);
});

test.describe("mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("bottom tab bar is used and nothing overflows horizontally", async ({ page }) => {
    await register(page, "Pedro Reyes");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link")).toHaveCount(5);
    for (const label of ["Learn", "Plan", "Progress", "Me", "Today"]) {
      await nav.getByRole("link", { name: label }).click();
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${label} overflows`).toBeLessThanOrEqual(0);
    }
  });
});
