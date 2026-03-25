import test from "node:test";
import assert from "node:assert/strict";

import { buildPetConsoleViewModel } from "./petConsoleViewModel.ts";

test("buildPetConsoleViewModel maps running brain run to thinking pet mood", () => {
  const viewModel = buildPetConsoleViewModel({
    activeRun: {
      id: "run-1",
      portfolio_id: "demo",
      run_type: "manual",
      status: "running",
      candidates: null,
      analysis_results: null,
      decisions: null,
      plan_ids: null,
      trade_ids: null,
      thinking_process: null,
      state_before: null,
      state_after: null,
      execution_summary: null,
      error_message: null,
      llm_tokens_used: 0,
      started_at: "2026-03-23T10:00:00",
      completed_at: null,
    },
    ledgerOverview: null,
    agentState: null,
    strategySummary: null,
    suiteResult: null,
  });

  assert.equal(viewModel.pet.mood, "thinking");
  assert.match(viewModel.pet.statusLabel, /思考|运行/);
});

test("buildPetConsoleViewModel maps smoke suite result into training summary", () => {
  const viewModel = buildPetConsoleViewModel({
    activeRun: null,
    ledgerOverview: null,
    agentState: {
      portfolio_id: "demo",
      market_view: { stance: "selective-risk-on" },
      position_level: "0.35",
      sector_preferences: ["consumer"],
      risk_alerts: ["demo-cycle-open-position"],
      source_run_id: "run-demo",
      created_at: "2026-03-23T10:00:00",
      updated_at: "2026-03-23T10:10:00",
    },
    strategySummary: "保持选择性进攻，回撤时优先自检。",
    suiteResult: {
      mode: "smoke",
      overall_status: "warn",
      scenario_id: "demo-evolution",
      portfolio_id: "demo-evolution",
      seed_summary: {},
      demo_verification: {
        verification_status: "pass",
        run_id: "verify-1",
      },
      backtest: {
        status: "completed",
        run_id: "bt-1",
        summary: {
          trade_count: 1,
          review_count: 4,
          memory_added: 0,
          memory_updated: 0,
          memory_retired: 0,
        },
      },
      evidence: {
        verification_run_id: "verify-1",
        backtest_run_id: "bt-1",
      },
      next_actions: ["backtest weak signal: no memory movement"],
    },
  });

  assert.equal(viewModel.training.modeLabel, "Smoke");
  assert.equal(viewModel.training.statusTone, "warn");
  assert.equal(viewModel.pet.mood, "training");
  assert.match(viewModel.training.summary, /reviews 4/i);
});

test("buildPetConsoleViewModel maps open positions into battle readiness", () => {
  const viewModel = buildPetConsoleViewModel({
    activeRun: null,
    ledgerOverview: {
      portfolio_id: "demo",
      account: {
        cash_balance: 800000,
        total_asset: 1005000,
        total_pnl: 5000,
        total_pnl_pct: 0.5,
        position_count: 1,
        pending_plan_count: 1,
        trade_count: 3,
      },
      positions: [
        {
          id: "pos-1",
          stock_code: "600519",
          stock_name: "贵州茅台",
        },
      ],
      pending_plans: [
        {
          id: "plan-1",
          stock_code: "600519",
          stock_name: "贵州茅台",
          direction: "buy",
          status: "pending",
        },
      ],
      recent_trades: [],
    },
    agentState: null,
    strategySummary: null,
    suiteResult: null,
  });

  assert.equal(viewModel.battle.readinessLabel, "已出战");
  assert.equal(viewModel.pet.mood, "battle");
});

test("buildPetConsoleViewModel maps negative pnl into drawdown mood", () => {
  const viewModel = buildPetConsoleViewModel({
    activeRun: null,
    ledgerOverview: {
      portfolio_id: "demo",
      account: {
        cash_balance: 700000,
        total_asset: 930000,
        total_pnl: -70000,
        total_pnl_pct: -7,
        position_count: 2,
        pending_plan_count: 0,
        trade_count: 8,
      },
      positions: [],
      pending_plans: [],
      recent_trades: [],
    },
    agentState: null,
    strategySummary: null,
    suiteResult: null,
  });

  assert.equal(viewModel.pet.mood, "drawdown");
  assert.match(viewModel.pet.statusLabel, /回撤/);
});
