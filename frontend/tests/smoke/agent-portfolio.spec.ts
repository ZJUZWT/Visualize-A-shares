import { expect, test } from "@playwright/test";

import {
  assertNoRuntimeErrors,
  attachPageErrorCollectors,
  installApiMocks,
  installWebSocketMock,
} from "./support/smokeHarness";

test("agent can create a virtual portfolio from empty state", async ({ page }) => {
  const runtimeErrors = attachPageErrorCollectors(page);
  await installWebSocketMock(page);
  await installApiMocks(page, { agentPortfolios: [] });

  await page.goto("/agent");

  await page.getByRole("heading", { name: "电子宠物培养台" }).waitFor();
  await page.getByRole("button", { name: "创建虚拟账户" }).waitFor();
  await page.getByRole("button", { name: "创建虚拟账户" }).click();

  await page.getByLabel("账户 ID").fill("pet-alpha");
  await page.getByLabel("初始资金").fill("888888");
  await page.getByRole("button", { name: "立即创建" }).click();

  await expect(page.getByText("请先创建虚拟账户")).toHaveCount(0);
  await expect(page.getByText("pet-alpha")).toBeVisible();
  await page.waitForTimeout(400);

  assertNoRuntimeErrors("/agent", runtimeErrors);
});
