import test from "node:test";
import assert from "node:assert/strict";

import { extractInfoReview, omitInfoReview } from "./reflectionFeed.ts";

test("extractInfoReview returns normalized counters and daily digest entries", () => {
  const infoReview = extractInfoReview({
    portfolio_id: "live",
    info_review: {
      summary: "信息复盘：有效信号占优",
      details: {
        digest_count: 3,
        useful_count: 2,
        misleading_count: 1,
        inconclusive_count: 0,
        noted_count: 0,
        top_missing_sources: ["filing", "channel"],
        items: [
          {
            digest_id: "digest-1",
            stock_code: "600519",
            review_label: "useful",
            impact_assessment: "minor_adjust",
            summary: "白酒需求回暖",
            missing_sources: [],
          },
        ],
      },
    },
  });

  assert.ok(infoReview);
  assert.equal(infoReview.summary, "信息复盘：有效信号占优");
  assert.deepEqual(
    infoReview.counters.map((item) => [item.key, item.value]),
    [
      ["digest_count", 3],
      ["useful_count", 2],
      ["misleading_count", 1],
      ["inconclusive_count", 0],
      ["noted_count", 0],
    ]
  );
  assert.deepEqual(infoReview.topMissingSources, ["filing", "channel"]);
  assert.equal(infoReview.items.length, 1);
  assert.equal(infoReview.items[0].stockCode, "600519");
  assert.equal(infoReview.items[0].reviewLabel, "useful");
  assert.equal(infoReview.items[0].summary, "白酒需求回暖");
});

test("omitInfoReview keeps non-info details and extractInfoReview normalizes weekly days", () => {
  const details = {
    week_start: "2026-03-16",
    week_end: "2026-03-20",
    notes: "focus on review discipline",
    info_review: {
      summary: "周信息复盘：公告缺口集中",
      details: {
        digest_count: "5",
        useful_count: "2",
        misleading_count: "1",
        inconclusive_count: "1",
        noted_count: "1",
        top_missing_sources: ["filing", 3, null],
        days: [
          {
            review_date: "2026-03-18",
            digest_count: "2",
            useful_count: 1,
            misleading_count: 1,
            inconclusive_count: 0,
            noted_count: 0,
            summary: "次日信息复盘",
          },
        ],
      },
    },
  };

  assert.deepEqual(omitInfoReview(details), {
    week_start: "2026-03-16",
    week_end: "2026-03-20",
    notes: "focus on review discipline",
  });

  const infoReview = extractInfoReview(details);
  assert.ok(infoReview);
  assert.deepEqual(infoReview.topMissingSources, ["filing"]);
  assert.equal(infoReview.days.length, 1);
  assert.deepEqual(infoReview.days[0], {
    reviewDate: "2026-03-18",
    digestCount: 2,
    usefulCount: 1,
    misleadingCount: 1,
    inconclusiveCount: 0,
    notedCount: 0,
    summary: "次日信息复盘",
  });
});
