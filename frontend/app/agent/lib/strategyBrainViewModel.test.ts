import test from "node:test";
import assert from "node:assert/strict";

import { buildStrategyBrainViewModel } from "./strategyBrainViewModel.ts";

test("buildStrategyBrainViewModel maps state and active run into a brain snapshot", () => {
  const viewModel = buildStrategyBrainViewModel({
    state: {
      portfolio_id: "live",
      market_view: { regime: "bullish", reason: "风险偏好回升" },
      position_level: "medium",
      sector_preferences: [
        { sector: "AI", weight: 0.4, reason: "景气度抬升" },
        { sector: "券商", weight: 0.2, reason: "beta 弹性" },
      ],
      risk_alerts: ["北向资金转弱"],
      source_run_id: "run-2",
      created_at: "2026-03-23T09:00:00",
      updated_at: "2026-03-23T10:00:00",
    },
    runs: [
      {
        id: "run-2",
        portfolio_id: "live",
        run_type: "manual",
        status: "completed",
        candidates: null,
        analysis_results: null,
        decisions: [
          {
            action: "buy",
            stock_code: "600519",
            stock_name: "贵州茅台",
            confidence: 0.72,
            reasoning: "龙头回踩后企稳",
          },
        ],
        plan_ids: ["plan-1"],
        trade_ids: ["trade-1"],
        thinking_process: null,
        state_before: { market_view: "neutral", position_level: "low" },
        state_after: { market_view: "bullish", position_level: "medium" },
        execution_summary: { decision_count: 1, trade_count: 1 },
        error_message: null,
        llm_tokens_used: 1880,
        started_at: "2026-03-23T09:50:00",
        completed_at: "2026-03-23T10:00:00",
      },
    ],
    memoryRules: [],
    reflectionFeed: [],
    strategyHistory: [],
  });

  assert.equal(viewModel.snapshot.marketViewLabel, "bullish");
  assert.equal(viewModel.snapshot.positionLevelLabel, "medium");
  assert.equal(viewModel.snapshot.sectorPreferenceCount, 2);
  assert.equal(viewModel.snapshot.riskAlertCount, 1);
  assert.equal(viewModel.snapshot.activeRun?.id, "run-2");
  assert.equal(viewModel.snapshot.activeRun?.decisionCount, 1);
});

test("buildStrategyBrainViewModel maps memory rules into belief cards", () => {
  const viewModel = buildStrategyBrainViewModel({
    state: null,
    runs: [],
    memoryRules: [
      {
        id: "rule-1",
        rule_text: "放量突破后回踩 5 日线更容易走二波",
        category: "short_term",
        source_run_id: "run-1",
        status: "active",
        confidence: 0.78,
        verify_count: 9,
        verify_win: 6,
        created_at: "2026-03-20T10:00:00",
        retired_at: null,
      },
      {
        id: "rule-2",
        rule_text: "弱势市场追高券商容易吃回撤",
        category: "risk_control",
        source_run_id: "run-2",
        status: "retired",
        confidence: 0.55,
        verify_count: 4,
        verify_win: 1,
        created_at: "2026-03-19T10:00:00",
        retired_at: "2026-03-23T10:00:00",
      },
    ],
    reflectionFeed: [],
    strategyHistory: [],
  });

  assert.equal(viewModel.beliefs.length, 2);
  assert.equal(viewModel.beliefs[0].title, "放量突破后回踩 5 日线更容易走二波");
  assert.equal(viewModel.beliefs[0].confidencePct, 78);
  assert.equal(viewModel.beliefs[1].statusTone, "muted");
});

test("buildStrategyBrainViewModel maps runs into decision timeline nodes", () => {
  const viewModel = buildStrategyBrainViewModel({
    state: null,
    runs: [
      {
        id: "run-3",
        portfolio_id: "live",
        run_type: "scheduled",
        status: "completed",
        candidates: [{ stock_code: "000001", stock_name: "平安银行", source: "watchlist" }],
        analysis_results: null,
        decisions: [
          {
            action: "reduce",
            stock_code: "600519",
            stock_name: "贵州茅台",
            confidence: 0.61,
            reasoning: "短期涨幅过快，先锁一部分利润",
          },
        ],
        plan_ids: [],
        trade_ids: ["trade-9"],
        thinking_process: "先检查仓位风险，再处理兑现收益的标的。",
        state_before: { position_level: "high", market_view: "bullish" },
        state_after: { position_level: "medium", market_view: "bullish" },
        execution_summary: { candidate_count: 1, decision_count: 1, trade_count: 1 },
        error_message: null,
        llm_tokens_used: 920,
        started_at: "2026-03-23T14:50:00",
        completed_at: "2026-03-23T15:00:00",
      },
    ],
    memoryRules: [],
    reflectionFeed: [],
    strategyHistory: [],
  });

  assert.equal(viewModel.timeline.length, 1);
  assert.equal(viewModel.timeline[0].title, "scheduled · completed");
  assert.equal(viewModel.timeline[0].decisionCount, 1);
  assert.equal(viewModel.timeline[0].decisions[0].stockCode, "600519");
  assert.equal(viewModel.timeline[0].deltaSummary[0], "仓位: high -> medium");
});

test("buildStrategyBrainViewModel maps reflections and strategy history into evolution feed", () => {
  const viewModel = buildStrategyBrainViewModel({
    state: null,
    runs: [],
    memoryRules: [],
    reflectionFeed: [
      {
        id: "reflection-1",
        kind: "daily",
        date: "2026-03-23",
        summary: "今天追价偏多，午后应该更克制。",
        metrics: { win_rate: 0.5, total_trades: 2 },
        details: null,
      },
    ],
    strategyHistory: [
      {
        id: "history-1",
        run_id: "run-2",
        occurred_at: "2026-03-23T10:00:00",
        market_view: { regime: "bullish" },
        position_level: "medium",
        sector_preferences: [{ sector: "AI" }],
        risk_alerts: ["北向资金转弱"],
        execution_counters: { trade_count: 1 },
      },
    ],
  });

  assert.equal(viewModel.evolution.reflectionCards.length, 1);
  assert.equal(viewModel.evolution.reflectionCards[0].title, "daily · 2026-03-23");
  assert.equal(viewModel.evolution.strategyNodes.length, 1);
  assert.equal(viewModel.evolution.strategyNodes[0].positionLevel, "medium");
  assert.equal(viewModel.evolution.strategyNodes[0].marketViewLabel, "bullish");
});

test("buildStrategyBrainViewModel returns safe defaults for empty data", () => {
  const viewModel = buildStrategyBrainViewModel({
    state: null,
    runs: [],
    memoryRules: [],
    reflectionFeed: [],
    strategyHistory: [],
  });

  assert.equal(viewModel.snapshot.marketViewLabel, "未设置");
  assert.equal(viewModel.beliefs.length, 0);
  assert.equal(viewModel.timeline.length, 0);
  assert.equal(viewModel.evolution.reflectionCards.length, 0);
  assert.equal(viewModel.evolution.strategyNodes.length, 0);
});
