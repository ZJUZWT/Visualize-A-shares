"use client";

import { useCallback, useEffect, useState } from "react";
import type { TradePlanData } from "@/lib/parseTradePlan";
import NavSidebar from "@/components/ui/NavSidebar";
import AgentChatPanel from "./components/AgentChatPanel";
import AgentStatePanel from "./components/AgentStatePanel";
import DecisionRunPanel from "./components/DecisionRunPanel";
import ExecutionLedgerPanel from "./components/ExecutionLedgerPanel";
import ReviewRecordsPanel from "./components/ReviewRecordsPanel";
import MemoryRulesPanel from "./components/MemoryRulesPanel";
import ReflectionFeedPanel from "./components/ReflectionFeedPanel";
import StrategyHistoryPanel from "./components/StrategyHistoryPanel";
import {
  AgentChatEntry,
  AgentChatSession,
  AgentConsoleTab,
  AgentState,
  AgentStrategyActionRecord,
  AgentStrategyActionRequest,
  AgentStrategyActionState,
  BrainRun,
  LedgerOverview,
  MemoryRule,
  ReflectionFeedItem,
  ReviewRecord,
  ReviewStats,
  StrategyHistoryEntry,
  WatchlistItem,
  WeeklySummary,
  buildAgentStrategyActionLookupKey,
  buildAgentStrategyKey,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let chatEntryCounter = 0;

function nextChatEntryId() {
  chatEntryCounter += 1;
  return `agent-chat-${Date.now()}-${chatEntryCounter}`;
}

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

function normalizePercent(value: unknown): number | null {
  const numeric = toNumber(value);
  if (numeric === null) {
    return null;
  }
  return Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
}

async function fetchJson<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText}`);
  }
  return resp.json() as Promise<T>;
}

async function fetchFirstAvailable<T>(urls: string[]): Promise<T> {
  let lastError: Error | null = null;
  for (const url of urls) {
    try {
      return await fetchJson<T>(url);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }
  throw lastError ?? new Error("No available endpoint");
}

async function readErrorMessage(resp: Response, fallback: string): Promise<string> {
  const text = await resp.text().catch(() => "");
  if (!text) {
    return fallback;
  }
  try {
    const parsed = JSON.parse(text) as { detail?: string; message?: string; error?: string };
    return parsed.detail || parsed.message || parsed.error || fallback;
  } catch {
    return text;
  }
}

function normalizeAgentState(portfolioId: string, raw: unknown): AgentState {
  const data = isRecord(raw) ? raw : {};
  return {
    portfolio_id: typeof data.portfolio_id === "string" ? data.portfolio_id : portfolioId,
    market_view: isRecord(data.market_view) ? data.market_view : null,
    position_level: typeof data.position_level === "string" ? data.position_level : null,
    sector_preferences: Array.isArray(data.sector_preferences) ? data.sector_preferences : null,
    risk_alerts: Array.isArray(data.risk_alerts) ? data.risk_alerts : null,
    source_run_id: typeof data.source_run_id === "string" ? data.source_run_id : null,
    created_at: typeof data.created_at === "string" ? data.created_at : null,
    updated_at: typeof data.updated_at === "string" ? data.updated_at : null,
  };
}

function normalizeLedgerOverview(portfolioId: string, raw: unknown): LedgerOverview {
  const data = isRecord(raw) ? raw : {};
  const assetSummary = isRecord(data.asset_summary) ? data.asset_summary : null;
  const activePlans = isRecord(data.active_plans) ? data.active_plans : null;
  const accountSource = isRecord(data.account)
    ? data.account
    : assetSummary
      ? assetSummary
      : isRecord(data.summary)
        ? data.summary
        : data;
  const positions = Array.isArray(data.positions)
    ? data.positions
    : Array.isArray(data.open_positions)
      ? data.open_positions
      : [];
  const pendingPlans = Array.isArray(data.pending_plans)
    ? data.pending_plans
    : Array.isArray(data.plans)
      ? data.plans
      : activePlans
        ? [
            ...(Array.isArray(activePlans.pending) ? activePlans.pending : []),
            ...(Array.isArray(activePlans.executing) ? activePlans.executing : []),
          ]
        : [];
  const recentTrades = Array.isArray(data.recent_trades)
    ? data.recent_trades
    : Array.isArray(data.trades)
      ? data.trades
      : [];

  return {
    portfolio_id: typeof data.portfolio_id === "string" ? data.portfolio_id : portfolioId,
    account: {
      cash_balance: toNumber(accountSource.cash_balance),
      total_asset: toNumber(accountSource.total_asset),
      total_pnl: toNumber(accountSource.total_pnl),
      total_pnl_pct: toNumber(accountSource.total_pnl_pct),
      position_count:
        toNumber(accountSource.position_count)
        ?? toNumber(accountSource.open_position_count)
        ?? positions.length,
      pending_plan_count: toNumber(accountSource.pending_plan_count) ?? pendingPlans.length,
      trade_count:
        toNumber(accountSource.trade_count)
        ?? toNumber(accountSource.recent_trade_count)
        ?? recentTrades.length,
    },
    positions: positions as LedgerOverview["positions"],
    pending_plans: pendingPlans as LedgerOverview["pending_plans"],
    recent_trades: recentTrades as LedgerOverview["recent_trades"],
  };
}

function buildLedgerFallback(
  portfolioId: string,
  portfolio: unknown,
  plans: unknown,
  trades: unknown
): LedgerOverview {
  const portfolioData = isRecord(portfolio) ? portfolio : {};
  const config = isRecord(portfolioData.config) ? portfolioData.config : {};
  const positions = Array.isArray(portfolioData.positions) ? portfolioData.positions : [];
  const planList = Array.isArray(plans) ? plans : [];
  const tradeList = Array.isArray(trades) ? trades : [];
  const pendingPlans = planList.filter(
    (plan) => isRecord(plan) && plan.status !== "completed" && plan.status !== "expired"
  );

  return {
    portfolio_id: typeof config.id === "string" ? config.id : portfolioId,
    account: {
      cash_balance: toNumber(portfolioData.cash_balance),
      total_asset: toNumber(portfolioData.total_asset),
      total_pnl: toNumber(portfolioData.total_pnl),
      total_pnl_pct: toNumber(portfolioData.total_pnl_pct),
      position_count: positions.length,
      pending_plan_count: pendingPlans.length,
      trade_count: tradeList.length,
    },
    positions: positions as LedgerOverview["positions"],
    pending_plans: pendingPlans as LedgerOverview["pending_plans"],
    recent_trades: tradeList as LedgerOverview["recent_trades"],
  };
}

function normalizeReviewRecords(raw: unknown): ReviewRecord[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.records)
      ? raw.records
      : isRecord(raw) && Array.isArray(raw.items)
        ? raw.items
        : isRecord(raw) && Array.isArray(raw.results)
          ? raw.results
          : [];

  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    return {
      id: typeof data.id === "string" ? data.id : `review-${index}`,
      brain_run_id: typeof data.brain_run_id === "string" ? data.brain_run_id : null,
      trade_id: typeof data.trade_id === "string" ? data.trade_id : null,
      stock_code: typeof data.stock_code === "string" ? data.stock_code : null,
      stock_name: typeof data.stock_name === "string" ? data.stock_name : null,
      action: typeof data.action === "string" ? data.action : null,
      decision_price: toNumber(data.decision_price),
      review_price: toNumber(data.review_price),
      pnl_pct: normalizePercent(data.pnl_pct),
      holding_days: toNumber(data.holding_days),
      status: typeof data.status === "string" ? data.status : null,
      review_date: typeof data.review_date === "string" ? data.review_date : null,
      review_type: typeof data.review_type === "string" ? data.review_type : null,
      created_at: typeof data.created_at === "string" ? data.created_at : null,
    };
  });
}

function normalizeReviewStats(raw: unknown, records: ReviewRecord[]): ReviewStats {
  const data = isRecord(raw) ? raw : {};
  const totalReviews = records.length;
  const winCount = records.filter((record) => record.status === "win").length;
  const weeklyRecords = records.filter((record) => record.review_type === "weekly");
  const weeklyWinCount = weeklyRecords.filter((record) => record.status === "win").length;
  const average = (values: number[]) =>
    values.length === 0 ? null : values.reduce((sum, value) => sum + value, 0) / values.length;

  return {
    total_win_rate:
      normalizePercent(data.total_win_rate)
      ?? normalizePercent(data.win_rate)
      ?? (totalReviews > 0 ? (winCount / totalReviews) * 100 : null),
    total_pnl_pct:
      normalizePercent(data.total_pnl_pct)
      ?? average(
        records
          .map((record) => record.pnl_pct)
          .filter((value): value is number => value !== null && value !== undefined)
      ),
    weekly_win_rate:
      normalizePercent(data.weekly_win_rate)
      ?? (weeklyRecords.length > 0 ? (weeklyWinCount / weeklyRecords.length) * 100 : null),
    weekly_pnl_pct:
      normalizePercent(data.weekly_pnl_pct)
      ?? average(
        weeklyRecords
          .map((record) => record.pnl_pct)
          .filter((value): value is number => value !== null && value !== undefined)
      ),
    total_reviews: toNumber(data.total_reviews) ?? totalReviews,
  };
}

function normalizeWeeklySummaries(raw: unknown): WeeklySummary[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.weekly_summaries)
      ? raw.weekly_summaries
      : isRecord(raw) && Array.isArray(raw.items)
        ? raw.items
        : isRecord(raw) && Array.isArray(raw.results)
          ? raw.results
          : [];

  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    return {
      id: typeof data.id === "string" ? data.id : `weekly-${index}`,
      week_start: typeof data.week_start === "string" ? data.week_start : null,
      week_end: typeof data.week_end === "string" ? data.week_end : null,
      total_trades: toNumber(data.total_trades),
      win_count: toNumber(data.win_count),
      loss_count: toNumber(data.loss_count),
      win_rate: normalizePercent(data.win_rate),
      total_pnl_pct: normalizePercent(data.total_pnl_pct),
      insights: typeof data.insights === "string" ? data.insights : null,
      created_at: typeof data.created_at === "string" ? data.created_at : null,
    };
  });
}

function normalizeMemoryRules(raw: unknown): MemoryRule[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.rules)
      ? raw.rules
      : isRecord(raw) && Array.isArray(raw.items)
        ? raw.items
        : isRecord(raw) && Array.isArray(raw.results)
          ? raw.results
          : [];

  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    return {
      id: typeof data.id === "string" ? data.id : `rule-${index}`,
      rule_text: typeof data.rule_text === "string" ? data.rule_text : "",
      category: typeof data.category === "string" ? data.category : null,
      source_run_id: typeof data.source_run_id === "string" ? data.source_run_id : null,
      status: typeof data.status === "string" ? data.status : null,
      confidence: toNumber(data.confidence),
      verify_count: toNumber(data.verify_count),
      verify_win: toNumber(data.verify_win),
      created_at: typeof data.created_at === "string" ? data.created_at : null,
      retired_at: typeof data.retired_at === "string" ? data.retired_at : null,
    };
  });
}

function normalizeReflectionFeed(raw: unknown): ReflectionFeedItem[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.items)
      ? raw.items
      : isRecord(raw) && Array.isArray(raw.results)
        ? raw.results
        : isRecord(raw) && Array.isArray(raw.reflections)
          ? raw.reflections
          : [];

  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    const rawMetrics = isRecord(data.metrics) ? data.metrics : {};
    const metrics = Object.fromEntries(
      Object.entries(rawMetrics).map(([key, value]) => [
        key,
        typeof value === "number"
          ? value
          : toNumber(value) ?? (typeof value === "string" ? value : null),
      ])
    );

    return {
      id: typeof data.id === "string" ? data.id : `reflection-${index}`,
      kind: typeof data.kind === "string" ? data.kind : null,
      date:
        typeof data.date === "string"
          ? data.date
          : typeof data.created_at === "string"
            ? data.created_at
            : null,
      summary: typeof data.summary === "string" ? data.summary : null,
      metrics,
      details: isRecord(data.details) ? data.details : null,
    };
  });
}

function normalizeStrategyHistory(raw: unknown): StrategyHistoryEntry[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.items)
      ? raw.items
      : isRecord(raw) && Array.isArray(raw.results)
        ? raw.results
        : isRecord(raw) && Array.isArray(raw.history)
          ? raw.history
          : [];

  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    const executionSource = isRecord(data.execution_counters)
      ? data.execution_counters
      : isRecord(data.execution_summary)
        ? data.execution_summary
        : {
            candidate_count: data.candidate_count,
            analysis_count: data.analysis_count,
            decision_count: data.decision_count,
            plan_count: data.plan_count,
            trade_count: data.trade_count,
          };
    const executionCounters = Object.fromEntries(
      Object.entries(executionSource).map(([key, value]) => [
        key,
        typeof value === "number"
          ? value
          : toNumber(value) ?? (typeof value === "string" ? value : null),
      ])
    );

    return {
      id:
        typeof data.id === "string"
          ? data.id
          : typeof data.run_id === "string"
            ? data.run_id
            : `history-${index}`,
      run_id: typeof data.run_id === "string" ? data.run_id : null,
      occurred_at:
        typeof data.occurred_at === "string"
          ? data.occurred_at
          : typeof data.started_at === "string"
            ? data.started_at
            : null,
      market_view: isRecord(data.market_view) ? data.market_view : null,
      position_level: typeof data.position_level === "string" ? data.position_level : null,
      sector_preferences: Array.isArray(data.sector_preferences) ? data.sector_preferences : null,
      risk_alerts: Array.isArray(data.risk_alerts) ? data.risk_alerts : null,
      execution_counters: executionCounters,
    };
  });
}

function normalizeAgentChatSessions(portfolioId: string, raw: unknown): AgentChatSession[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.items)
      ? raw.items
      : isRecord(raw) && Array.isArray(raw.sessions)
        ? raw.sessions
        : isRecord(raw) && Array.isArray(raw.results)
          ? raw.results
          : isRecord(raw)
            ? [raw]
            : [];

  return items
    .map((item, index): AgentChatSession | null => {
      const data = isRecord(item) ? item : {};
      if (typeof data.id !== "string") {
        return null;
      }
      return {
        id: data.id,
        portfolio_id:
          typeof data.portfolio_id === "string" ? data.portfolio_id : (portfolioId as string | null),
        title: typeof data.title === "string" ? data.title : null,
        created_at: typeof data.created_at === "string" ? data.created_at : null,
        updated_at: typeof data.updated_at === "string" ? data.updated_at : null,
        message_count: toNumber(data.message_count) ?? toNumber(data.msg_count) ?? index * 0,
      };
    })
    .filter((value): value is AgentChatSession => value !== null);
}

function normalizeAgentChatMessages(sessionId: string, raw: unknown): AgentChatEntry[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.items)
      ? raw.items
      : isRecord(raw) && Array.isArray(raw.messages)
        ? raw.messages
        : isRecord(raw) && Array.isArray(raw.results)
          ? raw.results
          : [];

  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    const roleSource = typeof data.role === "string" ? data.role.toLowerCase() : "assistant";
    const role = roleSource === "user" ? "user" : "assistant";
    return {
      id: typeof data.id === "string" ? data.id : `${sessionId}-message-${index}`,
      role,
      content: typeof data.content === "string" ? data.content : "",
      created_at:
        typeof data.created_at === "string" ? data.created_at : new Date().toISOString(),
      session_id:
        typeof data.session_id === "string" ? data.session_id : sessionId,
      is_streaming: false,
      is_persisted: true,
    };
  });
}

function normalizeStrategyDecision(value: unknown): AgentStrategyActionRecord["action"] | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  if (
    [
      "adopt",
      "adopted",
      "accept",
      "accepted",
      "active",
      "executing",
      "completed",
    ].includes(normalized)
  ) {
    return "adopted";
  }
  if (["reject", "rejected", "dismiss", "dismissed", "ignored"].includes(normalized)) {
    return "rejected";
  }
  return null;
}

function buildStrategyPlanFromRaw(raw: Record<string, unknown>): TradePlanData | null {
  const stockCode = typeof raw.stock_code === "string" ? raw.stock_code : null;
  if (!stockCode) {
    return null;
  }

  return {
    stock_code: stockCode,
    stock_name: typeof raw.stock_name === "string" ? raw.stock_name : stockCode,
    current_price: toNumber(raw.current_price),
    direction: raw.direction === "sell" ? "sell" : "buy",
    entry_price: toNumber(raw.entry_price),
    entry_method: typeof raw.entry_method === "string" ? raw.entry_method : null,
    position_pct: toNumber(raw.position_pct),
    take_profit: toNumber(raw.take_profit),
    take_profit_method:
      typeof raw.take_profit_method === "string" ? raw.take_profit_method : null,
    stop_loss: toNumber(raw.stop_loss),
    stop_loss_method: typeof raw.stop_loss_method === "string" ? raw.stop_loss_method : null,
    reasoning: typeof raw.reasoning === "string" ? raw.reasoning : "",
    risk_note: typeof raw.risk_note === "string" ? raw.risk_note : null,
    invalidation: typeof raw.invalidation === "string" ? raw.invalidation : null,
    valid_until: typeof raw.valid_until === "string" ? raw.valid_until : null,
  };
}

function normalizeStrategyActions(raw: unknown): AgentStrategyActionRecord[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.items)
      ? raw.items
      : isRecord(raw) && Array.isArray(raw.actions)
        ? raw.actions
        : isRecord(raw) && Array.isArray(raw.results)
          ? raw.results
          : isRecord(raw)
            ? [raw]
            : [];

  return items
    .map((item, index) => {
      const data = isRecord(item) ? item : {};
      const planSource = isRecord(data.trade_plan)
        ? data.trade_plan
        : isRecord(data.plan)
          ? data.plan
          : isRecord(data.strategy)
            ? data.strategy
            : data;
      const plan = buildStrategyPlanFromRaw(planSource);
      const strategyKey =
        typeof data.strategy_key === "string"
          ? data.strategy_key
          : typeof data.plan_key === "string"
            ? data.plan_key
            : plan
              ? buildAgentStrategyKey(plan)
              : null;
      const action =
        normalizeStrategyDecision(data.decision)
        ?? normalizeStrategyDecision(data.action)
        ?? normalizeStrategyDecision(data.status);

      if (!strategyKey || !action) {
        return null;
      }

      return {
        id: typeof data.id === "string" ? data.id : `strategy-action-${index}`,
        session_id: typeof data.session_id === "string" ? data.session_id : null,
        message_id: typeof data.message_id === "string" ? data.message_id : null,
        strategy_key: strategyKey,
        action,
        status: typeof data.status === "string" ? data.status : null,
        reason: typeof data.reason === "string" ? data.reason : null,
        created_at: typeof data.created_at === "string" ? data.created_at : null,
        updated_at: typeof data.updated_at === "string" ? data.updated_at : null,
      };
    })
    .filter((value): value is AgentStrategyActionRecord => value !== null);
}

function applyStrategyRecord(
  current: AgentStrategyActionState | undefined,
  record: AgentStrategyActionRecord
): AgentStrategyActionState {
  return {
    id: record.id,
    action: record.action,
    status: record.status,
    reason: record.reason,
    updated_at: record.updated_at ?? record.created_at,
    is_submitting: current?.is_submitting ?? false,
    error: null,
  };
}

export default function AgentPage() {
  const [runs, setRuns] = useState<BrainRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BrainRun | null>(null);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [ledgerOverview, setLedgerOverview] = useState<LedgerOverview | null>(null);
  const [reviewRecords, setReviewRecords] = useState<ReviewRecord[]>([]);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [weeklySummaries, setWeeklySummaries] = useState<WeeklySummary[]>([]);
  const [memoryRules, setMemoryRules] = useState<MemoryRule[]>([]);
  const [reflectionFeed, setReflectionFeed] = useState<ReflectionFeedItem[]>([]);
  const [strategyHistory, setStrategyHistory] = useState<StrategyHistoryEntry[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [chatSessions, setChatSessions] = useState<AgentChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [chatEntries, setChatEntries] = useState<AgentChatEntry[]>([]);
  const [chatDraft, setChatDraft] = useState("");
  const [chatStreaming, setChatStreaming] = useState(false);
  const [chatSessionsLoading, setChatSessionsLoading] = useState(false);
  const [chatMessagesLoading, setChatMessagesLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [strategyActions, setStrategyActions] = useState<
    Record<string, AgentStrategyActionState>
  >({});
  const [strategyActionsError, setStrategyActionsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [reflectionLoading, setReflectionLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [stateError, setStateError] = useState<string | null>(null);
  const [ledgerError, setLedgerError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [reflectionError, setReflectionError] = useState<string | null>(null);
  const [strategyHistoryError, setStrategyHistoryError] = useState<string | null>(null);
  const [ledgerSource, setLedgerSource] = useState<
    "overview" | "fallback" | "unavailable" | null
  >(null);
  const [activeTab, setActiveTab] = useState<AgentConsoleTab>("runs");
  const [reviewType, setReviewType] = useState<"all" | "daily" | "weekly">("all");
  const [memoryStatus, setMemoryStatus] = useState<"all" | "active" | "retired">("all");
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/agent/portfolio`)
      .then((resp) => resp.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0 && typeof data[0]?.id === "string") {
          setPortfolioId(data[0].id);
        }
      })
      .catch(() => {});
  }, []);

  const fetchRuns = useCallback(async () => {
    if (!portfolioId) {
      return [];
    }
    const data = await fetchJson<BrainRun[]>(
      `${API_BASE}/api/v1/agent/brain/runs?portfolio_id=${portfolioId}`
    );
    setRuns(data);
    setSelectedRun((current) => {
      if (data.length === 0) {
        return null;
      }
      if (!current) {
        return data[0];
      }
      return data.find((run) => run.id === current.id) || data[0];
    });
    return data;
  }, [portfolioId]);

  const fetchAgentState = useCallback(async () => {
    if (!portfolioId) {
      return null;
    }
    const data = await fetchJson<unknown>(`${API_BASE}/api/v1/agent/state?portfolio_id=${portfolioId}`);
    const normalized = normalizeAgentState(portfolioId, data);
    setAgentState(normalized);
    return normalized;
  }, [portfolioId]);

  const fetchLedgerOverview = useCallback(async () => {
    if (!portfolioId) {
      return null;
    }
    try {
      const data = await fetchJson<unknown>(
        `${API_BASE}/api/v1/agent/ledger/overview?portfolio_id=${portfolioId}`
      );
      const normalized = normalizeLedgerOverview(portfolioId, data);
      setLedgerOverview(normalized);
      setLedgerSource("overview");
      setLedgerError(null);
      return normalized;
    } catch {
      try {
        const [portfolio, plans, trades] = await Promise.all([
          fetchJson<unknown>(`${API_BASE}/api/v1/agent/portfolio/${portfolioId}`),
          fetchJson<unknown>(`${API_BASE}/api/v1/agent/plans`),
          fetchJson<unknown>(`${API_BASE}/api/v1/agent/portfolio/${portfolioId}/trades?limit=20`),
        ]);
        const fallback = buildLedgerFallback(portfolioId, portfolio, plans, trades);
        setLedgerOverview(fallback);
        setLedgerSource("fallback");
        setLedgerError(null);
        return fallback;
      } catch {
        setLedgerOverview(null);
        setLedgerSource("unavailable");
        setLedgerError(
          "执行台账暂不可用，`ledger/overview` 尚未就绪且 fallback 读取失败。"
        );
        return null;
      }
    }
  }, [portfolioId]);

  const refreshConsole = useCallback(async () => {
    if (!portfolioId) {
      return;
    }
    setLoading(true);
    const [runsResult, stateResult] = await Promise.allSettled([
      fetchRuns(),
      fetchAgentState(),
    ]);
    await fetchLedgerOverview();
    if (runsResult.status === "rejected") {
      setRuns([]);
      setSelectedRun(null);
    }
    if (stateResult.status === "rejected") {
      setAgentState(null);
      setStateError("当前状态读取失败");
    } else {
      setStateError(null);
    }
    setLoading(false);
  }, [fetchAgentState, fetchLedgerOverview, fetchRuns, portfolioId]);

  const fetchReviewData = useCallback(async () => {
    if (!portfolioId) {
      return;
    }
    setReviewLoading(true);
    try {
      const [recordsRaw, statsRaw, weeklyRaw] = await Promise.all([
        fetchFirstAvailable<unknown>([
          `${API_BASE}/api/v1/agent/reviews?portfolio_id=${portfolioId}&days=30`,
        ]),
        fetchFirstAvailable<unknown>([
          `${API_BASE}/api/v1/agent/reviews/stats?portfolio_id=${portfolioId}&days=30`,
        ]),
        fetchFirstAvailable<unknown>([`${API_BASE}/api/v1/agent/reviews/weekly?limit=10`]),
      ]);

      const normalizedRecords = normalizeReviewRecords(recordsRaw);
      setReviewRecords(normalizedRecords);
      setReviewStats(normalizeReviewStats(statsRaw, normalizedRecords));
      setWeeklySummaries(normalizeWeeklySummaries(weeklyRaw));
      setReviewError(null);
    } catch {
      setReviewRecords([]);
      setReviewStats(null);
      setWeeklySummaries([]);
      setReviewError(
        "复盘读接口暂不可用，review records / stats / weekly summaries 尚未就绪。"
      );
    } finally {
      setReviewLoading(false);
    }
  }, [portfolioId]);

  const fetchMemoryData = useCallback(async () => {
    setMemoryLoading(true);
    try {
      const raw = await fetchFirstAvailable<unknown>([
        `${API_BASE}/api/v1/agent/memories?status=${memoryStatus}`,
      ]);
      setMemoryRules(normalizeMemoryRules(raw));
      setMemoryError(null);
    } catch {
      setMemoryRules([]);
      setMemoryError("经验规则读接口暂不可用，memory rules 端点尚未就绪。");
    } finally {
      setMemoryLoading(false);
    }
  }, [memoryStatus]);

  const fetchReflectionData = useCallback(async () => {
    if (!portfolioId) {
      return;
    }
    setReflectionLoading(true);
    const [feedResult, historyResult] = await Promise.allSettled([
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/reflections`),
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/strategy/history?portfolio_id=${portfolioId}`),
    ]);

    if (feedResult.status === "fulfilled") {
      setReflectionFeed(normalizeReflectionFeed(feedResult.value));
      setReflectionError(null);
    } else {
      setReflectionFeed([]);
      setReflectionError("反思 feed 接口暂不可用，`/api/v1/agent/reflections` 尚未就绪。");
    }

    if (historyResult.status === "fulfilled") {
      setStrategyHistory(normalizeStrategyHistory(historyResult.value));
      setStrategyHistoryError(null);
    } else {
      setStrategyHistory([]);
      setStrategyHistoryError(
        "策略历史接口暂不可用，`/api/v1/agent/strategy/history` 尚未就绪。"
      );
    }

    setReflectionLoading(false);
  }, [portfolioId]);

  const fetchChatSessions = useCallback(
    async (preferredSessionId?: string | null) => {
      if (!portfolioId) {
        setChatSessions([]);
        return [];
      }
      setChatSessionsLoading(true);
      try {
        const raw = await fetchJson<unknown>(
          `${API_BASE}/api/v1/agent/chat/sessions?portfolio_id=${portfolioId}`
        );
        const sessions = normalizeAgentChatSessions(portfolioId, raw);
        setChatSessions(sessions);
        setActiveSessionId((current) => {
          const target = preferredSessionId ?? current;
          if (target && sessions.some((session) => session.id === target)) {
            return target;
          }
          return sessions[0]?.id ?? null;
        });
        setSessionError(null);
        return sessions;
      } catch {
        setChatSessions([]);
        setSessionError("Agent chat session 列表暂不可用，`/api/v1/agent/chat/sessions` 尚未就绪。");
        return [];
      } finally {
        setChatSessionsLoading(false);
      }
    },
    [portfolioId]
  );

  const fetchSessionMessages = useCallback(
    async (sessionId: string) => {
      if (!portfolioId) {
        setChatEntries([]);
        return [];
      }
      setChatMessagesLoading(true);
      try {
        const raw = await fetchJson<unknown>(
          `${API_BASE}/api/v1/agent/chat/sessions/${sessionId}/messages?portfolio_id=${portfolioId}`
        );
        const messages = normalizeAgentChatMessages(sessionId, raw);
        setChatEntries(messages);
        setChatError(null);
        return messages;
      } catch {
        setChatEntries([]);
        setChatError(
          "Agent chat 消息读取失败，`/api/v1/agent/chat/sessions/{session_id}/messages` 尚未就绪。"
        );
        return [];
      } finally {
        setChatMessagesLoading(false);
      }
    },
    [portfolioId]
  );

  const fetchStrategyActions = useCallback(async (sessionId: string | null) => {
    if (!sessionId) {
      setStrategyActions({});
      setStrategyActionsError(null);
      return {};
    }
    try {
      const raw = await fetchJson<unknown>(
        `${API_BASE}/api/v1/agent/strategy-actions?session_id=${sessionId}`
      );
      const records = normalizeStrategyActions(raw);
      const next: Record<string, AgentStrategyActionState> = {};
      for (const record of records) {
        const lookupKey = buildAgentStrategyActionLookupKey(
          record.message_id,
          record.strategy_key
        );
        next[lookupKey] = applyStrategyRecord(next[lookupKey], record);
      }
      setStrategyActions(next);
      setStrategyActionsError(null);
      return next;
    } catch {
      setStrategyActions({});
      setStrategyActionsError(
        "策略动作记录暂不可用，`/api/v1/agent/strategy-actions?session_id=...` 尚未就绪。"
      );
      return {};
    }
  }, []);

  const createSession = useCallback(
    async (seedTitle?: string) => {
      if (!portfolioId) {
        return null;
      }
      try {
        const resp = await fetch(`${API_BASE}/api/v1/agent/chat/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            portfolio_id: portfolioId,
            title: seedTitle?.trim().slice(0, 32) || "新会话",
          }),
        });
        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }
        const raw = await resp.json();
        const session = normalizeAgentChatSessions(portfolioId, raw)[0];
        if (!session) {
          throw new Error("会话创建响应缺少 session id");
        }
        setChatSessions((current) => [session, ...current.filter((item) => item.id !== session.id)]);
        setActiveSessionId(session.id);
        setChatEntries([]);
        setStrategyActions({});
        setSessionError(null);
        return session.id;
      } catch (error) {
        setSessionError(error instanceof Error ? error.message : "创建 chat session 失败");
        return null;
      }
    },
    [portfolioId]
  );

  useEffect(() => {
    refreshConsole();
  }, [refreshConsole]);

  useEffect(() => {
    if (activeTab === "reviews" && portfolioId) {
      fetchReviewData();
    }
  }, [activeTab, fetchReviewData, portfolioId]);

  useEffect(() => {
    if (activeTab === "memory") {
      fetchMemoryData();
    }
  }, [activeTab, fetchMemoryData]);

  useEffect(() => {
    if (activeTab === "reflection" && portfolioId) {
      fetchReflectionData();
    }
  }, [activeTab, fetchReflectionData, portfolioId]);

  useEffect(() => {
    if (portfolioId) {
      fetchChatSessions();
    }
  }, [fetchChatSessions, portfolioId]);

  useEffect(() => {
    if (!activeSessionId) {
      setChatEntries([]);
      setStrategyActions({});
      return;
    }
    fetchSessionMessages(activeSessionId);
    fetchStrategyActions(activeSessionId);
  }, [activeSessionId, fetchSessionMessages, fetchStrategyActions]);

  const fetchWatchlist = useCallback(async () => {
    const resp = await fetch(`${API_BASE}/api/v1/agent/watchlist`);
    if (resp.ok) {
      setWatchlist(await resp.json());
    }
  }, []);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  const handleRun = async () => {
    if (!portfolioId || running) {
      return;
    }
    setRunning(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/brain/run?portfolio_id=${portfolioId}`, {
        method: "POST",
      });
      if (!resp.ok) {
        setRunning(false);
        return;
      }
      const run = (await resp.json()) as BrainRun;
      setSelectedRun(run);
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      const poll = setInterval(async () => {
        const result = await fetch(`${API_BASE}/api/v1/agent/brain/runs/${run.id}`);
        if (!result.ok) {
          return;
        }
        const updated = (await result.json()) as BrainRun;
        setSelectedRun(updated);
        setRuns((current) => {
          const next = current.filter((item) => item.id !== updated.id);
          return [updated, ...next];
        });
        if (updated.status !== "running") {
          clearInterval(poll);
          setRunning(false);
          refreshConsole();
        }
      }, 3000);
    } catch {
      setRunning(false);
    }
  };

  const handleCreateSession = useCallback(async () => {
    await createSession();
  }, [createSession]);

  const handleSendChat = useCallback(async () => {
    const content = chatDraft.trim();
    if (!content || chatStreaming || !portfolioId) {
      return;
    }

    const sessionId = activeSessionId ?? (await createSession(content));
    if (!sessionId) {
      return;
    }

    const createdAt = new Date().toISOString();
    const userEntry: AgentChatEntry = {
      id: nextChatEntryId(),
      role: "user",
      content,
      created_at: createdAt,
      session_id: sessionId,
      is_persisted: false,
    };
    const assistantEntry: AgentChatEntry = {
      id: nextChatEntryId(),
      role: "assistant",
      content: "",
      created_at: createdAt,
      session_id: sessionId,
      is_streaming: true,
      is_persisted: false,
    };

    setActiveSessionId(sessionId);
    setChatEntries((current) => [...current, userEntry, assistantEntry]);
    setChatDraft("");
    setChatError(null);
    setChatStreaming(true);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          portfolio_id: portfolioId,
          session_id: sessionId,
          message: content,
        }),
      });

      if (!resp.ok) {
        throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        throw new Error("浏览器不支持流式读取");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const eventBlock of events) {
          if (!eventBlock.trim()) {
            continue;
          }
          const lines = eventBlock.split("\n");
          let eventType = "";
          let eventData = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              eventData = line.slice(6);
            }
          }

          if (!eventType || !eventData) {
            continue;
          }

          const parsed = JSON.parse(eventData) as {
            token?: string;
            content?: string;
            full_text?: string;
            full_content?: string;
            message?: string;
          };

          if (eventType === "reply_token") {
            fullContent += parsed.token || parsed.content || "";
            setChatEntries((current) =>
              current.map((entry) =>
                entry.id === assistantEntry.id
                  ? { ...entry, content: fullContent }
                  : entry
              )
            );
          } else if (eventType === "reply_complete") {
            const finalContent = parsed.full_text || parsed.full_content || fullContent;
            setChatEntries((current) =>
              current.map((entry) =>
                entry.id === assistantEntry.id
                  ? { ...entry, content: finalContent, is_streaming: false }
                  : entry
              )
            );
            await Promise.all([
              fetchChatSessions(sessionId),
              fetchSessionMessages(sessionId),
              fetchStrategyActions(sessionId),
            ]);
            setChatStreaming(false);
            return;
          } else if (eventType === "error") {
            throw new Error(parsed.message || "Agent 回复失败");
          }
        }
      }

      await Promise.all([
        fetchChatSessions(sessionId),
        fetchSessionMessages(sessionId),
        fetchStrategyActions(sessionId),
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "发送消息失败";
      setChatError(message);
      setChatEntries((current) =>
        current.map((entry) =>
          entry.id === assistantEntry.id
            ? { ...entry, content: `❌ ${message}`, is_streaming: false }
            : entry
        )
      );
    } finally {
      setChatStreaming(false);
    }
  }, [
    activeSessionId,
    chatDraft,
    chatStreaming,
    createSession,
    fetchChatSessions,
    fetchSessionMessages,
    fetchStrategyActions,
    portfolioId,
  ]);

  const handleStrategyAction = useCallback(
    async (request: AgentStrategyActionRequest) => {
      if (!portfolioId) {
        return;
      }

      const lookupKey = buildAgentStrategyActionLookupKey(
        request.message_id,
        request.strategy_key
      );
      const pendingState = strategyActions[lookupKey];
      setStrategyActions((current) => ({
        ...current,
        [lookupKey]: {
          id: pendingState?.id ?? null,
          action: pendingState?.action ?? null,
          status: pendingState?.status ?? null,
          reason: pendingState?.reason ?? null,
          updated_at: pendingState?.updated_at ?? null,
          is_submitting: true,
          error: null,
        },
      }));

      const endpoint =
        request.intent === "adopt"
          ? `${API_BASE}/api/v1/agent/adopt-strategy`
          : `${API_BASE}/api/v1/agent/reject-strategy`;

      try {
        const resp = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            portfolio_id: portfolioId,
            session_id: request.session_id,
            message_id: request.message_id,
            strategy_key: request.strategy_key,
            stock_code: request.plan.stock_code,
            trade_plan: request.plan,
            reason: request.reason ?? null,
          }),
        });

        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }

        const raw = await resp.json().catch(() => null);
        const records = normalizeStrategyActions(raw);
        const matched = records.find(
          (record) =>
            record.message_id === request.message_id
            && record.strategy_key === request.strategy_key
        );

        setStrategyActions((current) => ({
          ...current,
          [lookupKey]: matched
            ? applyStrategyRecord(current[lookupKey], matched)
            : {
                id: current[lookupKey]?.id ?? null,
                action: request.intent === "adopt" ? "adopted" : "rejected",
                status: request.intent === "adopt" ? "adopted" : "rejected",
                reason: request.reason ?? null,
                updated_at: new Date().toISOString(),
                is_submitting: false,
                error: null,
              },
        }));
        fetchStrategyActions(request.session_id).catch(() => {});
      } catch (error) {
        const message = error instanceof Error ? error.message : "策略动作提交失败";
        setStrategyActions((current) => ({
          ...current,
          [lookupKey]: {
            ...(current[lookupKey] ?? {
              id: null,
              action: null,
              status: null,
              reason: null,
              updated_at: null,
            }),
            is_submitting: false,
            error: message,
          },
        }));
      }
    },
    [portfolioId, strategyActions, fetchStrategyActions]
  );

  const handleAddWatch = async () => {
    if (!newCode.trim()) {
      return;
    }
    await fetch(`${API_BASE}/api/v1/agent/watchlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        stock_code: newCode.trim(),
        stock_name: newName.trim() || newCode.trim(),
      }),
    });
    setNewCode("");
    setNewName("");
    fetchWatchlist();
  };

  const handleRemoveWatch = async (id: string) => {
    await fetch(`${API_BASE}/api/v1/agent/watchlist/${id}`, { method: "DELETE" });
    fetchWatchlist();
  };

  const statusColor: Record<string, string> = {
    running: "bg-blue-500/20 text-blue-400",
    completed: "bg-green-500/20 text-green-400",
    failed: "bg-red-500/20 text-red-400",
  };
  const activeRun = selectedRun || runs[0] || null;
  const filteredReviewRecords = reviewRecords.filter((record) => {
    if (reviewType === "all") {
      return true;
    }
    return record.review_type === reviewType;
  });
  const filteredMemoryRules = memoryRules.filter((rule) => {
    if (memoryStatus === "all") {
      return true;
    }
    return rule.status === memoryStatus;
  });
  const chatNotices = [sessionError, chatError, strategyActionsError].filter(
    (value): value is string => Boolean(value)
  );

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-white">
      <NavSidebar />
      <div className="ml-12 flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-white/10 p-4">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold">🤖 Agent Brain</h1>
            {activeRun && (
              <span className={`rounded px-2 py-0.5 text-xs ${statusColor[activeRun.status] || ""}`}>
                {activeRun.status === "running" ? "运行中..." : activeRun.status}
              </span>
            )}
          </div>
          <button
            onClick={handleRun}
            disabled={running || !portfolioId}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              running
                ? "cursor-wait bg-blue-500/20 text-blue-400"
                : "bg-white/10 text-white hover:bg-white/20"
            }`}
          >
            {running ? "运行中..." : "▶ 手动运行"}
          </button>
        </div>

        <div className="flex flex-1 flex-col overflow-hidden xl:flex-row">
          <div className="min-h-0 border-b border-white/10 xl:w-[430px] xl:min-w-[430px] xl:border-b-0 xl:border-r">
            <AgentChatPanel
              portfolioReady={Boolean(portfolioId)}
              sessions={chatSessions}
              activeSessionId={activeSessionId}
              sessionsLoading={chatSessionsLoading}
              messagesLoading={chatMessagesLoading}
              messages={chatEntries}
              notices={chatNotices}
              isStreaming={chatStreaming}
              draft={chatDraft}
              onDraftChange={setChatDraft}
              onSend={handleSendChat}
              onCreateSession={handleCreateSession}
              onSelectSession={setActiveSessionId}
              runs={runs}
              selectedRunId={activeRun?.id || null}
              onSelectRun={setSelectedRun}
              statusColor={statusColor}
              watchlist={watchlist}
              newCode={newCode}
              newName={newName}
              onNewCodeChange={setNewCode}
              onNewNameChange={setNewName}
              onAddWatch={handleAddWatch}
              onRemoveWatch={handleRemoveWatch}
              strategyActions={strategyActions}
              onStrategyAction={handleStrategyAction}
            />
          </div>

          <div className="flex-1 overflow-hidden">
            {!portfolioId ? (
              <div className="w-full py-20 text-center text-gray-500">请先创建虚拟账户</div>
            ) : (
              <div className="grid h-full grid-cols-1 xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
                <div className="overflow-y-auto border-r border-white/10 p-6">
                  <div className="space-y-6">
                    <div className="inline-flex rounded-xl border border-white/10 bg-white/5 p-1 text-sm">
                      {([
                        { key: "runs", label: "运行记录" },
                        { key: "reviews", label: "复盘记录" },
                        { key: "memory", label: "经验规则" },
                        { key: "reflection", label: "反思演进" },
                      ] as const).map((tab) => (
                        <button
                          key={tab.key}
                          type="button"
                          onClick={() => setActiveTab(tab.key)}
                          className={`rounded-lg px-4 py-2 transition-colors ${
                            activeTab === tab.key
                              ? "bg-white/15 text-white"
                              : "text-gray-400 hover:bg-white/10 hover:text-white"
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    {activeTab === "runs" ? (
                      <>
                        <AgentStatePanel
                          state={agentState}
                          run={activeRun}
                          loading={loading}
                          error={stateError}
                        />
                        <DecisionRunPanel
                          run={activeRun}
                          loading={loading}
                          statusColor={statusColor}
                        />
                      </>
                    ) : activeTab === "reviews" ? (
                      <ReviewRecordsPanel
                        loading={reviewLoading}
                        error={reviewError}
                        records={filteredReviewRecords}
                        stats={reviewStats}
                        weeklySummaries={weeklySummaries}
                        reviewType={reviewType}
                        onReviewTypeChange={setReviewType}
                      />
                    ) : activeTab === "memory" ? (
                      <MemoryRulesPanel
                        loading={memoryLoading}
                        error={memoryError}
                        rules={filteredMemoryRules}
                        statusFilter={memoryStatus}
                        onStatusFilterChange={setMemoryStatus}
                      />
                    ) : (
                      <ReflectionFeedPanel
                        loading={reflectionLoading}
                        error={reflectionError}
                        items={reflectionFeed}
                      />
                    )}
                  </div>
                </div>

                <div className="overflow-y-auto p-6">
                  {activeTab === "runs" ? (
                    <ExecutionLedgerPanel
                      overview={ledgerOverview}
                      loading={loading}
                      error={ledgerError}
                      source={ledgerSource}
                    />
                  ) : activeTab === "reviews" ? (
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-400">
                      右栏保留给执行台账。当前 tab 聚焦复盘摘要、记录列表和 weekly summaries。
                    </div>
                  ) : activeTab === "memory" ? (
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-400">
                      经验规则 tab 为只读规则库视图，不展示执行台账。
                    </div>
                  ) : (
                    <StrategyHistoryPanel
                      loading={reflectionLoading}
                      error={strategyHistoryError}
                      items={strategyHistory}
                    />
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
