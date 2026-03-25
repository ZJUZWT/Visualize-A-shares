import type { AgentBacktestDay, AgentBacktestSummary } from "../types";

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

export function normalizeBacktestSummary(raw: unknown): AgentBacktestSummary | null {
  if (!isRecord(raw) || typeof raw.run_id !== "string") {
    return null;
  }
  return {
    run_id: raw.run_id,
    status: typeof raw.status === "string" ? raw.status : "unknown",
    start_date: typeof raw.start_date === "string" ? raw.start_date : null,
    end_date: typeof raw.end_date === "string" ? raw.end_date : null,
    total_return: toNumber(raw.total_return),
    max_drawdown: toNumber(raw.max_drawdown),
    trade_count: toNumber(raw.trade_count),
    win_rate: toNumber(raw.win_rate),
    review_count: toNumber(raw.review_count),
    memory_added: toNumber(raw.memory_added),
    memory_updated: toNumber(raw.memory_updated),
    memory_retired: toNumber(raw.memory_retired),
    buy_and_hold_return: toNumber(raw.buy_and_hold_return),
  };
}

export function normalizeBacktestDays(raw: unknown): AgentBacktestDay[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  const normalized: AgentBacktestDay[] = [];
  for (const item of raw) {
    const data = isRecord(item) ? item : {};
    const tradeDate = typeof data.trade_date === "string" ? data.trade_date : null;
    if (!tradeDate) {
      continue;
    }
    normalized.push({
      id: typeof data.id === "string" ? data.id : undefined,
      run_id: typeof data.run_id === "string" ? data.run_id : null,
      portfolio_id: typeof data.portfolio_id === "string" ? data.portfolio_id : null,
      trade_date: tradeDate,
      brain_run_id: typeof data.brain_run_id === "string" ? data.brain_run_id : null,
      review_created: typeof data.review_created === "boolean" ? data.review_created : null,
      memory_delta: isRecord(data.memory_delta) ? data.memory_delta : null,
      created_at: typeof data.created_at === "string" ? data.created_at : null,
    });
  }

  return normalized;
}
