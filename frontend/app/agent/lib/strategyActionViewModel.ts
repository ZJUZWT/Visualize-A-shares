import type { TradePlanData } from "@/lib/parseTradePlan";

export interface StrategyExecutionState {
  id: string | null;
  decision: "adopted" | "rejected" | null;
  status: string | null;
  reason: string | null;
  updated_at: string | null;
  is_submitting: boolean;
  error: string | null;
}

export interface StrategyMemoState {
  id: string | null;
  saved: boolean;
  note: string | null;
  updated_at: string | null;
  is_submitting: boolean;
  error: string | null;
}

export interface StrategyExecutionRecord {
  id: string;
  session_id: string | null;
  message_id: string | null;
  strategy_key: string;
  decision: "adopted" | "rejected";
  status: string | null;
  reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface StrategyActionPayloadBase {
  portfolio_id: string;
  session_id: string;
  message_id: string;
  strategy_key: string;
  plan: TradePlanData;
  source_run_id?: string | null;
}

interface RejectStrategyActionPayload extends StrategyActionPayloadBase {
  reason?: string | null;
}

export function mapExecutionRecord(raw: Record<string, unknown>): StrategyExecutionRecord | null {
  const decision = raw.decision === "adopted" || raw.decision === "rejected" ? raw.decision : null;
  const strategyKey = typeof raw.strategy_key === "string" ? raw.strategy_key : null;
  if (!decision || !strategyKey) {
    return null;
  }
  return {
    id: typeof raw.id === "string" ? raw.id : strategyKey,
    session_id: typeof raw.session_id === "string" ? raw.session_id : null,
    message_id: typeof raw.message_id === "string" ? raw.message_id : null,
    strategy_key: strategyKey,
    decision,
    status: typeof raw.status === "string" ? raw.status : null,
    reason: typeof raw.reason === "string" ? raw.reason : null,
    created_at: typeof raw.created_at === "string" ? raw.created_at : null,
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : null,
  };
}

export function mergeStrategyCardState(
  executionState?: StrategyExecutionState,
  memoState?: StrategyMemoState
) {
  const executionLabel =
    executionState?.decision === "adopted"
      ? "已采纳"
      : executionState?.decision === "rejected"
        ? "已忽略"
        : null;
  const memoLabel = memoState?.saved ? "已收藏" : null;

  return {
    executionLabel,
    memoLabel,
    canAdopt: !executionState?.decision && !executionState?.is_submitting,
    canReject: !executionState?.decision && !executionState?.is_submitting,
    canSaveMemo: !memoState?.saved && !memoState?.is_submitting,
  };
}

export function buildStrategyExecutionRequestConfig(
  intent: "adopt" | "reject",
  payload: StrategyActionPayloadBase | RejectStrategyActionPayload
) {
  return {
    endpoint: intent === "adopt" ? "/api/v1/agent/adopt-strategy" : "/api/v1/agent/reject-strategy",
    method: "POST" as const,
    body: payload,
  };
}

export function buildMemoRequestConfig(
  portfolioId: string,
  payload: {
    session_id: string;
    message_id: string;
    strategy_key: string;
    plan: TradePlanData;
    note?: string | null;
  }
) {
  return {
    endpoint: "/api/v1/agent/strategy-memos",
    method: "POST" as const,
    body: {
      portfolio_id: portfolioId,
      source_agent: "agent_chat",
      source_session_id: payload.session_id,
      source_message_id: payload.message_id,
      strategy_key: payload.strategy_key,
      stock_code: payload.plan.stock_code,
      stock_name: payload.plan.stock_name,
      plan_snapshot: payload.plan,
      note: payload.note ?? null,
      status: "saved" as const,
    },
  };
}
