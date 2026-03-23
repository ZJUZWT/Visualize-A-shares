import test from "node:test";
import assert from "node:assert/strict";

import { buildRightRailPositionGroups } from "./rightRailPositionViewModel.ts";

test("buildRightRailPositionGroups groups positions by holding type and preserves order", () => {
  const groups = buildRightRailPositionGroups([
    {
      id: "p1",
      stock_code: "600519",
      stock_name: "贵州茅台",
      holding_type: "mid_term",
      entry_price: 1800,
      current_qty: 100,
      cost_basis: 180000,
      status: "open",
      entry_date: "2026-03-20",
      market_value: 180000,
      unrealized_pnl: 0,
      unrealized_pnl_pct: 0,
      position_pct: 0.6,
      status_signal: "healthy",
      status_reason: "策略阈值仍处于正常观察区间",
      latest_strategy: null,
    },
    {
      id: "p2",
      stock_code: "002594",
      stock_name: "比亚迪",
      holding_type: "long_term",
      entry_price: 240,
      current_qty: 200,
      cost_basis: 48000,
      status: "open",
      entry_date: "2026-03-19",
      market_value: 50000,
      unrealized_pnl: 2000,
      unrealized_pnl_pct: 4.17,
      position_pct: 0.4,
      status_signal: "warning",
      status_reason: "止盈空间有限，建议关注执行节奏",
      latest_strategy: null,
    },
  ]);

  assert.equal(groups.length, 2);
  assert.equal(groups[0].key, "long_term");
  assert.equal(groups[1].key, "mid_term");
  assert.equal(groups[0].items[0].stockCode, "002594");
});

test("buildRightRailPositionGroups extracts long term strategy highlights", () => {
  const groups = buildRightRailPositionGroups([
    {
      id: "p1",
      stock_code: "002594",
      stock_name: "比亚迪",
      holding_type: "long_term",
      entry_price: 240,
      current_qty: 200,
      cost_basis: 48000,
      status: "open",
      entry_date: "2026-03-19",
      market_value: 50000,
      unrealized_pnl: 2000,
      unrealized_pnl_pct: 4.17,
      position_pct: 0.4,
      status_signal: "healthy",
      status_reason: "策略阈值仍处于正常观察区间",
      latest_strategy: {
        id: "strategy-1",
        holding_type: "long_term",
        take_profit: 300,
        stop_loss: 210,
        reasoning: "行业景气与龙头份额逻辑未破坏",
        details: {
          fundamental_anchor: "电动车渗透率持续上行",
          exit_condition: "销量增速连续两个季度失速",
          rebalance_trigger: "若价格战扩大则减仓 1/3",
        },
        version: 2,
        source_run_id: "run-1",
        created_at: "2026-03-20T10:00:00",
        updated_at: "2026-03-23T10:00:00",
      },
    },
  ]);

  const card = groups[0].items[0];

  assert.equal(card.highlights[0].label, "基本面锚点");
  assert.equal(card.highlights[0].value, "电动车渗透率持续上行");
  assert.equal(card.highlights[1].label, "离场条件");
});

test("buildRightRailPositionGroups extracts mid term strategy highlights", () => {
  const groups = buildRightRailPositionGroups([
    {
      id: "p1",
      stock_code: "600519",
      stock_name: "贵州茅台",
      holding_type: "mid_term",
      entry_price: 1800,
      current_qty: 100,
      cost_basis: 180000,
      status: "open",
      entry_date: "2026-03-20",
      market_value: 186000,
      unrealized_pnl: 6000,
      unrealized_pnl_pct: 3.33,
      position_pct: 0.6,
      status_signal: "warning",
      status_reason: "浮盈已较大，需关注兑现或上调止盈",
      latest_strategy: {
        id: "strategy-2",
        holding_type: "mid_term",
        take_profit: 1950,
        stop_loss: 1700,
        reasoning: "沿 20 日线趋势持有",
        details: {
          trend_indicator: "20日均线",
          add_position_price: 1760,
          half_exit_price: 1930,
          target_catalyst: "业绩继续修复",
        },
        version: 1,
        source_run_id: "run-2",
        created_at: "2026-03-20T10:00:00",
        updated_at: "2026-03-23T10:00:00",
      },
    },
  ]);

  const card = groups[0].items[0];

  assert.equal(card.signal.label, "接近阈值");
  assert.equal(card.highlights[0].label, "趋势指标");
  assert.equal(card.highlights[2].label, "减仓位");
});

test("buildRightRailPositionGroups falls back when no latest strategy exists", () => {
  const groups = buildRightRailPositionGroups([
    {
      id: "p1",
      stock_code: "300750",
      stock_name: "宁德时代",
      holding_type: "short_term",
      entry_price: 200,
      current_qty: 100,
      cost_basis: 20000,
      status: "open",
      entry_date: "2026-03-22",
      market_value: 18800,
      unrealized_pnl: -1200,
      unrealized_pnl_pct: -6,
      position_pct: 1,
      status_signal: "danger",
      status_reason: "浮亏已超过 5%，接近防守阈值",
      latest_strategy: null,
    },
  ]);

  const card = groups[0].items[0];

  assert.equal(card.signal.label, "触发风险");
  assert.equal(card.highlights.length, 1);
  assert.equal(card.highlights[0].label, "策略");
});
