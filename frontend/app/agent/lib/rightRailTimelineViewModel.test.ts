import test from "node:test";
import assert from "node:assert/strict";

import {
  buildEquityPolylinePoints,
  clampReplayDate,
  normalizeEquityTimeline,
  normalizeReplaySnapshot,
  pickDefaultReplayDate,
  summarizeEquityTimeline,
} from "./rightRailTimelineViewModel.ts";

test("normalizeEquityTimeline returns stable defaults for missing fields", () => {
  const timeline = normalizeEquityTimeline("live", {});

  assert.deepEqual(timeline, {
    portfolio_id: "live",
    start_date: null,
    end_date: null,
    mark_to_market: [],
    realized_only: [],
  });
});

test("normalizeReplaySnapshot parses nested arrays and numeric fields defensively", () => {
  const replay = normalizeReplaySnapshot("live", {
    date: "2026-03-20",
    account: {
      cash_balance: "991000",
      total_asset_mark_to_market: 1002200,
      total_asset_realized_only: "1001000",
      realized_pnl: "1000",
      unrealized_pnl: 1200,
    },
    positions: [
      {
        id: "pos-1",
        stock_code: "600519",
        current_qty: "100",
        cost_basis: "10000",
        close_price: 112,
      },
    ],
    trades: [{ id: "trade-1", stock_code: "600519", action: "reduce" }],
    what_ai_knew: {
      trade_theses: ["减仓锁定阶段收益"],
      plan_reasoning: ["短期涨幅已兑现一部分"],
    },
    what_happened: {
      review_statuses: ["win"],
      next_day_move_pct: "2.68",
    },
  });

  assert.equal(replay.portfolio_id, "live");
  assert.equal(replay.date, "2026-03-20");
  assert.equal(replay.account.cash_balance, 991000);
  assert.equal(replay.account.total_asset_realized_only, 1001000);
  assert.equal(replay.positions.length, 1);
  assert.equal(replay.positions[0].current_qty, 100);
  assert.deepEqual(replay.what_ai_knew.trade_theses, ["减仓锁定阶段收益"]);
  assert.equal(replay.what_happened.next_day_move_pct, 2.68);
});

test("pickDefaultReplayDate prefers the last timeline day and clamps within bounds", () => {
  const timeline = normalizeEquityTimeline("live", {
    start_date: "2026-03-18",
    end_date: "2026-03-20",
    mark_to_market: [
      { date: "2026-03-18", equity: 1000000 },
      { date: "2026-03-20", equity: 1002200 },
    ],
    realized_only: [],
  });

  assert.equal(pickDefaultReplayDate(timeline, "2026-03-23"), "2026-03-20");
  assert.equal(clampReplayDate("2026-03-01", "2026-03-18", "2026-03-20"), "2026-03-18");
  assert.equal(clampReplayDate("2026-03-25", "2026-03-18", "2026-03-20"), "2026-03-20");
});

test("summarizeEquityTimeline and buildEquityPolylinePoints expose chart-ready values", () => {
  const timeline = normalizeEquityTimeline("live", {
    mark_to_market: [
      { date: "2026-03-18", equity: 1000000 },
      { date: "2026-03-19", equity: 1000500 },
      { date: "2026-03-20", equity: 1002200 },
    ],
    realized_only: [
      { date: "2026-03-18", equity: 1000000 },
      { date: "2026-03-19", equity: 1000000 },
      { date: "2026-03-20", equity: 1001000 },
    ],
  });

  const summary = summarizeEquityTimeline(timeline);
  assert.equal(summary.latest_mark_to_market, 1002200);
  assert.equal(summary.latest_realized_only, 1001000);
  assert.equal(summary.unrealized_delta, 1200);

  const points = buildEquityPolylinePoints(timeline.mark_to_market, 300, 100);
  assert.match(points, /^\d+(\.\d+)?,\d+(\.\d+)? \d+(\.\d+)?,\d+(\.\d+)? \d+(\.\d+)?,\d+(\.\d+)?$/);
});
