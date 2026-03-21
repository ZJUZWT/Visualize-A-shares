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

export interface WatchlistItem {
  id: string;
  stock_code: string;
  stock_name: string;
  reason: string | null;
  added_by: string;
  created_at: string;
}
