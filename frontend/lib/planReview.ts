function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function toBoolean(value: unknown): boolean {
  return value === true || value === "true" || value === 1 || value === "1";
}

export type PlanReviewOutcomeLabel = "useful" | "misleading" | "incomplete" | "pending";

export interface PlanReviewViewModel {
  id: string;
  planId: string;
  reviewDate: string | null;
  reviewWindow: number;
  entryHit: boolean;
  takeProfitHit: boolean;
  stopLossHit: boolean;
  invalidationHit: boolean;
  maxGainPct: number | null;
  maxDrawdownPct: number | null;
  closePrice: number | null;
  outcomeLabel: PlanReviewOutcomeLabel;
  summary: string;
  lessonSummary: string;
}

export interface TradePlanCardSavedState {
  id: string;
  status: string;
  createdAt: string;
  latestReview: PlanReviewViewModel | null;
}

export const PLAN_REVIEW_OUTCOME_LABELS: Record<PlanReviewOutcomeLabel, string> = {
  useful: "有效",
  misleading: "误导",
  incomplete: "待补充",
  pending: "待验证",
};

export function normalizePlanReview(raw: unknown): PlanReviewViewModel | null {
  if (!isRecord(raw) || typeof raw.id !== "string" || typeof raw.plan_id !== "string") {
    return null;
  }
  const outcome =
    raw.outcome_label === "useful"
    || raw.outcome_label === "misleading"
    || raw.outcome_label === "incomplete"
    || raw.outcome_label === "pending"
      ? raw.outcome_label
      : "pending";

  return {
    id: raw.id,
    planId: raw.plan_id,
    reviewDate: typeof raw.review_date === "string" ? raw.review_date : null,
    reviewWindow: Math.max(1, Math.round(toNumber(raw.review_window) ?? 5)),
    entryHit: toBoolean(raw.entry_hit),
    takeProfitHit: toBoolean(raw.take_profit_hit),
    stopLossHit: toBoolean(raw.stop_loss_hit),
    invalidationHit: toBoolean(raw.invalidation_hit),
    maxGainPct: toNumber(raw.max_gain_pct),
    maxDrawdownPct: toNumber(raw.max_drawdown_pct),
    closePrice: toNumber(raw.close_price),
    outcomeLabel: outcome,
    summary: typeof raw.summary === "string" ? raw.summary : "",
    lessonSummary: typeof raw.lesson_summary === "string" ? raw.lesson_summary : "",
  };
}

export function normalizeSavedTradePlanCard(raw: unknown): TradePlanCardSavedState | null {
  if (!isRecord(raw) || typeof raw.id !== "string" || typeof raw.status !== "string") {
    return null;
  }
  return {
    id: raw.id,
    status: raw.status,
    createdAt: typeof raw.created_at === "string" ? raw.created_at : "",
    latestReview: normalizePlanReview(raw.latest_review),
  };
}
