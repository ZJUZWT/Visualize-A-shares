import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeReplayLearning,
  summarizeReplayLearning,
} from "./replayLearningViewModel.ts";

test("normalizeReplayLearning returns stable replay learning payload", () => {
  const learning = normalizeReplayLearning("live", {
    portfolio_id: "live",
    date: "2026-03-20",
    what_ai_knew: {
      trade_theses: ["减仓锁定阶段收益"],
      run_ids: ["run-1"],
    },
    what_happened: {
      review_statuses: ["win"],
      next_day_move_pct: "2.68",
    },
    counterfactual: {
      would_change: false,
      action_bias: "hold_course",
      rationale: "当时的动作和事后结果基本一致，优先保留原计划。",
    },
    lesson_summary: "减仓锁定阶段收益；复盘结论：当时的动作和事后结果基本一致，优先保留原计划。",
  });

  assert.deepEqual(learning, {
    portfolio_id: "live",
    date: "2026-03-20",
    what_ai_knew: {
      trade_theses: ["减仓锁定阶段收益"],
      plan_reasoning: [],
      trade_reasons: [],
      run_ids: ["run-1"],
    },
    what_happened: {
      review_statuses: ["win"],
      next_day_move_pct: 2.68,
      total_asset_mark_to_market_close: null,
      total_asset_realized_only_close: null,
    },
    counterfactual: {
      would_change: false,
      action_bias: "hold_course",
      rationale: "当时的动作和事后结果基本一致，优先保留原计划。",
    },
    lesson_summary: "减仓锁定阶段收益；复盘结论：当时的动作和事后结果基本一致，优先保留原计划。",
  });
});

test("summarizeReplayLearning maps counterfactual change into warn tone", () => {
  const summary = summarizeReplayLearning({
    portfolio_id: "live",
    date: "2026-03-20",
    what_ai_knew: {
      trade_theses: [],
      plan_reasoning: [],
      trade_reasons: [],
      run_ids: [],
    },
    what_happened: {
      review_statuses: ["loss"],
      next_day_move_pct: -3.2,
      total_asset_mark_to_market_close: null,
      total_asset_realized_only_close: null,
    },
    counterfactual: {
      would_change: true,
      action_bias: "tighten_confirmation",
      rationale: "事后复盘出现亏损，下一次应先提高确认门槛。",
    },
    lesson_summary: "如果重来一次，应先提高确认门槛。",
  });

  assert.equal(summary.badgeTone, "warn");
  assert.match(summary.headline, /确认门槛/);
});
