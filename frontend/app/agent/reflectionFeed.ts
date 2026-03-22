import type { ReflectionFeedItem } from "./types";

type ReflectionDetails = ReflectionFeedItem["details"];

const COUNTER_LABELS = {
  digest_count: "Digest",
  useful_count: "有效",
  misleading_count: "误导",
  inconclusive_count: "待确认",
  noted_count: "已记录",
} as const;

type CounterKey = keyof typeof COUNTER_LABELS;

export interface InfoReviewCounter {
  key: CounterKey;
  label: string;
  value: number;
}

export interface InfoReviewDigestEntry {
  digestId: string | null;
  stockCode: string | null;
  reviewLabel: string | null;
  impactAssessment: string | null;
  summary: string | null;
  missingSources: string[];
}

export interface InfoReviewDaySummary {
  reviewDate: string | null;
  digestCount: number;
  usefulCount: number;
  misleadingCount: number;
  inconclusiveCount: number;
  notedCount: number;
  summary: string | null;
}

export interface ReflectionInfoReviewView {
  summary: string | null;
  counters: InfoReviewCounter[];
  topMissingSources: string[];
  items: InfoReviewDigestEntry[];
  days: InfoReviewDaySummary[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

export function omitInfoReview(details: ReflectionDetails): Record<string, unknown> | null {
  if (!isRecord(details)) {
    return null;
  }
  const restEntries = Object.entries(details).filter(([key]) => key !== "info_review");
  if (restEntries.length === 0) {
    return null;
  }
  return Object.fromEntries(restEntries);
}

export function extractInfoReview(details: ReflectionDetails): ReflectionInfoReviewView | null {
  if (!isRecord(details) || !isRecord(details.info_review)) {
    return null;
  }

  const infoReview = details.info_review;
  const detailRecord = isRecord(infoReview.details) ? infoReview.details : {};
  const counters = (Object.keys(COUNTER_LABELS) as CounterKey[]).map((key) => ({
    key,
    label: COUNTER_LABELS[key],
    value: toNumber(detailRecord[key]) ?? 0,
  }));

  const items = Array.isArray(detailRecord.items)
    ? detailRecord.items.map((item) => {
        const row = isRecord(item) ? item : {};
        return {
          digestId: typeof row.digest_id === "string" ? row.digest_id : null,
          stockCode: typeof row.stock_code === "string" ? row.stock_code : null,
          reviewLabel: typeof row.review_label === "string" ? row.review_label : null,
          impactAssessment:
            typeof row.impact_assessment === "string" ? row.impact_assessment : null,
          summary: typeof row.summary === "string" ? row.summary : null,
          missingSources: toStringArray(row.missing_sources),
        };
      })
    : [];

  const days = Array.isArray(detailRecord.days)
    ? detailRecord.days.map((item) => {
        const row = isRecord(item) ? item : {};
        return {
          reviewDate: typeof row.review_date === "string" ? row.review_date : null,
          digestCount: toNumber(row.digest_count) ?? 0,
          usefulCount: toNumber(row.useful_count) ?? 0,
          misleadingCount: toNumber(row.misleading_count) ?? 0,
          inconclusiveCount: toNumber(row.inconclusive_count) ?? 0,
          notedCount: toNumber(row.noted_count) ?? 0,
          summary: typeof row.summary === "string" ? row.summary : null,
        };
      })
    : [];

  return {
    summary: typeof infoReview.summary === "string" ? infoReview.summary : null,
    counters,
    topMissingSources: toStringArray(detailRecord.top_missing_sources),
    items,
    days,
  };
}
