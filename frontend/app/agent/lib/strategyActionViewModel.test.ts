import test from "node:test";
import assert from "node:assert/strict";

import {
  buildMemoRequestConfig,
  buildStrategyExecutionRequestConfig,
  mapExecutionRecord,
  mergeStrategyCardState,
} from "./strategyActionViewModel.ts";

test("mergeStrategyCardState keeps execution and memo badges independent", () => {
  const merged = mergeStrategyCardState(
    {
      id: "action-1",
      decision: "adopted",
      status: "adopted",
      reason: null,
      updated_at: "2026-03-23T10:00:00",
      is_submitting: false,
      error: null,
    },
    {
      id: "memo-1",
      saved: true,
      note: "回头对照复盘",
      updated_at: "2026-03-23T10:01:00",
      is_submitting: false,
      error: null,
    }
  );

  assert.equal(merged.executionLabel, "已采纳");
  assert.equal(merged.memoLabel, "已收藏");
  assert.equal(merged.canAdopt, false);
  assert.equal(merged.canReject, false);
  assert.equal(merged.canSaveMemo, false);
});

test("mergeStrategyCardState keeps execution buttons available when only memo is saved", () => {
  const merged = mergeStrategyCardState(undefined, {
    id: "memo-1",
    saved: true,
    note: null,
    updated_at: "2026-03-23T10:01:00",
    is_submitting: false,
    error: null,
  });

  assert.equal(merged.executionLabel, null);
  assert.equal(merged.memoLabel, "已收藏");
  assert.equal(merged.canAdopt, true);
  assert.equal(merged.canReject, true);
  assert.equal(merged.canSaveMemo, false);
});

test("mapExecutionRecord normalizes adopted and rejected action payloads", () => {
  const adopted = mapExecutionRecord({
    id: "action-1",
    session_id: "session-1",
    message_id: "message-1",
    strategy_key: "600519|buy|100.0000|120.0000|90.0000|2026-04-01",
    decision: "adopted",
    status: "adopted",
    reason: null,
    updated_at: "2026-03-23T10:00:00",
  });
  const rejected = mapExecutionRecord({
    id: "action-2",
    session_id: "session-1",
    message_id: "message-2",
    strategy_key: "000001|buy|10.0000|12.0000|9.0000|2026-04-01",
    decision: "rejected",
    status: "rejected",
    reason: "等回调",
    updated_at: "2026-03-23T10:01:00",
  });

  assert.equal(adopted?.decision, "adopted");
  assert.equal(rejected?.decision, "rejected");
  assert.equal(rejected?.reason, "等回调");
});

test("buildStrategyExecutionRequestConfig routes adopt intent to adopt endpoint", () => {
  const request = buildStrategyExecutionRequestConfig("adopt", {
    portfolio_id: "live",
    session_id: "session-1",
    message_id: "message-1",
    strategy_key: "600519|buy|100.0000|120.0000|90.0000|2026-04-01",
    source_run_id: "run-1",
    plan: {
      stock_code: "600519",
      stock_name: "贵州茅台",
      direction: "buy",
      current_price: 100,
      entry_price: 100,
      entry_method: "分批",
      position_pct: 0.1,
      take_profit: 120,
      take_profit_method: "120 附近分批止盈",
      stop_loss: 90,
      stop_loss_method: "90 附近止损",
      reasoning: "龙头企稳，准备执行",
      risk_note: "消费恢复不及预期",
      invalidation: "跌破 90",
      valid_until: "2026-04-01",
    },
  });

  assert.equal(request.endpoint, "/api/v1/agent/adopt-strategy");
  assert.equal(request.method, "POST");
  assert.equal(request.body.portfolio_id, "live");
});

test("buildStrategyExecutionRequestConfig routes reject intent to reject endpoint", () => {
  const request = buildStrategyExecutionRequestConfig("reject", {
    portfolio_id: "live",
    session_id: "session-1",
    message_id: "message-1",
    strategy_key: "600519|buy|100.0000|120.0000|90.0000|2026-04-01",
    source_run_id: "run-1",
    plan: {
      stock_code: "600519",
      stock_name: "贵州茅台",
      direction: "buy",
      current_price: 100,
      entry_price: 100,
      entry_method: "分批",
      position_pct: 0.1,
      take_profit: 120,
      take_profit_method: "120 附近分批止盈",
      stop_loss: 90,
      stop_loss_method: "90 附近止损",
      reasoning: "龙头企稳，准备执行",
      risk_note: "消费恢复不及预期",
      invalidation: "跌破 90",
      valid_until: "2026-04-01",
    },
    reason: "位置太高，等回调",
  });

  assert.equal(request.endpoint, "/api/v1/agent/reject-strategy");
  assert.equal(request.method, "POST");
  assert.equal(request.body.reason, "位置太高，等回调");
});

test("buildMemoRequestConfig keeps save action on memo endpoint", () => {
  const request = buildMemoRequestConfig("live", {
    session_id: "session-1",
    message_id: "message-1",
    strategy_key: "600519|buy|100.0000|120.0000|90.0000|2026-04-01",
    plan: {
      stock_code: "600519",
      stock_name: "贵州茅台",
      direction: "buy",
      current_price: 100,
      entry_price: 100,
      entry_method: "分批",
      position_pct: 0.1,
      take_profit: 120,
      take_profit_method: "120 附近分批止盈",
      stop_loss: 90,
      stop_loss_method: "90 附近止损",
      reasoning: "龙头企稳，准备执行",
      risk_note: "消费恢复不及预期",
      invalidation: "跌破 90",
      valid_until: "2026-04-01",
    },
    note: "加入个人观察池",
  });

  assert.equal(request.endpoint, "/api/v1/agent/strategy-memos");
  assert.equal(request.method, "POST");
  assert.equal(request.body.status, "saved");
  assert.equal(request.body.note, "加入个人观察池");
});
