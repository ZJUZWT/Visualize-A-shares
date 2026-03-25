import test from "node:test";
import assert from "node:assert/strict";

import { normalizeWatchlist } from "./watchlist.ts";

test("normalizeWatchlist returns empty array for non-array payloads", () => {
  assert.deepEqual(normalizeWatchlist({}), []);
  assert.deepEqual(normalizeWatchlist(null), []);
});

test("normalizeWatchlist keeps valid items and filters malformed rows", () => {
  const result = normalizeWatchlist([
    {
      id: "watch-1",
      stock_code: "600519",
      stock_name: "贵州茅台",
      reason: "关注白酒",
      added_by: "demo",
      created_at: "2026-03-24T09:00:00",
    },
    {
      id: "watch-2",
      stock_code: "000001",
    },
    "bad-row",
  ]);

  assert.deepEqual(result, [{
    id: "watch-1",
    stock_code: "600519",
    stock_name: "贵州茅台",
    reason: "关注白酒",
    added_by: "demo",
    created_at: "2026-03-24T09:00:00",
  }]);
});
