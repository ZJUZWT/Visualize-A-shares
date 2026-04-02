import test from "node:test";
import assert from "node:assert/strict";

import { normalizeExpertLearningProfile } from "./expertLearning.ts";

test("normalizeExpertLearningProfile reorders verified knowledge for data vs short_term", () => {
  const raw = {
    portfolio_id: "paper-1",
    expert_type: "rag",
    score_cards: [],
    verified_knowledge: [
      {
        id: "mem-risk",
        title: "短线不能逆势追高",
        category: "risk",
        confidence: 0.91,
        verify_count: 6,
      },
      {
        id: "mem-data",
        title: "成交额不够时先别把突破当确认",
        category: "data_validation",
        confidence: 0.84,
        verify_count: 5,
      },
    ],
    recent_lessons: [],
    common_mistakes: [],
    applicability_boundaries: [],
    source_summary: {
      review_count: 2,
      memory_count: 2,
      reflection_count: 1,
      win_rate: 0.5,
    },
    pending_plan_summary: {
      expert_plan_count: 1,
    },
  };

  const dataView = normalizeExpertLearningProfile(raw, "data");
  const shortTermView = normalizeExpertLearningProfile(raw, "short_term");

  assert.equal(dataView.verifiedKnowledge[0]?.id, "mem-data");
  assert.equal(shortTermView.verifiedKnowledge[0]?.id, "mem-risk");
});

test("normalizeExpertLearningProfile builds empty state when evidence is missing", () => {
  const view = normalizeExpertLearningProfile(
    {
      portfolio_id: "paper-1",
      expert_type: "data",
      score_cards: [],
      verified_knowledge: [],
      recent_lessons: [],
      common_mistakes: [],
      applicability_boundaries: [],
      source_summary: {
        review_count: 0,
        memory_count: 0,
        reflection_count: 0,
        win_rate: 0,
      },
      pending_plan_summary: {
        expert_plan_count: 0,
      },
    },
    "data",
  );

  assert.equal(view.isEmpty, true);
  assert.match(view.emptyMessage, /还没有足够复盘数据/);
});

test("normalizeExpertLearningProfile keeps non-empty state when recent plan lessons already exist", () => {
  const view = normalizeExpertLearningProfile(
    {
      portfolio_id: "paper-1",
      expert_type: "data",
      score_cards: [],
      verified_knowledge: [],
      recent_lessons: [
        {
          id: "plan-review-1",
          title: "回踩确认后再分批低吸，这次节奏是成立的。",
          category: "plan_review:useful",
          date: "2026-04-02",
        },
      ],
      common_mistakes: [],
      applicability_boundaries: [],
      source_summary: {
        review_count: 0,
        memory_count: 0,
        reflection_count: 0,
        win_rate: 0,
      },
      pending_plan_summary: {
        expert_plan_count: 0,
      },
    },
    "data",
  );

  assert.equal(view.isEmpty, false);
  assert.equal(view.recentLessons[0]?.id, "plan-review-1");
});
