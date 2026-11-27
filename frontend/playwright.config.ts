import { defineConfig, devices } from "@playwright/test";

const PORT = 8765;
const DB = "/tmp/sideline-e2e.db";
const UPLOADS = "/tmp/sideline-e2e-uploads";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `rm -rf ${DB} ${UPLOADS} && .venv/bin/python -m app.cli seed-samples && .venv/bin/python -m app.cli pretrain --students 300 && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
    cwd: "../backend",
    env: { DATABASE_URL: `sqlite:///${DB}`, UPLOAD_DIR: UPLOADS, SCHEDULER_ENABLED: "false" },
    url: `http://127.0.0.1:${PORT}/api/auth/me`,
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "ignore",
  },
});
