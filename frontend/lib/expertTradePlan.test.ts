import test from "node:test";
import assert from "node:assert/strict";

import type { TradePlanData } from "./parseTradePlan.ts";
import { buildExpertTradePlanPayload } from "./expertTradePlan.ts";

const SAMPLE_PLAN: TradePlanData = {
  stock_code: "300750",
  stock_name: "宁德时代",
  current_price: 218.5,
  direction: "buy",
  entry_price: "215 / 210",
  entry_method: "分批低吸",
  win_odds: "2:1",
  take_profit: "235 / 248",
  take_profit_method: "分批止盈",
  stop_loss: 205,
  stop_loss_method: "跌破止损位离场",
  reasoning: "量价结构仍有修复空间。",
  risk_note: "若板块转弱需降低仓位。",
  invalidation: "放量跌破平台支撑。",
  valid_until: "2026-04-15",
};

test("buildExpertTradePlanPayload includes source conversation id and source message id when provided", () => {
  assert.deepEqual(buildExpertTradePlanPayload(SAMPLE_PLAN, "session-123", "msg-456"), {
    ...SAMPLE_PLAN,
    source_conversation_id: "session-123",
    source_message_id: "msg-456",
  });
});

test("buildExpertTradePlanPayload omits source ids when unavailable", () => {
  assert.deepEqual(buildExpertTradePlanPayload(SAMPLE_PLAN, null, null), SAMPLE_PLAN);
});
