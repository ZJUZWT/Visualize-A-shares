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
  error_message: string | null;
  llm_tokens_used: number;
  started_at: string;
  completed_at: string | null;
}

export interface WatchlistItem {
  id: string;
  stock_code: string;
  stock_name: string;
  reason: string | null;
  added_by: string;
  created_at: string;
}
