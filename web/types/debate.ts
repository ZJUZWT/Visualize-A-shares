export type DebateSignal = "bullish" | "bearish" | "neutral";
export type DebateQuality = "consensus" | "strong_disagreement" | "one_sided";
export type DebateStatus = "idle" | "debating" | "final_round" | "judging" | "completed";
export type Stance = "insist" | "partial_concede" | "concede";

export interface DebateEntry {
  role: string;
  round: number;
  stance: Stance | null;
  speak: boolean;
  argument: string;
  challenges: string[];
  confidence: number;
  retail_sentiment_score: number | null;
}

export interface JudgeVerdict {
  target: string;
  debate_id: string;
  summary: string;
  signal: DebateSignal | null;
  score: number | null;
  key_arguments: string[];
  bull_core_thesis: string;
  bear_core_thesis: string;
  retail_sentiment_note: string;
  smart_money_note: string;
  risk_warnings: string[];
  debate_quality: DebateQuality;
  termination_reason: string;
  timestamp: string;
}

export interface DebateHistoryItem {
  debate_id: string;
  target: string;
  signal: DebateSignal | null;
  debate_quality: DebateQuality | null;
  rounds_completed: number;
  termination_reason: string;
  created_at: string;
}

export interface DebateReplayRecord {
  debate_id: string;
  target: string;
  blackboard_json: string;
  judge_verdict_json: string;
  rounds_completed: number;
  termination_reason: string;
  created_at: string;
}

export interface DebateStartPayload {
  debate_id: string;
  target: string;
  max_rounds: number;
  participants: string[];
}

export interface DebateRoundStartPayload {
  round: number;
  is_final: boolean;
}

export interface DebateEndPayload {
  reason: string;
  rounds_completed: number;
}

export interface ObserverState {
  speak: boolean;
  argument: string;
  retail_sentiment_score?: number;
}

export interface RoleState {
  stance: Stance | null;
  confidence: number;
  conceded: boolean;
}

export interface DataRequestItem {
  id: string;
  requested_by: string;
  action: string;
  status: "pending" | "done" | "failed";
  result_summary?: string;
  duration_ms?: number;
}
