import type { TradePlanData } from "@/lib/parseTradePlan";

export interface AgentState {
  portfolio_id: string;
  market_view: Record<string, unknown> | null;
  position_level: string | null;
  sector_preferences: unknown[] | null;
  risk_alerts: unknown[] | null;
  source_run_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentCandidate {
  stock_code: string;
  stock_name: string;
  source: string;
}

export interface AgentAnalysisResult {
  stock_code: string;
  stock_name: string;
  error?: string | null;
  daily?: unknown;
}

export interface AgentDecision {
  action: string;
  stock_code: string;
  stock_name: string;
  confidence?: number | null;
  price?: number | string | null;
  quantity?: number | string | null;
  take_profit?: number | string | null;
  stop_loss?: number | string | null;
  reasoning?: string | null;
}

export interface BrainRun {
  id: string;
  portfolio_id: string;
  run_type: string;
  status: string;
  candidates: AgentCandidate[] | null;
  analysis_results: AgentAnalysisResult[] | null;
  decisions: AgentDecision[] | null;
  plan_ids: string[] | null;
  trade_ids: string[] | null;
  thinking_process: Record<string, unknown> | unknown[] | string | null;
  state_before: Record<string, unknown> | null;
  state_after: Record<string, unknown> | null;
  execution_summary: Record<string, unknown> | null;
  error_message: string | null;
  llm_tokens_used: number;
  started_at: string;
  completed_at: string | null;
}

export interface LedgerPosition {
  id: string;
  stock_code: string;
  stock_name: string;
  holding_type?: string | null;
  entry_price?: number | null;
  current_qty?: number | null;
  cost_basis?: number | null;
  status?: string | null;
  entry_date?: string | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  position_pct?: number | null;
  status_signal?: "healthy" | "warning" | "danger" | null;
  status_reason?: string | null;
  latest_strategy?: {
    id: string;
    holding_type?: string | null;
    take_profit?: number | null;
    stop_loss?: number | null;
    reasoning?: string | null;
    details?: Record<string, unknown> | null;
    version?: number | null;
    source_run_id?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
  } | null;
}

export interface LedgerTrade {
  id: string;
  stock_code: string;
  stock_name: string;
  action: string;
  price?: number | null;
  quantity?: number | null;
  amount?: number | null;
  created_at?: string | null;
  source_run_id?: string | null;
  source_plan_id?: string | null;
}

export interface LedgerPlan {
  id: string;
  stock_code: string;
  stock_name: string;
  direction: string;
  status: string;
  entry_price?: number | null;
  take_profit?: number | null;
  stop_loss?: number | null;
  updated_at?: string | null;
  source_run_id?: string | null;
}

export interface LedgerAccountOverview {
  cash_balance: number | null;
  total_asset: number | null;
  total_pnl: number | null;
  total_pnl_pct: number | null;
  position_count: number;
  pending_plan_count: number;
  trade_count: number;
}

export interface LedgerOverview {
  portfolio_id: string;
  account: LedgerAccountOverview;
  positions: LedgerPosition[];
  pending_plans: LedgerPlan[];
  recent_trades: LedgerTrade[];
}

export interface EquityTimelinePoint {
  date: string;
  equity: number | null;
  cash_balance: number | null;
  position_value?: number | null;
  position_cost_basis_open?: number | null;
  realized_pnl: number | null;
  unrealized_pnl?: number | null;
}

export interface AgentEquityTimeline {
  portfolio_id: string;
  start_date: string | null;
  end_date: string | null;
  mark_to_market: EquityTimelinePoint[];
  realized_only: EquityTimelinePoint[];
}

export interface ReplayAccountSummary {
  cash_balance: number | null;
  position_value_mark_to_market: number | null;
  position_cost_basis_open: number | null;
  total_asset_mark_to_market: number | null;
  total_asset_realized_only: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
}

export interface ReplayPosition {
  id: string;
  stock_code: string | null;
  stock_name: string | null;
  holding_type: string | null;
  current_qty: number | null;
  avg_entry_price: number | null;
  cost_basis: number | null;
  close_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
}

export interface ReplayTrade {
  id: string;
  stock_code: string | null;
  stock_name: string | null;
  action: string | null;
  price: number | null;
  quantity: number | null;
  amount: number | null;
  reason: string | null;
  thesis: string | null;
  created_at: string | null;
}

export interface ReplayPlan {
  id: string;
  stock_code: string | null;
  stock_name: string | null;
  direction: string | null;
  status: string | null;
  reasoning: string | null;
  entry_price: number | null;
  current_price: number | null;
  position_pct: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentReplaySnapshot {
  portfolio_id: string;
  date: string | null;
  account: ReplayAccountSummary;
  positions: ReplayPosition[];
  trades: ReplayTrade[];
  plans: ReplayPlan[];
  brain_runs: BrainRun[];
  reviews: ReviewRecord[];
  reflections: ReflectionFeedItem[];
  what_ai_knew: {
    run_ids: string[];
    trade_theses: string[];
    plan_reasoning: string[];
    trade_reasons: string[];
  };
  what_happened: {
    review_statuses: string[];
    next_day_move_pct: number | null;
    total_asset_mark_to_market_close: number | null;
    total_asset_realized_only_close: number | null;
  };
}

export interface ReviewRecord {
  id: string;
  brain_run_id?: string | null;
  trade_id?: string | null;
  stock_code: string | null;
  stock_name: string | null;
  action: string | null;
  decision_price?: number | null;
  review_price?: number | null;
  pnl_pct?: number | null;
  holding_days?: number | null;
  status: string | null;
  review_date: string | null;
  review_type: string | null;
  created_at?: string | null;
}

export interface ReviewStats {
  total_win_rate: number | null;
  total_pnl_pct: number | null;
  weekly_win_rate: number | null;
  weekly_pnl_pct: number | null;
  total_reviews: number | null;
}

export interface WeeklySummary {
  id: string;
  week_start: string | null;
  week_end: string | null;
  total_trades?: number | null;
  win_count?: number | null;
  loss_count?: number | null;
  win_rate?: number | null;
  total_pnl_pct?: number | null;
  insights?: string | null;
  created_at?: string | null;
}

export interface MemoryRule {
  id: string;
  rule_text: string;
  category: string | null;
  source_run_id?: string | null;
  status: string | null;
  confidence?: number | null;
  verify_count?: number | null;
  verify_win?: number | null;
  created_at?: string | null;
  retired_at?: string | null;
}

export interface ReflectionFeedItem {
  id: string;
  kind: string | null;
  date: string | null;
  summary: string | null;
  metrics: Record<string, number | string | null>;
  details: (Record<string, unknown> & {
    info_review?: {
      summary: string | null;
      details: Record<string, unknown> | null;
    } | null;
  }) | null;
}

export interface StrategyHistoryEntry {
  id: string;
  run_id: string | null;
  occurred_at: string | null;
  market_view: Record<string, unknown> | null;
  position_level: string | null;
  sector_preferences: unknown[] | null;
  risk_alerts: unknown[] | null;
  execution_counters: Record<string, number | string | null>;
}

export type WatchSignalStatus =
  | "watching"
  | "analyzing"
  | "triggered"
  | "failed"
  | "expired"
  | "cancelled";

export interface WatchSignalEvidenceItem {
  title: string | null;
  type: string | null;
  summary: string | null;
}

export interface WatchSignal {
  id: string;
  portfolio_id: string | null;
  stock_code: string | null;
  sector: string | null;
  signal_description: string;
  check_engine: string | null;
  keywords: string[];
  if_triggered: string | null;
  cycle_context: string | null;
  status: WatchSignalStatus | null;
  trigger_evidence: WatchSignalEvidenceItem[];
  source_run_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  triggered_at: string | null;
}

export interface InfoDigest {
  id: string;
  portfolio_id: string | null;
  run_id: string | null;
  stock_code: string | null;
  digest_type: string | null;
  summary: string | null;
  key_evidence: string[];
  risk_flags: string[];
  strategy_relevance: string | null;
  impact_assessment: string | null;
  missing_sources: string[];
  structured_summary: Record<string, unknown> | null;
  raw_summary: Record<string, unknown> | null;
  created_at: string | null;
}

export interface WakeSummary {
  total: number;
  watching: number;
  triggered: number;
  inactive: number;
}

export interface WatchSignalFormState {
  stock_code: string;
  sector: string;
  signal_description: string;
  keywords: string;
  if_triggered: string;
  cycle_context: string;
}

export interface CreateWatchSignalPayload {
  portfolio_id: string;
  stock_code: string;
  sector?: string;
  signal_description: string;
  check_engine: "info";
  keywords: string[];
  if_triggered?: string;
  cycle_context?: string;
  status: "watching";
}

export interface WatchlistItem {
  id: string;
  stock_code: string;
  stock_name: string;
  reason: string | null;
  added_by: string;
  created_at: string;
}

export interface AgentChatSession {
  id: string;
  portfolio_id: string | null;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  message_count: number | null;
}

export interface AgentChatEntry {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  session_id?: string | null;
  is_streaming?: boolean;
  is_persisted?: boolean;
}

export type AgentLeftPanelTab = "console" | "memo_inbox";

export type AgentStrategyExecutionDecision = "adopted" | "rejected";
export type AgentStrategyExecutionIntent = "adopt" | "reject";

export interface AgentStrategyExecutionRecord {
  id: string;
  session_id: string | null;
  message_id: string | null;
  strategy_key: string;
  decision: AgentStrategyExecutionDecision;
  status: string | null;
  reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentStrategyExecutionState {
  id: string | null;
  decision: AgentStrategyExecutionDecision | null;
  status: string | null;
  reason: string | null;
  updated_at: string | null;
  is_submitting: boolean;
  error: string | null;
}

export type AgentStrategyExecutionLookup = Record<string, AgentStrategyExecutionState>;

export interface AgentStrategyExecutionRequest {
  intent: AgentStrategyExecutionIntent;
  session_id: string;
  message_id: string;
  strategy_key: string;
  plan: TradePlanData;
  reason?: string | null;
  source_run_id?: string | null;
}

export interface AgentStrategyMemoState {
  id: string | null;
  saved: boolean;
  note: string | null;
  updated_at: string | null;
  is_submitting: boolean;
  error: string | null;
}

export type AgentStrategyMemoLookup = Record<string, AgentStrategyMemoState>;

export interface AgentStrategyMemoSaveRequest {
  session_id: string;
  message_id: string;
  strategy_key: string;
  plan: TradePlanData;
  note?: string | null;
}

export interface StrategyMemoEntry {
  id: string;
  portfolio_id: string | null;
  source_agent: string | null;
  source_session_id: string | null;
  source_message_id: string | null;
  session_id: string | null;
  message_id: string | null;
  strategy_key: string;
  stock_code: string;
  stock_name: string | null;
  plan_snapshot: TradePlanData | null;
  note: string | null;
  status: "saved" | "ignored" | "archived" | null;
  created_at: string | null;
  updated_at: string | null;
}

export type WakeDigestMode = "selected_run" | "recent";

export type AgentConsoleTab = "runs" | "wake" | "reviews" | "memory" | "reflection";

export function buildAgentStrategyKey(plan: TradePlanData): string {
  const numericPart = (value: number | null) => (value === null ? "" : value.toFixed(4));

  return [
    plan.stock_code.trim().toUpperCase(),
    plan.direction,
    numericPart(plan.entry_price),
    numericPart(plan.take_profit),
    numericPart(plan.stop_loss),
    (plan.valid_until || "").trim(),
  ].join("|");
}

export function buildAgentStrategyActionLookupKey(
  messageId: string | null,
  strategyKey: string
): string {
  return `${messageId || "__pending__"}::${strategyKey}`;
}
