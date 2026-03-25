import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCreatePortfolioPayload,
  normalizePortfolioSummaries,
  pickActivePortfolioId,
} from "./portfolioWorkspace.ts";

test("normalizePortfolioSummaries keeps valid portfolio rows", () => {
  const result = normalizePortfolioSummaries([
    { id: "paper-1", mode: "paper", initial_capital: 500000, cash_balance: 480000 },
    { id: 123, mode: "paper" },
    null,
  ]);

  assert.deepEqual(result, [
    {
      id: "paper-1",
      mode: "paper",
      initialCapital: 500000,
      cashBalance: 480000,
      createdAt: null,
    },
  ]);
});

test("pickActivePortfolioId prefers an explicitly requested portfolio", () => {
  const portfolios = normalizePortfolioSummaries([
    { id: "paper-1", mode: "paper" },
    { id: "paper-2", mode: "paper" },
  ]);

  assert.equal(pickActivePortfolioId(portfolios, "paper-1", "paper-2"), "paper-2");
  assert.equal(pickActivePortfolioId(portfolios, "missing", null), "paper-1");
  assert.equal(pickActivePortfolioId([], "paper-1", null), null);
});

test("buildCreatePortfolioPayload rejects blank ids and non-positive capital", () => {
  assert.deepEqual(
    buildCreatePortfolioPayload({
      id: "   ",
      mode: "paper",
      initialCapital: "1000000",
    }),
    { ok: false, error: "账户 ID 不能为空。" }
  );

  assert.deepEqual(
    buildCreatePortfolioPayload({
      id: "paper-1",
      mode: "paper",
      initialCapital: "0",
    }),
    { ok: false, error: "初始资金必须大于 0。" }
  );
});

test("buildCreatePortfolioPayload returns normalized request body", () => {
  assert.deepEqual(
    buildCreatePortfolioPayload({
      id: " paper-1 ",
      mode: "paper",
      initialCapital: "888888",
    }),
    {
      ok: true,
      value: {
        id: "paper-1",
        mode: "paper",
        initial_capital: 888888,
        sim_start_date: null,
      },
    }
  );
});
