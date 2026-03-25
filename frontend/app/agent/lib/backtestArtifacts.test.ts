import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeBacktestDays,
  normalizeBacktestSummary,
} from "./backtestArtifacts.ts";

test("normalizeBacktestSummary keeps numeric fields and requires run id", () => {
  assert.equal(normalizeBacktestSummary({ status: "done" }), null);

  assert.deepEqual(
    normalizeBacktestSummary({
      run_id: "bt-1",
      status: "completed",
      total_return: "12.5",
      trade_count: 4,
      memory_added: "2",
    }),
    {
      run_id: "bt-1",
      status: "completed",
      start_date: null,
      end_date: null,
      total_return: 12.5,
      max_drawdown: null,
      trade_count: 4,
      win_rate: null,
      review_count: null,
      memory_added: 2,
      memory_updated: null,
      memory_retired: null,
      buy_and_hold_return: null,
    }
  );
});

test("normalizeBacktestDays filters invalid rows and returns stable day records", () => {
  assert.deepEqual(
    normalizeBacktestDays([
      {
        run_id: "bt-1",
        trade_date: "2026-03-20",
        brain_run_id: "brain-1",
        review_created: true,
        memory_delta: { added: 1 },
      },
      {
        run_id: "bt-1",
      },
    ]),
    [
      {
        id: undefined,
        run_id: "bt-1",
        portfolio_id: null,
        trade_date: "2026-03-20",
        brain_run_id: "brain-1",
        review_created: true,
        memory_delta: { added: 1 },
        created_at: null,
      },
    ]
  );
});
