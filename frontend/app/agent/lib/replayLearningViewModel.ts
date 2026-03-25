import type { AgentReplayLearning } from "../types";

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

function toStringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => toStringOrNull(item))
    .filter((item): item is string => Boolean(item));
}

export function normalizeReplayLearning(
  portfolioId: string,
  raw: unknown
): AgentReplayLearning | null {
  const data = isRecord(raw) ? raw : null;
  if (!data) {
    return null;
  }

  const whatAiKnew = isRecord(data.what_ai_knew) ? data.what_ai_knew : {};
  const whatHappened = isRecord(data.what_happened) ? data.what_happened : {};
  const counterfactual = isRecord(data.counterfactual) ? data.counterfactual : {};

  return {
    portfolio_id: toStringOrNull(data.portfolio_id) ?? portfolioId,
    date: toStringOrNull(data.date),
    what_ai_knew: {
      trade_theses: toStringList(whatAiKnew.trade_theses),
      plan_reasoning: toStringList(whatAiKnew.plan_reasoning),
      trade_reasons: toStringList(whatAiKnew.trade_reasons),
      run_ids: toStringList(whatAiKnew.run_ids),
    },
    what_happened: {
      review_statuses: toStringList(whatHappened.review_statuses),
      next_day_move_pct: toNumber(whatHappened.next_day_move_pct),
      total_asset_mark_to_market_close: toNumber(whatHappened.total_asset_mark_to_market_close),
      total_asset_realized_only_close: toNumber(whatHappened.total_asset_realized_only_close),
    },
    counterfactual: {
      would_change: counterfactual.would_change === true,
      action_bias: toStringOrNull(counterfactual.action_bias),
      rationale: toStringOrNull(counterfactual.rationale),
    },
    lesson_summary: toStringOrNull(data.lesson_summary),
  };
}

export function summarizeReplayLearning(learning: AgentReplayLearning | null): {
  headline: string;
  badgeTone: "steady" | "warn";
} {
  if (!learning) {
    return {
      headline: "还没有 replay learning 结果",
      badgeTone: "steady",
    };
  }

  if (learning.counterfactual.would_change) {
    return {
      headline: learning.lesson_summary || "这次如果重来，Agent 会调整动作。",
      badgeTone: "warn",
    };
  }

  return {
    headline: learning.lesson_summary || "这次 replay learning 认为原动作可以保留。",
    badgeTone: "steady",
  };
}
