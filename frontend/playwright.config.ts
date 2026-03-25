import { defineConfig, devices } from "@playwright/test";

const HOST = "127.0.0.1";
const PORT = Number(process.env.PLAYWRIGHT_PORT ?? "3000");
const BASE_URL = `http://${HOST}:${PORT}`;
const SKIP_WEBSERVER = process.env.PLAYWRIGHT_SKIP_WEBSERVER === "1";

export default defineConfig({
  testDir: "./tests/smoke",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  retries: 0,
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  webServer: SKIP_WEBSERVER
    ? undefined
    : {
        command: `npm run build && npx next start --hostname ${HOST} --port ${PORT}`,
        url: BASE_URL,
        reuseExistingServer: true,
        timeout: 240_000,
      },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
