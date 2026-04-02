import test from "node:test";
import assert from "node:assert/strict";

import { normalizePlanReview, normalizeSavedTradePlanCard } from "./planReview.ts";

test("normalizePlanReview keeps deterministic review fields", () => {
  const review = normalizePlanReview({
    id: "review-1",
    plan_id: "plan-1",
    review_date: "2026-04-02",
    review_window: 5,
    entry_hit: true,
    take_profit_hit: true,
    stop_loss_hit: false,
    invalidation_hit: false,
    max_gain_pct: 13.13,
    max_drawdown_pct: 0,
    close_price: 112,
    outcome_label: "useful",
    summary: "计划触发后命中止盈。",
    lesson_summary: "等待首档买点确认后再执行，这次节奏成立。",
  });

  assert.deepEqual(review, {
    id: "review-1",
    planId: "plan-1",
    reviewDate: "2026-04-02",
    reviewWindow: 5,
    entryHit: true,
    takeProfitHit: true,
    stopLossHit: false,
    invalidationHit: false,
    maxGainPct: 13.13,
    maxDrawdownPct: 0,
    closePrice: 112,
    outcomeLabel: "useful",
    summary: "计划触发后命中止盈。",
    lessonSummary: "等待首档买点确认后再执行，这次节奏成立。",
  });
});

test("normalizeSavedTradePlanCard extracts latest review", () => {
  const saved = normalizeSavedTradePlanCard({
    id: "plan-1",
    status: "pending",
    created_at: "2026-04-02T09:30:00",
    latest_review: {
      id: "review-1",
      plan_id: "plan-1",
      review_date: "2026-04-02",
      review_window: 5,
      entry_hit: true,
      take_profit_hit: true,
      stop_loss_hit: false,
      invalidation_hit: false,
      max_gain_pct: 13.13,
      max_drawdown_pct: 0,
      close_price: 112,
      outcome_label: "useful",
      summary: "计划触发后命中止盈。",
      lesson_summary: "等待首档买点确认后再执行，这次节奏成立。",
    },
  });

  assert.equal(saved?.id, "plan-1");
  assert.equal(saved?.latestReview?.id, "review-1");
  assert.equal(saved?.latestReview?.outcomeLabel, "useful");
});
