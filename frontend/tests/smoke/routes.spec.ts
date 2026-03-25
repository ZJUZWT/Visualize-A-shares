import type { Page } from "@playwright/test";
import { test } from "@playwright/test";

import {
  assertNoRuntimeErrors,
  attachPageErrorCollectors,
  installApiMocks,
  installWebSocketMock,
} from "./support/smokeHarness";

interface RouteSmokeCase {
  path: string;
  waitForReady: (page: Page) => Promise<void>;
}

const ROUTES = [
  {
    path: "/",
    waitForReady: (page: Page) =>
      page.getByRole("heading", { name: "StockScape" }).waitFor(),
  },
  {
    path: "/expert",
    waitForReady: (page: Page) =>
      page.getByRole("heading", { name: "专家团队" }).waitFor(),
  },
  {
    path: "/debate",
    waitForReady: (page: Page) =>
      page.getByRole("button", { name: "开始辩论" }).waitFor(),
  },
  {
    path: "/agent",
    waitForReady: async (page: Page) => {
      await page.getByRole("heading", { name: "电子宠物培养台" }).waitFor();
      await page.getByRole("button", { name: /^训练$/ }).click();
      await page.getByRole("button", { name: /^回测$/ }).click();
      await page.getByRole("button", { name: /^模拟盘$/ }).click();
      await page.getByRole("button", { name: /^宠物$/ }).click();
    },
  },
  {
    path: "/sector",
    waitForReady: (page: Page) =>
      page.getByRole("heading", { name: /板块研究/ }).waitFor(),
  },
  {
    path: "/plans",
    waitForReady: (page: Page) =>
      page.getByRole("heading", { name: /交易计划备忘录/ }).waitFor(),
  },
  {
    path: "/tasks",
    waitForReady: (page: Page) =>
      page.getByRole("heading", { name: /事务管理/ }).waitFor(),
  },
] satisfies RouteSmokeCase[];

test.describe("frontend console smoke", () => {
  for (const route of ROUTES) {
    test(`opens ${route.path} without runtime errors`, async ({ page }) => {
      const runtimeErrors = attachPageErrorCollectors(page);
      await installWebSocketMock(page);
      await installApiMocks(page);

      await page.goto(route.path);
      await route.waitForReady(page);
      await page.waitForTimeout(400);

      assertNoRuntimeErrors(route.path, runtimeErrors);
    });
  }
});
