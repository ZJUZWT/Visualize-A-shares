import type {
  AgentState,
  BrainRun,
  MemoryRule,
  ReflectionFeedItem,
  StrategyHistoryEntry,
} from "../types";

export interface StrategyBrainInput {
  state: AgentState | null;
  runs: BrainRun[];
  memoryRules: MemoryRule[];
  reflectionFeed: ReflectionFeedItem[];
  strategyHistory: StrategyHistoryEntry[];
  activeRun?: BrainRun | null;
}

export interface StrategyBrainViewModel {
  snapshot: {
    marketViewLabel: string;
    positionLevelLabel: string;
    sectorPreferenceCount: number;
    riskAlertCount: number;
    sectorPreferences: unknown[];
    riskAlerts: unknown[];
    activeRun: {
      id: string;
      status: string;
      runType: string;
      startedAt: string;
      completedAt: string | null;
      decisionCount: number;
      tokenCount: number;
    } | null;
  };
  beliefs: Array<{
    id: string;
    title: string;
    category: string;
    status: string;
    statusTone: "strong" | "muted";
    confidencePct: number;
    verifyCount: number;
    verifyWin: number;
    sourceRunId: string | null;
    createdAt: string | null;
    retiredAt: string | null;
  }>;
  timeline: Array<{
    id: string;
    title: string;
    occurredAt: string | null;
    decisionCount: number;
    candidateCount: number;
    tradeCount: number;
    deltaSummary: string[];
    decisions: Array<{
      action: string;
      stockCode: string;
      stockName: string;
      confidencePct: number | null;
      reasoning: string | null;
    }>;
    thinkingSummary: string | null;
  }>;
  evolution: {
    reflectionCards: Array<{
      id: string;
      title: string;
      summary: string;
      metrics: Record<string, number | string | null>;
    }>;
    strategyNodes: Array<{
      id: string;
      runId: string | null;
      occurredAt: string | null;
      marketViewLabel: string;
      positionLevel: string;
      riskAlertCount: number;
      sectorPreferenceCount: number;
      executionCounters: Record<string, number | string | null>;
    }>;
  };
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "未设置";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function extractMarketViewLabel(value: unknown): string {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    const preferred = record.regime ?? record.view ?? record.bias ?? record.label;
    if (typeof preferred === "string" && preferred.trim()) {
      return preferred;
    }
  }
  return renderValue(value);
}

function summarizeStateDelta(before: Record<string, unknown> | null, after: Record<string, unknown> | null) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  const labelMap: Record<string, string> = {
    position_level: "仓位",
    market_view: "市场观点",
  };
  return keys
    .filter((key) => renderValue(before?.[key]) !== renderValue(after?.[key]))
    .map((key) => `${labelMap[key] ?? key}: ${renderValue(before?.[key])} -> ${renderValue(after?.[key])}`);
}

function buildSnapshot(state: AgentState | null, activeRun: BrainRun | null) {
  return {
    marketViewLabel: state?.market_view ? extractMarketViewLabel(state.market_view) : "未设置",
    positionLevelLabel: state?.position_level || "未设置",
    sectorPreferenceCount: state?.sector_preferences?.length ?? 0,
    riskAlertCount: state?.risk_alerts?.length ?? 0,
    sectorPreferences: state?.sector_preferences ?? [],
    riskAlerts: state?.risk_alerts ?? [],
    activeRun: activeRun
      ? {
          id: activeRun.id,
          status: activeRun.status,
          runType: activeRun.run_type,
          startedAt: activeRun.started_at,
          completedAt: activeRun.completed_at,
          decisionCount:
            activeRun.decisions?.length
            ?? Number(activeRun.execution_summary?.decision_count ?? 0),
          tokenCount: activeRun.llm_tokens_used,
        }
      : null,
  };
}

function buildBeliefs(memoryRules: MemoryRule[]) {
  return [...memoryRules]
    .sort((a, b) => {
      const aRank = a.status === "active" ? 0 : 1;
      const bRank = b.status === "active" ? 0 : 1;
      if (aRank !== bRank) {
        return aRank - bRank;
      }
      return (b.confidence ?? 0) - (a.confidence ?? 0);
    })
    .map((rule) => ({
      id: rule.id,
      title: rule.rule_text,
      category: rule.category || "uncategorized",
      status: rule.status || "unknown",
      statusTone: (rule.status === "active" ? "strong" : "muted") as "strong" | "muted",
      confidencePct: Math.round((rule.confidence ?? 0) * 100),
      verifyCount: rule.verify_count ?? 0,
      verifyWin: rule.verify_win ?? 0,
      sourceRunId: rule.source_run_id ?? null,
      createdAt: rule.created_at ?? null,
      retiredAt: rule.retired_at ?? null,
    }));
}

function buildTimeline(runs: BrainRun[]) {
  return runs.map((run) => ({
    id: run.id,
    title: `${run.run_type} · ${run.status}`,
    occurredAt: run.completed_at ?? run.started_at,
    decisionCount: run.decisions?.length ?? Number(run.execution_summary?.decision_count ?? 0),
    candidateCount: run.candidates?.length ?? Number(run.execution_summary?.candidate_count ?? 0),
    tradeCount: Number(run.execution_summary?.trade_count ?? 0),
    deltaSummary: summarizeStateDelta(run.state_before, run.state_after),
    decisions: (run.decisions ?? []).map((decision) => ({
      action: decision.action,
      stockCode: decision.stock_code,
      stockName: decision.stock_name,
      confidencePct: decision.confidence === null || decision.confidence === undefined
        ? null
        : Math.round(decision.confidence * 100),
      reasoning: decision.reasoning ?? null,
    })),
    thinkingSummary:
      typeof run.thinking_process === "string"
        ? run.thinking_process
        : run.thinking_process
          ? JSON.stringify(run.thinking_process)
          : null,
  }));
}

function buildEvolution(reflectionFeed: ReflectionFeedItem[], strategyHistory: StrategyHistoryEntry[]) {
  return {
    reflectionCards: reflectionFeed.map((item) => ({
      id: item.id,
      title: `${item.kind || "unknown"} · ${item.date || "--"}`,
      summary: item.summary || "未提供摘要",
      metrics: item.metrics,
    })),
    strategyNodes: strategyHistory.map((item) => ({
      id: item.id,
      runId: item.run_id,
      occurredAt: item.occurred_at,
      marketViewLabel: item.market_view ? extractMarketViewLabel(item.market_view) : "未设置",
      positionLevel: item.position_level || "未设置",
      riskAlertCount: item.risk_alerts?.length ?? 0,
      sectorPreferenceCount: item.sector_preferences?.length ?? 0,
      executionCounters: item.execution_counters,
    })),
  };
}

export function buildStrategyBrainViewModel(input: StrategyBrainInput): StrategyBrainViewModel {
  const activeRun = input.activeRun ?? input.runs[0] ?? null;
  return {
    snapshot: buildSnapshot(input.state, activeRun),
    beliefs: buildBeliefs(input.memoryRules),
    timeline: buildTimeline(input.runs),
    evolution: buildEvolution(input.reflectionFeed, input.strategyHistory),
  };
}
