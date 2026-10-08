import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { tmpdir } from "node:os";

const root = resolve(__dirname, "../..");
const python = existsSync(resolve(root, ".venv/bin/python"))
  ? resolve(root, ".venv/bin/python")
  : "python";
export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    viewport: { width: 1440, height: 1100 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
  },
  webServer: [
    {
      command: `${python} -m uvicorn neuroresect_api.main:app --host 127.0.0.1 --port 8000`,
      cwd: root,
      url: "http://127.0.0.1:8000/health",
      env: {
        DATABASE_URL: `sqlite:///${resolve(tmpdir(), `neuroresect-e2e-${process.pid}.db`)}`,
      },
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run dev",
      cwd: root,
      url: "http://localhost:3000",
      env: { API_URL: "http://127.0.0.1:8000", NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
