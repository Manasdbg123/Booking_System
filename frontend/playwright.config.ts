import { defineConfig, devices } from "@playwright/test";

/**
 * These are end-to-end UI tests: they expect the API (port 8000), the
 * workers, Redis and a seeded Postgres to already be running, plus the
 * Next.js dev server on port 3000 (started automatically below).
 * See docs/local-setup.md.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
