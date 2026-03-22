import test from "node:test";
import assert from "node:assert/strict";

import {
  buildWatchSignalPayload,
  filterInfoDigestsForRun,
  normalizeInfoDigests,
  normalizeWatchSignals,
  summarizeWatchSignals,
} from "./wakeViewModel.ts";

test("normalizeWatchSignals parses keywords and evidence defensively", () => {
  const signals = normalizeWatchSignals({
    items: [
      {
        id: "signal-1",
        portfolio_id: "demo",
        stock_code: "600519",
        sector: "白酒",
        signal_description: "渠道价企稳",
        check_engine: "info",
        keywords: ["渠道", "价格"],
        if_triggered: "重新评估仓位",
        cycle_context: "去库存尾声",
        status: "watching",
        trigger_evidence: [
          "经销商反馈改善",
          { title: "渠道跟踪", type: "news", summary: "终端价格止跌" },
        ],
      },
    ],
  });

  assert.equal(signals.length, 1);
  assert.deepEqual(signals[0].keywords, ["渠道", "价格"]);
  assert.equal(signals[0].trigger_evidence.length, 2);
  assert.equal(signals[0].trigger_evidence[0].summary, "经销商反馈改善");
  assert.equal(signals[0].trigger_evidence[1].title, "渠道跟踪");
});

test("summarizeWatchSignals counts statuses for wake overview cards", () => {
  const summary = summarizeWatchSignals([
    {
      id: "a",
      portfolio_id: null,
      stock_code: null,
      sector: null,
      signal_description: "A",
      check_engine: null,
      keywords: [],
      if_triggered: null,
      cycle_context: null,
      status: "watching",
      trigger_evidence: [],
      source_run_id: null,
      created_at: null,
      updated_at: null,
      triggered_at: null,
    },
    {
      id: "b",
      portfolio_id: null,
      stock_code: null,
      sector: null,
      signal_description: "B",
      check_engine: null,
      keywords: [],
      if_triggered: null,
      cycle_context: null,
      status: "triggered",
      trigger_evidence: [],
      source_run_id: null,
      created_at: null,
      updated_at: null,
      triggered_at: null,
    },
    {
      id: "c",
      portfolio_id: null,
      stock_code: null,
      sector: null,
      signal_description: "C",
      check_engine: null,
      keywords: [],
      if_triggered: null,
      cycle_context: null,
      status: "cancelled",
      trigger_evidence: [],
      source_run_id: null,
      created_at: null,
      updated_at: null,
      triggered_at: null,
    },
  ]);

  assert.deepEqual(summary, {
    total: 3,
    watching: 1,
    triggered: 1,
    inactive: 1,
  });
});

test("normalizeInfoDigests extracts summary, evidence and risk flags", () => {
  const digests = normalizeInfoDigests({
    items: [
      {
        id: "digest-1",
        portfolio_id: "demo",
        run_id: "run-1",
        stock_code: "600519",
        digest_type: "wake",
        structured_summary: {
          summary: "渠道价格止跌，库存压力缓解",
          key_evidence: ["news_count=3", "announcement_count=1"],
          risk_flags: ["missing_sources=technical_indicators"],
        },
        strategy_relevance: "watch signal triggered",
        impact_assessment: "minor_adjust",
        missing_sources: ["technical_indicators"],
        created_at: "2026-03-22T12:00:00",
      },
    ],
  });

  assert.equal(digests.length, 1);
  assert.equal(digests[0].summary, "渠道价格止跌，库存压力缓解");
  assert.deepEqual(digests[0].key_evidence, ["news_count=3", "announcement_count=1"]);
  assert.deepEqual(digests[0].risk_flags, ["missing_sources=technical_indicators"]);
});

test("filterInfoDigestsForRun prefers selected run and falls back to recent when empty", () => {
  const digests = normalizeInfoDigests([
    {
      id: "digest-1",
      run_id: "run-1",
      stock_code: "600519",
      digest_type: "wake",
      structured_summary: { summary: "run 1 digest" },
    },
    {
      id: "digest-2",
      run_id: "run-2",
      stock_code: "300750",
      digest_type: "wake",
      structured_summary: { summary: "run 2 digest" },
    },
  ]);

  const selectedRun = filterInfoDigestsForRun(digests, "run-1", "selected_run");
  const fallbackRecent = filterInfoDigestsForRun(digests, "run-3", "selected_run");
  const recent = filterInfoDigestsForRun(digests, "run-1", "recent");

  assert.deepEqual(selectedRun.map((item) => item.id), ["digest-1"]);
  assert.deepEqual(fallbackRecent.map((item) => item.id), ["digest-1", "digest-2"]);
  assert.deepEqual(recent.map((item) => item.id), ["digest-1", "digest-2"]);
});

test("buildWatchSignalPayload trims fields and splits comma keywords", () => {
  const payload = buildWatchSignalPayload("demo", {
    stock_code: " 600519 ",
    sector: " 白酒 ",
    signal_description: " 渠道价企稳 ",
    keywords: " 渠道 , 价格,渠道 ",
    if_triggered: " 加仓并复核盈利预测 ",
    cycle_context: " 去库存尾声 ",
  });

  assert.deepEqual(payload, {
    portfolio_id: "demo",
    stock_code: "600519",
    sector: "白酒",
    signal_description: "渠道价企稳",
    check_engine: "info",
    keywords: ["渠道", "价格"],
    if_triggered: "加仓并复核盈利预测",
    cycle_context: "去库存尾声",
    status: "watching",
  });
});
