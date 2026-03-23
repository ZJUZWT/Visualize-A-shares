import type {
  AgentEquityTimeline,
  AgentReplaySnapshot,
  BrainRun,
  EquityTimelinePoint,
  ReflectionFeedItem,
  ReplayPlan,
  ReplayPosition,
  ReplayTrade,
  ReviewRecord,
} from "../types";

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

function normalizeTimelinePoint(raw: unknown): EquityTimelinePoint | null {
  const data = isRecord(raw) ? raw : null;
  const date = toStringOrNull(data?.date);
  if (!date) {
    return null;
  }
  return {
    date,
    equity: toNumber(data?.equity),
    cash_balance: toNumber(data?.cash_balance),
    position_value: toNumber(data?.position_value),
    position_cost_basis_open: toNumber(data?.position_cost_basis_open),
    realized_pnl: toNumber(data?.realized_pnl),
    unrealized_pnl: toNumber(data?.unrealized_pnl),
  };
}

function normalizeReplayPosition(raw: unknown): ReplayPosition | null {
  const data = isRecord(raw) ? raw : null;
  const id = toStringOrNull(data?.id);
  if (!id) {
    return null;
  }
  return {
    id,
    stock_code: toStringOrNull(data?.stock_code),
    stock_name: toStringOrNull(data?.stock_name),
    holding_type: toStringOrNull(data?.holding_type),
    current_qty: toNumber(data?.current_qty),
    avg_entry_price: toNumber(data?.avg_entry_price),
    cost_basis: toNumber(data?.cost_basis),
    close_price: toNumber(data?.close_price),
    market_value: toNumber(data?.market_value),
    unrealized_pnl: toNumber(data?.unrealized_pnl),
  };
}

function normalizeReplayTrade(raw: unknown): ReplayTrade | null {
  const data = isRecord(raw) ? raw : null;
  const id = toStringOrNull(data?.id);
  if (!id) {
    return null;
  }
  return {
    id,
    stock_code: toStringOrNull(data?.stock_code),
    stock_name: toStringOrNull(data?.stock_name),
    action: toStringOrNull(data?.action),
    price: toNumber(data?.price),
    quantity: toNumber(data?.quantity),
    amount: toNumber(data?.amount),
    reason: toStringOrNull(data?.reason),
    thesis: toStringOrNull(data?.thesis),
    created_at: toStringOrNull(data?.created_at),
  };
}

function normalizeReplayPlan(raw: unknown): ReplayPlan | null {
  const data = isRecord(raw) ? raw : null;
  const id = toStringOrNull(data?.id);
  if (!id) {
    return null;
  }
  return {
    id,
    stock_code: toStringOrNull(data?.stock_code),
    stock_name: toStringOrNull(data?.stock_name),
    direction: toStringOrNull(data?.direction),
    status: toStringOrNull(data?.status),
    reasoning: toStringOrNull(data?.reasoning),
    entry_price: toNumber(data?.entry_price),
    current_price: toNumber(data?.current_price),
    position_pct: toNumber(data?.position_pct),
    created_at: toStringOrNull(data?.created_at),
    updated_at: toStringOrNull(data?.updated_at),
  };
}

function normalizeReviewRecord(raw: unknown): ReviewRecord | null {
  const data = isRecord(raw) ? raw : null;
  const id = toStringOrNull(data?.id);
  if (!id) {
    return null;
  }
  return {
    id,
    brain_run_id: toStringOrNull(data?.brain_run_id),
    trade_id: toStringOrNull(data?.trade_id),
    stock_code: toStringOrNull(data?.stock_code),
    stock_name: toStringOrNull(data?.stock_name),
    action: toStringOrNull(data?.action),
    decision_price: toNumber(data?.decision_price),
    review_price: toNumber(data?.review_price),
    pnl_pct: toNumber(data?.pnl_pct),
    holding_days: toNumber(data?.holding_days),
    status: toStringOrNull(data?.status),
    review_date: toStringOrNull(data?.review_date),
    review_type: toStringOrNull(data?.review_type),
    created_at: toStringOrNull(data?.created_at),
  };
}

function normalizeReflectionItem(raw: unknown): ReflectionFeedItem | null {
  const data = isRecord(raw) ? raw : null;
  const id = toStringOrNull(data?.id);
  if (!id) {
    return null;
  }
  return {
    id,
    kind: toStringOrNull(data?.kind),
    date: toStringOrNull(data?.date),
    summary: toStringOrNull(data?.summary),
    metrics: isRecord(data?.metrics) ? (data?.metrics as Record<string, number | string | null>) : {},
    details: isRecord(data?.details)
      ? (data.details as ReflectionFeedItem["details"])
      : null,
  };
}

function normalizeBrainRun(raw: unknown): BrainRun | null {
  const data = isRecord(raw) ? raw : null;
  const id = toStringOrNull(data?.id);
  if (!id) {
    return null;
  }
  return {
    id,
    portfolio_id: toStringOrNull(data?.portfolio_id) ?? "",
    run_type: toStringOrNull(data?.run_type) ?? "",
    status: toStringOrNull(data?.status) ?? "",
    candidates: Array.isArray(data?.candidates) ? (data?.candidates as BrainRun["candidates"]) : null,
    analysis_results: Array.isArray(data?.analysis_results) ? (data?.analysis_results as BrainRun["analysis_results"]) : null,
    decisions: Array.isArray(data?.decisions) ? (data?.decisions as BrainRun["decisions"]) : null,
    plan_ids: Array.isArray(data?.plan_ids) ? (data?.plan_ids as string[]) : null,
    trade_ids: Array.isArray(data?.trade_ids) ? (data?.trade_ids as string[]) : null,
    thinking_process: data?.thinking_process ?? null,
    state_before: isRecord(data?.state_before) ? (data?.state_before as Record<string, unknown>) : null,
    state_after: isRecord(data?.state_after) ? (data?.state_after as Record<string, unknown>) : null,
    execution_summary: isRecord(data?.execution_summary) ? (data?.execution_summary as Record<string, unknown>) : null,
    error_message: toStringOrNull(data?.error_message),
    llm_tokens_used: toNumber(data?.llm_tokens_used) ?? 0,
    started_at: toStringOrNull(data?.started_at) ?? "",
    completed_at: toStringOrNull(data?.completed_at),
  };
}

export function normalizeEquityTimeline(
  portfolioId: string,
  raw: unknown
): AgentEquityTimeline {
  const data = isRecord(raw) ? raw : {};
  const markToMarket = Array.isArray(data.mark_to_market)
    ? data.mark_to_market.map(normalizeTimelinePoint).filter(Boolean) as EquityTimelinePoint[]
    : [];
  const realizedOnly = Array.isArray(data.realized_only)
    ? data.realized_only.map(normalizeTimelinePoint).filter(Boolean) as EquityTimelinePoint[]
    : [];

  return {
    portfolio_id: toStringOrNull(data.portfolio_id) ?? portfolioId,
    start_date: toStringOrNull(data.start_date),
    end_date: toStringOrNull(data.end_date),
    mark_to_market: markToMarket,
    realized_only: realizedOnly,
  };
}

export function normalizeReplaySnapshot(
  portfolioId: string,
  raw: unknown
): AgentReplaySnapshot {
  const data = isRecord(raw) ? raw : {};
  const account = isRecord(data.account) ? data.account : {};

  return {
    portfolio_id: toStringOrNull(data.portfolio_id) ?? portfolioId,
    date: toStringOrNull(data.date),
    account: {
      cash_balance: toNumber(account.cash_balance),
      position_value_mark_to_market: toNumber(account.position_value_mark_to_market),
      position_cost_basis_open: toNumber(account.position_cost_basis_open),
      total_asset_mark_to_market: toNumber(account.total_asset_mark_to_market),
      total_asset_realized_only: toNumber(account.total_asset_realized_only),
      realized_pnl: toNumber(account.realized_pnl),
      unrealized_pnl: toNumber(account.unrealized_pnl),
    },
    positions: Array.isArray(data.positions)
      ? data.positions.map(normalizeReplayPosition).filter(Boolean) as ReplayPosition[]
      : [],
    trades: Array.isArray(data.trades)
      ? data.trades.map(normalizeReplayTrade).filter(Boolean) as ReplayTrade[]
      : [],
    plans: Array.isArray(data.plans)
      ? data.plans.map(normalizeReplayPlan).filter(Boolean) as ReplayPlan[]
      : [],
    brain_runs: Array.isArray(data.brain_runs)
      ? data.brain_runs.map(normalizeBrainRun).filter(Boolean) as BrainRun[]
      : [],
    reviews: Array.isArray(data.reviews)
      ? data.reviews.map(normalizeReviewRecord).filter(Boolean) as ReviewRecord[]
      : [],
    reflections: Array.isArray(data.reflections)
      ? data.reflections.map(normalizeReflectionItem).filter(Boolean) as ReflectionFeedItem[]
      : [],
    what_ai_knew: {
      run_ids: Array.isArray(data.what_ai_knew) ? [] : Array.isArray((data.what_ai_knew as Record<string, unknown> | undefined)?.run_ids)
        ? ((data.what_ai_knew as Record<string, unknown>).run_ids as unknown[]).map((item) => toStringOrNull(item)).filter(Boolean) as string[]
        : [],
      trade_theses: Array.isArray((data.what_ai_knew as Record<string, unknown> | undefined)?.trade_theses)
        ? ((data.what_ai_knew as Record<string, unknown>).trade_theses as unknown[]).map((item) => toStringOrNull(item)).filter(Boolean) as string[]
        : [],
      plan_reasoning: Array.isArray((data.what_ai_knew as Record<string, unknown> | undefined)?.plan_reasoning)
        ? ((data.what_ai_knew as Record<string, unknown>).plan_reasoning as unknown[]).map((item) => toStringOrNull(item)).filter(Boolean) as string[]
        : [],
      trade_reasons: Array.isArray((data.what_ai_knew as Record<string, unknown> | undefined)?.trade_reasons)
        ? ((data.what_ai_knew as Record<string, unknown>).trade_reasons as unknown[]).map((item) => toStringOrNull(item)).filter(Boolean) as string[]
        : [],
    },
    what_happened: {
      review_statuses: Array.isArray((data.what_happened as Record<string, unknown> | undefined)?.review_statuses)
        ? ((data.what_happened as Record<string, unknown>).review_statuses as unknown[]).map((item) => toStringOrNull(item)).filter(Boolean) as string[]
        : [],
      next_day_move_pct: toNumber((data.what_happened as Record<string, unknown> | undefined)?.next_day_move_pct),
      total_asset_mark_to_market_close: toNumber((data.what_happened as Record<string, unknown> | undefined)?.total_asset_mark_to_market_close),
      total_asset_realized_only_close: toNumber((data.what_happened as Record<string, unknown> | undefined)?.total_asset_realized_only_close),
    },
  };
}

export function pickDefaultReplayDate(
  timeline: AgentEquityTimeline | null,
  today: string
): string {
  const lastTimelineDate = timeline?.mark_to_market[timeline.mark_to_market.length - 1]?.date
    ?? timeline?.realized_only[timeline.realized_only.length - 1]?.date
    ?? timeline?.end_date;
  return lastTimelineDate ?? today;
}

export function clampReplayDate(
  value: string,
  minDate: string | null,
  maxDate: string | null
): string {
  if (minDate && value < minDate) {
    return minDate;
  }
  if (maxDate && value > maxDate) {
    return maxDate;
  }
  return value;
}

export function summarizeEquityTimeline(timeline: AgentEquityTimeline | null): {
  latest_mark_to_market: number | null;
  latest_realized_only: number | null;
  unrealized_delta: number | null;
} {
  const latestMark = timeline?.mark_to_market[timeline.mark_to_market.length - 1]?.equity ?? null;
  const latestRealized = timeline?.realized_only[timeline.realized_only.length - 1]?.equity ?? null;
  return {
    latest_mark_to_market: latestMark,
    latest_realized_only: latestRealized,
    unrealized_delta:
      latestMark !== null && latestRealized !== null
        ? latestMark - latestRealized
        : null,
  };
}

export function buildEquityPolylinePoints(
  points: EquityTimelinePoint[],
  width: number,
  height: number
): string {
  if (points.length === 0) {
    return "";
  }
  const values = points
    .map((point) => point.equity)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (values.length === 0) {
    return "";
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return points
    .map((point, index) => {
      const value = point.equity ?? min;
      const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");
}
