"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { API_BASE } from "@/lib/api-base";
import type { TradePlanData } from "@/lib/parseTradePlan";
import NavSidebar from "@/components/ui/NavSidebar";
import AgentPetStage from "./components/AgentPetStage";
import CreatePortfolioDialog from "./components/CreatePortfolioDialog";

// 按需加载重型面板组件
const AgentChatPanel = dynamic(() => import("./components/AgentChatPanel"), { ssr: false });
const AgentStatePanel = dynamic(() => import("./components/AgentStatePanel"), { ssr: false });
const AgentTrainingPanel = dynamic(() => import("./components/AgentTrainingPanel"), { ssr: false });
const DecisionRunPanel = dynamic(() => import("./components/DecisionRunPanel"), { ssr: false });
const ExecutionLedgerPanel = dynamic(() => import("./components/ExecutionLedgerPanel"), { ssr: false });
const WatchSignalsPanel = dynamic(() => import("./components/WatchSignalsPanel"), { ssr: false });
const InfoDigestsPanel = dynamic(() => import("./components/InfoDigestsPanel"), { ssr: false });
const ReviewRecordsPanel = dynamic(() => import("./components/ReviewRecordsPanel"), { ssr: false });
const MemoryRulesPanel = dynamic(() => import("./components/MemoryRulesPanel"), { ssr: false });
const ReflectionFeedPanel = dynamic(() => import("./components/ReflectionFeedPanel"), { ssr: false });
const StrategyHistoryPanel = dynamic(() => import("./components/StrategyHistoryPanel"), { ssr: false });
const StrategyMemoPanel = dynamic(() => import("./components/StrategyMemoPanel"), { ssr: false });
const StrategyBrainPanel = dynamic(() => import("./components/StrategyBrainPanel"), { ssr: false });
import {
  buildWatchSignalPayload,
  filterInfoDigestsForRun,
  normalizeInfoDigests,
  normalizeWatchSignals,
  summarizeWatchSignals,
} from "./lib/wakeViewModel";
import {
  clampReplayDate,
  normalizeEquityTimeline,
  normalizeReplaySnapshot,
  pickDefaultReplayDate,
} from "./lib/rightRailTimelineViewModel";
import { normalizeReplayLearning } from "./lib/replayLearningViewModel";
import {
  normalizeBacktestDays,
  normalizeBacktestSummary,
} from "./lib/backtestArtifacts";
import { buildPetWorkspaceLayout } from "./lib/petWorkspaceLayout";
import {
  buildCreatePortfolioPayload,
  normalizePortfolioSummaries,
  pickActivePortfolioId,
  type CreatePortfolioDraft,
  type PortfolioSummary,
} from "./lib/portfolioWorkspace";
import { normalizeWatchlist } from "./lib/watchlist";
import {
  buildMemoRequestConfig,
  buildStrategyExecutionRequestConfig,
  mapExecutionRecord,
} from "./lib/strategyActionViewModel";
import {
  startBrainRunPoller,
  type BrainRunPollerHandle,
} from "./lib/brainRunPoller";
import { buildPetConsoleViewModel } from "./lib/petConsoleViewModel";
import { buildStrategyBrainViewModel } from "./lib/strategyBrainViewModel";
import {
  AgentBacktestDay,
  AgentBacktestSummary,
  AgentEquityTimeline,
  AgentLeftPanelTab,
  AgentReplayLearning,
  AgentReplaySnapshot,
  AgentChatEntry,
  AgentChatSession,
  AgentPageTab,
  AgentState,
  AgentStrategyExecutionRecord,
  AgentStrategyExecutionRequest,
  AgentStrategyExecutionState,
  AgentStrategyMemoSaveRequest,
  AgentStrategyMemoState,
  AgentVerificationSuiteResult,
  BrainRun,
  LedgerOverview,
  MemoryRule,
  InfoDigest,
  ReflectionFeedItem,
  ReviewRecord,
  ReviewStats,
  StrategyHistoryEntry,
  WakeDigestMode,
  WatchSignal,
  WatchSignalFormState,
  WatchlistItem,
  WeeklySummary,
  StrategyMemoEntry,
  buildAgentStrategyActionLookupKey,
  buildAgentStrategyKey,
} from "./types";

let chatEntryCounter = 0;

const EMPTY_WATCH_SIGNAL_FORM: WatchSignalFormState = {
  stock_code: "",
  sector: "",
  signal_description: "",
  keywords: "",
  if_triggered: "",
  cycle_context: "",
};

const DEFAULT_CREATE_PORTFOLIO_DRAFT: CreatePortfolioDraft = {
  id: "",
  mode: "paper",
  initialCapital: "1000000",
};

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

function buildStrategyPlanFromRaw(raw: Record<string, unknown>): TradePlanData | null {
  const stockCode = typeof raw.stock_code === "string" ? raw.stock_code : null;
  if (!stockCode) {
    return null;
  }

  // entry_price/take_profit 可能是数字或字符串（多档价格）
  const toStringOrNull = (v: unknown): string | null => {
    if (typeof v === "string") return v;
    if (typeof v === "number") return String(v);
    return null;
  };

  return {
    stock_code: stockCode,
    stock_name: typeof raw.stock_name === "string" ? raw.stock_name : stockCode,
    current_price: toNumber(raw.current_price),
    direction: raw.direction === "sell" ? "sell" : "buy",
    entry_price: toStringOrNull(raw.entry_price),
    entry_method: typeof raw.entry_method === "string" ? raw.entry_method : null,
    win_odds: typeof raw.win_odds === "string" ? raw.win_odds : null,
    take_profit: toStringOrNull(raw.take_profit),
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

function normalizeStrategyMemos(raw: unknown): StrategyMemoEntry[] {
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
  const normalized: StrategyMemoEntry[] = [];

  for (const [index, item] of items.entries()) {
    const data = isRecord(item) ? item : {};
    const planSource = isRecord(data.plan_snapshot)
      ? data.plan_snapshot
      : isRecord(data.plan)
        ? data.plan
        : isRecord(data.trade_plan)
          ? data.trade_plan
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
    const stockCode =
      plan?.stock_code || (typeof data.stock_code === "string" ? data.stock_code : "");

    if (!strategyKey || !stockCode) {
      continue;
    }

    normalized.push({
      id: typeof data.id === "string" ? data.id : `strategy-memo-${index}`,
      portfolio_id: typeof data.portfolio_id === "string" ? data.portfolio_id : null,
      source_agent: typeof data.source_agent === "string" ? data.source_agent : null,
      source_session_id:
        typeof data.source_session_id === "string" ? data.source_session_id : null,
      source_message_id:
        typeof data.source_message_id === "string" ? data.source_message_id : null,
      session_id:
        typeof data.source_session_id === "string"
          ? data.source_session_id
          : typeof data.session_id === "string"
            ? data.session_id
            : null,
      message_id:
        typeof data.source_message_id === "string"
          ? data.source_message_id
          : typeof data.message_id === "string"
            ? data.message_id
            : null,
      strategy_key: strategyKey,
      stock_code: stockCode,
      stock_name:
        plan?.stock_name
        || (typeof data.stock_name === "string" ? data.stock_name : null),
      plan_snapshot: plan,
      note: typeof data.note === "string" ? data.note : null,
      status:
        typeof data.status === "string"
          ? (data.status as StrategyMemoEntry["status"])
          : null,
      created_at: typeof data.created_at === "string" ? data.created_at : null,
      updated_at: typeof data.updated_at === "string" ? data.updated_at : null,
    });
  }

  return normalized;
}

function normalizeStrategyExecutionActions(raw: unknown): AgentStrategyExecutionRecord[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.items)
      ? raw.items
      : isRecord(raw) && Array.isArray(raw.actions)
        ? raw.actions
        : isRecord(raw)
          ? [raw]
          : [];
  return items
    .map((item) => mapExecutionRecord(isRecord(item) ? item : {}))
    .filter((value): value is AgentStrategyExecutionRecord => value !== null);
}

function normalizeVerificationSuiteResult(raw: unknown): AgentVerificationSuiteResult | null {
  if (!isRecord(raw)) {
    return null;
  }
  return {
    mode: raw.mode === "smoke" ? "smoke" : "default",
    overall_status:
      raw.overall_status === "fail"
        ? "fail"
        : raw.overall_status === "warn"
          ? "warn"
          : "pass",
    scenario_id: typeof raw.scenario_id === "string" ? raw.scenario_id : null,
    portfolio_id: typeof raw.portfolio_id === "string" ? raw.portfolio_id : null,
    seed_summary: isRecord(raw.seed_summary) ? raw.seed_summary : {},
    demo_verification: isRecord(raw.demo_verification) ? raw.demo_verification : {},
    backtest: isRecord(raw.backtest) ? raw.backtest : {},
    evidence: isRecord(raw.evidence) ? raw.evidence : {},
    next_actions: Array.isArray(raw.next_actions)
      ? raw.next_actions.filter((item): item is string => typeof item === "string")
      : [],
  };
}

function mapMemoToState(memo: StrategyMemoEntry): AgentStrategyMemoState | null {
  if (memo.status !== "saved") {
    return null;
  }
  return {
    id: memo.id,
    saved: true,
    note: memo.note,
    updated_at: memo.updated_at ?? memo.created_at,
    is_submitting: false,
    error: null,
  };
}

function applyExecutionRecordState(
  current: AgentStrategyExecutionState | undefined,
  record: AgentStrategyExecutionRecord
): AgentStrategyExecutionState {
  return {
    id: record.id,
    decision: record.decision,
    status: record.status,
    reason: record.reason,
    updated_at: record.updated_at ?? record.created_at,
    is_submitting: current?.is_submitting ?? false,
    error: null,
  };
}

function applyMemoState(
  current: AgentStrategyMemoState | undefined,
  state: AgentStrategyMemoState
): AgentStrategyMemoState {
  return {
    id: state.id,
    saved: state.saved,
    note: state.note,
    updated_at: state.updated_at,
    is_submitting: current?.is_submitting ?? false,
    error: null,
  };
}

export default function AgentPage() {
  const [runs, setRuns] = useState<BrainRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BrainRun | null>(null);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [ledgerOverview, setLedgerOverview] = useState<LedgerOverview | null>(null);
  const [equityTimeline, setEquityTimeline] = useState<AgentEquityTimeline | null>(null);
  const [replaySnapshot, setReplaySnapshot] = useState<AgentReplaySnapshot | null>(null);
  const [replayLearning, setReplayLearning] = useState<AgentReplayLearning | null>(null);
  const [replayDate, setReplayDate] = useState("");
  const [reviewRecords, setReviewRecords] = useState<ReviewRecord[]>([]);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [weeklySummaries, setWeeklySummaries] = useState<WeeklySummary[]>([]);
  const [memoryRules, setMemoryRules] = useState<MemoryRule[]>([]);
  const [watchSignals, setWatchSignals] = useState<WatchSignal[]>([]);
  const [infoDigests, setInfoDigests] = useState<InfoDigest[]>([]);
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
  const [executionActions, setExecutionActions] = useState<
    Record<string, AgentStrategyExecutionState>
  >({});
  const [executionActionsError, setExecutionActionsError] = useState<string | null>(null);
  const [memoStates, setMemoStates] = useState<
    Record<string, AgentStrategyMemoState>
  >({});
  const [memoStatesError, setMemoStatesError] = useState<string | null>(null);
  const [memoInboxItems, setMemoInboxItems] = useState<StrategyMemoEntry[]>([]);
  const [memoInboxLoading, setMemoInboxLoading] = useState(false);
  const [memoInboxError, setMemoInboxError] = useState<string | null>(null);
  const [memoMutatingId, setMemoMutatingId] = useState<string | null>(null);
  const [pageTab, setPageTab] = useState<AgentPageTab>("pet");
  const [leftPanelTab, setLeftPanelTab] = useState<AgentLeftPanelTab>("console");
  const [loading, setLoading] = useState(true);
  const [wakeLoading, setWakeLoading] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [reflectionLoading, setReflectionLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [suiteRunningMode, setSuiteRunningMode] = useState<"default" | "smoke" | null>(null);
  const [suiteResult, setSuiteResult] = useState<AgentVerificationSuiteResult | null>(null);
  const [suiteError, setSuiteError] = useState<string | null>(null);
  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [portfolioDialogOpen, setPortfolioDialogOpen] = useState(false);
  const [portfolioDraft, setPortfolioDraft] = useState<CreatePortfolioDraft>(
    DEFAULT_CREATE_PORTFOLIO_DRAFT
  );
  const [portfolioCreateSubmitting, setPortfolioCreateSubmitting] = useState(false);
  const [portfolioCreateError, setPortfolioCreateError] = useState<string | null>(null);
  const [stateError, setStateError] = useState<string | null>(null);
  const [ledgerError, setLedgerError] = useState<string | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [replayLearningError, setReplayLearningError] = useState<string | null>(null);
  const [watchSignalsError, setWatchSignalsError] = useState<string | null>(null);
  const [infoDigestsError, setInfoDigestsError] = useState<string | null>(null);
  const [wakeMutationError, setWakeMutationError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [reflectionError, setReflectionError] = useState<string | null>(null);
  const [strategyHistoryError, setStrategyHistoryError] = useState<string | null>(null);
  const [ledgerSource, setLedgerSource] = useState<
    "overview" | "fallback" | "unavailable" | null
  >(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayLearningLoading, setReplayLearningLoading] = useState(false);
  const [wakeDigestMode, setWakeDigestMode] = useState<WakeDigestMode>("selected_run");
  const [reviewType, setReviewType] = useState<"all" | "daily" | "weekly">("all");
  const [memoryStatus, setMemoryStatus] = useState<"all" | "active" | "retired">("all");
  const [watchSignalForm, setWatchSignalForm] = useState<WatchSignalFormState>({
    ...EMPTY_WATCH_SIGNAL_FORM,
  });
  const [watchSignalSubmitting, setWatchSignalSubmitting] = useState(false);
  const [watchSignalUpdatingId, setWatchSignalUpdatingId] = useState<string | null>(null);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [backtestStartDate, setBacktestStartDate] = useState("2026-03-18");
  const [backtestEndDate, setBacktestEndDate] = useState("2026-03-20");
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [backtestSummary, setBacktestSummary] = useState<AgentBacktestSummary | null>(null);
  const [backtestDays, setBacktestDays] = useState<AgentBacktestDay[]>([]);
  const chatEntriesRef = useRef<AgentChatEntry[]>([]);
  const brainRunPollerRef = useRef<BrainRunPollerHandle | null>(null);

  const stopBrainRunPoller = useCallback(() => {
    const poller = brainRunPollerRef.current;
    if (!poller) {
      return;
    }
    brainRunPollerRef.current = null;
    poller.stop();
  }, []);

  const fetchPortfolios = useCallback(async (preferredPortfolioId?: string | null) => {
    const raw = await fetchJson<unknown>(`${API_BASE}/api/v1/agent/portfolio`);
    const nextPortfolios = normalizePortfolioSummaries(raw);
    setPortfolios(nextPortfolios);
    setPortfolioId((current) => pickActivePortfolioId(nextPortfolios, current, preferredPortfolioId ?? null));
    if (nextPortfolios.length === 0) {
      setLoading(false);
    }
    return nextPortfolios;
  }, []);

  useEffect(() => {
    fetchPortfolios().catch(() => {
      setPortfolios([]);
      setPortfolioId(null);
      setLoading(false);
    });
  }, [fetchPortfolios]);

  useEffect(() => {
    chatEntriesRef.current = chatEntries;
  }, [chatEntries]);

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
          "执行台账加载失败，请确认后端已启动"
        );
        return null;
      }
    }
  }, [portfolioId]);

  const fetchEquityTimeline = useCallback(async () => {
    if (!portfolioId) {
      return null;
    }
    setTimelineLoading(true);
    try {
      const raw = await fetchJson<unknown>(
        `${API_BASE}/api/v1/agent/timeline/equity?portfolio_id=${portfolioId}`
      );
      const normalized = normalizeEquityTimeline(portfolioId, raw);
      setEquityTimeline(normalized);
      setTimelineError(null);

      const today = new Date().toISOString().slice(0, 10);
      const defaultReplayDate = clampReplayDate(
        pickDefaultReplayDate(normalized, today),
        normalized.start_date,
        normalized.end_date
      );
      setReplayDate((current) => {
        if (current) {
          return clampReplayDate(current, normalized.start_date, normalized.end_date);
        }
        return defaultReplayDate;
      });
      return normalized;
    } catch {
      setEquityTimeline(null);
      setTimelineError("收益曲线加载失败，请稍后重试");
      setReplayDate((current) => current || new Date().toISOString().slice(0, 10));
      return null;
    } finally {
      setTimelineLoading(false);
    }
  }, [portfolioId]);

  const fetchReplaySnapshot = useCallback(async () => {
    if (!portfolioId || !replayDate) {
      return null;
    }
    setReplayLoading(true);
    try {
      const raw = await fetchJson<unknown>(
        `${API_BASE}/api/v1/agent/timeline/replay?portfolio_id=${portfolioId}&date=${replayDate}`
      );
      const normalized = normalizeReplaySnapshot(portfolioId, raw);
      setReplaySnapshot(normalized);
      setReplayError(null);
      return normalized;
    } catch {
      setReplaySnapshot(null);
      setReplayError("历史回放加载失败，请稍后重试");
      return null;
    } finally {
      setReplayLoading(false);
    }
  }, [portfolioId, replayDate]);

  const fetchReplayLearning = useCallback(async () => {
    if (!portfolioId || !replayDate) {
      return null;
    }
    setReplayLearningLoading(true);
    try {
      const raw = await fetchJson<unknown>(
        `${API_BASE}/api/v1/agent/timeline/replay-learning?portfolio_id=${portfolioId}&date=${replayDate}`
      );
      const normalized = normalizeReplayLearning(portfolioId, raw);
      setReplayLearning(normalized);
      setReplayLearningError(null);
      return normalized;
    } catch {
      setReplayLearning(null);
      setReplayLearningError("学习回放加载失败，请稍后重试");
      return null;
    } finally {
      setReplayLearningLoading(false);
    }
  }, [portfolioId, replayDate]);

  const refreshConsole = useCallback(async () => {
    if (!portfolioId) {
      return;
    }
    setLoading(true);
    const [runsResult, stateResult] = await Promise.allSettled([
      fetchRuns(),
      fetchAgentState(),
      fetchEquityTimeline(),
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
  }, [fetchAgentState, fetchEquityTimeline, fetchLedgerOverview, fetchRuns, portfolioId]);

  const openCreatePortfolioDialog = useCallback(() => {
    setPortfolioCreateError(null);
    setPortfolioDraft(DEFAULT_CREATE_PORTFOLIO_DRAFT);
    setPortfolioDialogOpen(true);
  }, []);

  const closeCreatePortfolioDialog = useCallback(() => {
    if (portfolioCreateSubmitting) {
      return;
    }
    setPortfolioDialogOpen(false);
    setPortfolioCreateError(null);
    setPortfolioDraft(DEFAULT_CREATE_PORTFOLIO_DRAFT);
  }, [portfolioCreateSubmitting]);

  const handleCreatePortfolio = useCallback(async () => {
    const payloadResult = buildCreatePortfolioPayload(portfolioDraft);
    if (!payloadResult.ok) {
      setPortfolioCreateError(payloadResult.error);
      return;
    }

    setPortfolioCreateSubmitting(true);
    setPortfolioCreateError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/portfolio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadResult.value),
      });
      if (!resp.ok) {
        throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
      }
      const raw = await resp.json();
      const createdPortfolioId =
        isRecord(raw) && typeof raw.id === "string" ? raw.id : payloadResult.value.id;
      await fetchPortfolios(createdPortfolioId);
      setPortfolioDialogOpen(false);
      setPortfolioDraft(DEFAULT_CREATE_PORTFOLIO_DRAFT);
    } catch (error) {
      setPortfolioCreateError(error instanceof Error ? error.message : "创建虚拟账户失败");
    } finally {
      setPortfolioCreateSubmitting(false);
    }
  }, [fetchPortfolios, portfolioDraft]);

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
        "复盘数据加载失败，请确认后端已启动"
      );
    } finally {
      setReviewLoading(false);
    }
  }, [portfolioId]);

  const fetchMemoryData = useCallback(async () => {
    if (!portfolioId) return;
    setMemoryLoading(true);
    try {
      const raw = await fetchFirstAvailable<unknown>([
        `${API_BASE}/api/v1/agent/memories?status=${memoryStatus}&portfolio_id=${portfolioId}`,
      ]);
      setMemoryRules(normalizeMemoryRules(raw));
      setMemoryError(null);
    } catch {
      setMemoryRules([]);
      setMemoryError("经验规则加载失败，请确认后端已启动");
    } finally {
      setMemoryLoading(false);
    }
  }, [memoryStatus, portfolioId]);

  const fetchReflectionData = useCallback(async () => {
    if (!portfolioId) {
      return;
    }
    setReflectionLoading(true);
    const [feedResult, historyResult] = await Promise.allSettled([
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/reflections?portfolio_id=${portfolioId}`),
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/strategy/history?portfolio_id=${portfolioId}`),
    ]);

    if (feedResult.status === "fulfilled") {
      setReflectionFeed(normalizeReflectionFeed(feedResult.value));
      setReflectionError(null);
    } else {
      setReflectionFeed([]);
      setReflectionError("反思记录加载失败，请确认后端已启动");
    }

    if (historyResult.status === "fulfilled") {
      setStrategyHistory(normalizeStrategyHistory(historyResult.value));
      setStrategyHistoryError(null);
    } else {
      setStrategyHistory([]);
      setStrategyHistoryError(
        "策略历史加载失败，请确认后端已启动"
      );
    }

    setReflectionLoading(false);
  }, [portfolioId]);

  const fetchWakeData = useCallback(async () => {
    if (!portfolioId) {
      return;
    }

    setWakeLoading(true);
    const [signalsResult, digestsResult] = await Promise.allSettled([
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/watch-signals?portfolio_id=${portfolioId}`),
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/info-digests?portfolio_id=${portfolioId}&limit=30`),
    ]);

    if (signalsResult.status === "fulfilled") {
      setWatchSignals(normalizeWatchSignals(signalsResult.value));
      setWatchSignalsError(null);
    } else {
      setWatchSignals([]);
      setWatchSignalsError(
        "观察信号加载失败，请确认后端已启动"
      );
    }

    if (digestsResult.status === "fulfilled") {
      setInfoDigests(normalizeInfoDigests(digestsResult.value));
      setInfoDigestsError(null);
    } else {
      setInfoDigests([]);
      setInfoDigestsError(
        "信息摘要加载失败，请确认后端已启动"
      );
    }

    setWakeLoading(false);
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
        setSessionError("对话列表加载失败，请确认后端已启动");
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
        chatEntriesRef.current = [];
        setChatEntries([]);
        return [];
      }
      setChatMessagesLoading(true);
      try {
        const raw = await fetchJson<unknown>(
          `${API_BASE}/api/v1/agent/chat/sessions/${sessionId}/messages?portfolio_id=${portfolioId}`
        );
        const messages = normalizeAgentChatMessages(sessionId, raw);
        chatEntriesRef.current = messages;
        setChatEntries(messages);
        setChatError(null);
        return messages;
      } catch {
        chatEntriesRef.current = [];
        setChatEntries([]);
        setChatError(
          "对话消息加载失败，请确认后端已启动"
        );
        return [];
      } finally {
        setChatMessagesLoading(false);
      }
    },
    [portfolioId]
  );

  const fetchExecutionActions = useCallback(async (sessionId: string | null) => {
    if (!sessionId) {
      setExecutionActions({});
      setExecutionActionsError(null);
      return {};
    }
    try {
      const raw = await fetchJson<unknown>(
        `${API_BASE}/api/v1/agent/strategy-actions?session_id=${sessionId}`
      );
      const actions = normalizeStrategyExecutionActions(raw);
      const next: Record<string, AgentStrategyExecutionState> = {};
      for (const action of actions) {
        const lookupKey = buildAgentStrategyActionLookupKey(action.message_id, action.strategy_key);
        next[lookupKey] = applyExecutionRecordState(next[lookupKey], action);
      }
      setExecutionActions(next);
      setExecutionActionsError(null);
      return next;
    } catch {
      setExecutionActions({});
      setExecutionActionsError("策略执行记录加载失败，请确认后端已启动");
      return {};
    }
  }, []);

  const fetchMemoStates = useCallback(async (
    sessionId: string | null,
    sessionEntries?: AgentChatEntry[],
  ) => {
    if (!portfolioId) {
      setMemoStates({});
      setMemoStatesError(null);
      setMemoInboxItems([]);
      return {};
    }
    setMemoInboxLoading(true);
    try {
      const raw = await fetchJson<unknown>(
        `${API_BASE}/api/v1/agent/strategy-memos?portfolio_id=${portfolioId}&limit=200`
      );
      const memos = normalizeStrategyMemos(raw);
      setMemoInboxItems(memos.filter((memo) => memo.status === "saved"));
      setMemoInboxError(null);

      if (!sessionId) {
        setMemoStates({});
        setMemoStatesError(null);
        return {};
      }

      const entries = sessionEntries ?? chatEntriesRef.current;
      const currentSessionMessageIds = new Set(
        entries
          .filter((entry) => entry.session_id === sessionId)
          .map((entry) => entry.id)
      );
      const next: Record<string, AgentStrategyMemoState> = {};
      for (const memo of memos) {
        const matchesSession =
          memo.session_id === sessionId
          || (!memo.session_id && memo.message_id && currentSessionMessageIds.has(memo.message_id));
        if (!matchesSession || !memo.message_id) {
          continue;
        }
        const state = mapMemoToState(memo);
        if (!state) {
          continue;
        }
        const lookupKey = buildAgentStrategyActionLookupKey(memo.message_id, memo.strategy_key);
        next[lookupKey] = applyMemoState(next[lookupKey], state);
      }
      setMemoStates(next);
      setMemoStatesError(null);
      return next;
    } catch {
      setMemoStates({});
      setMemoStatesError("策略备忘加载失败，请确认后端已启动");
      setMemoInboxItems([]);
      setMemoInboxError("策略备忘列表读取失败。");
      return {};
    } finally {
      setMemoInboxLoading(false);
    }
  }, [portfolioId]);

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
        chatEntriesRef.current = [];
        setChatEntries([]);
        setExecutionActions({});
        setMemoStates({});
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
    if (portfolioId && replayDate) {
      fetchReplaySnapshot();
      fetchReplayLearning();
    }
  }, [fetchReplayLearning, fetchReplaySnapshot, portfolioId, replayDate]);

  useEffect(() => {
    if (portfolioId) {
      fetchWakeData();
    }
  }, [fetchWakeData, portfolioId]);

  useEffect(() => {
    if (portfolioId) {
      fetchReviewData();
    }
  }, [fetchReviewData, portfolioId]);

  useEffect(() => {
    if (portfolioId) {
      fetchMemoryData();
      fetchReflectionData();
    }
  }, [fetchMemoryData, fetchReflectionData, portfolioId]);

  useEffect(() => {
    if (equityTimeline?.start_date && equityTimeline?.end_date) {
      setBacktestStartDate((current) => current || equityTimeline.start_date || "2026-03-18");
      setBacktestEndDate((current) => current || equityTimeline.end_date || "2026-03-20");
    }
  }, [equityTimeline]);

  useEffect(() => {
    if (portfolioId) {
      fetchChatSessions();
    }
  }, [fetchChatSessions, portfolioId]);

  useEffect(() => {
    stopBrainRunPoller();
    setRunning(false);
    setRunError(null);
    setSuiteError(null);
    setSuiteRunningMode(null);
  }, [portfolioId, stopBrainRunPoller]);

  useEffect(() => () => {
    stopBrainRunPoller();
  }, [stopBrainRunPoller]);

  useEffect(() => {
    let cancelled = false;

    const syncSessionPanels = async () => {
      if (!activeSessionId) {
        chatEntriesRef.current = [];
        setChatEntries((current) => (current.length === 0 ? current : []));
        await fetchExecutionActions(null);
        await fetchMemoStates(null, []);
        return;
      }

      const messages = await fetchSessionMessages(activeSessionId);
      if (cancelled) {
        return;
      }

      await Promise.all([
        fetchExecutionActions(activeSessionId),
        fetchMemoStates(activeSessionId, messages),
      ]);
    };

    void syncSessionPanels();

    return () => {
      cancelled = true;
    };
  }, [activeSessionId, fetchExecutionActions, fetchMemoStates, fetchSessionMessages]);

  const fetchWatchlist = useCallback(async () => {
    if (!portfolioId) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/watchlist?portfolio_id=${portfolioId}`);
      if (!resp.ok) {
        setWatchlist([]);
        return;
      }
      setWatchlist(normalizeWatchlist(await resp.json()));
    } catch {
      setWatchlist([]);
    }
  }, [portfolioId]);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  const handleWatchSignalFormChange = useCallback(
    (field: keyof WatchSignalFormState, value: string) => {
      setWatchSignalForm((current) => ({
        ...current,
        [field]: value,
      }));
    },
    []
  );

  const handleReplayDateChange = useCallback((value: string) => {
    if (!value) {
      return;
    }
    setReplayDate(
      clampReplayDate(
        value,
        equityTimeline?.start_date ?? null,
        equityTimeline?.end_date ?? null
      )
    );
  }, [equityTimeline]);

  const handleCreateWatchSignal = useCallback(async () => {
    const payload = buildWatchSignalPayload(portfolioId, watchSignalForm);
    if (!payload) {
      setWakeMutationError("请至少填写股票代码和信号描述。");
      return;
    }

    setWatchSignalSubmitting(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/watch-signals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
      }
      setWatchSignalForm({ ...EMPTY_WATCH_SIGNAL_FORM });
      setWakeMutationError(null);
      await fetchWakeData();
    } catch (error) {
      setWakeMutationError(
        error instanceof Error ? error.message : "创建观察信号失败"
      );
    } finally {
      setWatchSignalSubmitting(false);
    }
  }, [fetchWakeData, portfolioId, watchSignalForm]);

  const handleWatchSignalStatusChange = useCallback(
    async (signalId: string, status: "triggered" | "cancelled") => {
      setWatchSignalUpdatingId(signalId);
      try {
        const resp = await fetch(`${API_BASE}/api/v1/agent/watch-signals/${signalId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        });
        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }
        setWakeMutationError(null);
        await fetchWakeData();
      } catch (error) {
        setWakeMutationError(
          error instanceof Error ? error.message : "更新观察信号失败"
        );
      } finally {
        setWatchSignalUpdatingId(null);
      }
    },
    [fetchWakeData]
  );

  const handleRun = async () => {
    if (!portfolioId || running) {
      return;
    }
    stopBrainRunPoller();
    setRunning(true);
    setRunError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/brain/run?portfolio_id=${portfolioId}`, {
        method: "POST",
      });
      if (!resp.ok) {
        throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
      }
      const run = (await resp.json()) as BrainRun;
      setSelectedRun(run);
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      const poller = startBrainRunPoller({
        intervalMs: 3_000,
        requestTimeoutMs: 15_000,
        maxPollMs: 5 * 60 * 1_000,
        maxConsecutiveErrors: 5,
        loadRun: async (signal) => {
          const result = await fetch(`${API_BASE}/api/v1/agent/brain/runs/${run.id}`, { signal });
          if (!result.ok) {
            throw new Error(await readErrorMessage(result, `HTTP ${result.status}`));
          }
          return (await result.json()) as BrainRun;
        },
        onUpdate: (updated) => {
          setSelectedRun(updated);
          setRuns((current) => {
            const next = current.filter((item) => item.id !== updated.id);
            return [updated, ...next];
          });
        },
        onTerminal: async (updated) => {
          setRunning(false);
          if (updated.status === "failed" && updated.error_message) {
            setRunError(updated.error_message);
          }
          await refreshConsole();
          await fetchWakeData();
        },
        onTimeout: () => {
          setRunning(false);
          setRunError("主脑运行超时，请检查服务是否稳定。");
        },
        onError: () => {
          setRunning(false);
          setRunError("主脑运行状态查询失败，请检查服务是否稳定。");
        },
      });
      brainRunPollerRef.current = poller;
      void poller.done.finally(() => {
        if (brainRunPollerRef.current === poller) {
          brainRunPollerRef.current = null;
        }
      });
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "主脑运行失败");
      setRunning(false);
    }
  };

  const fetchBacktestArtifacts = useCallback(async (runId: string) => {
    const [summaryRaw, daysRaw] = await Promise.all([
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/backtest/run/${runId}`),
      fetchJson<unknown>(`${API_BASE}/api/v1/agent/backtest/run/${runId}/days`),
    ]);
    setBacktestSummary(normalizeBacktestSummary(summaryRaw));
    setBacktestDays(normalizeBacktestDays(daysRaw));
  }, []);

  const handleRunTrainingSuite = useCallback(
    async (mode: "default" | "smoke") => {
      setSuiteRunningMode(mode);
      setSuiteError(null);
      try {
        const resp = await fetch(`${API_BASE}/api/v1/agent/verification-suite/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scenario_id: "demo-evolution",
            smoke_mode: mode === "smoke",
          }),
        });
        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }
        const raw = await resp.json();
        const normalized = normalizeVerificationSuiteResult(raw);
        if (!normalized) {
          throw new Error("训练结果解析失败");
        }
        setSuiteResult({
          ...normalized,
          requested_portfolio_id: portfolioId,
        });
        const suiteBacktest = isRecord(normalized.backtest)
          ? normalizeBacktestSummary({
              ...normalized.backtest,
              ...(isRecord(normalized.backtest.summary) ? normalized.backtest.summary : {}),
              run_id:
                typeof normalized.backtest.run_id === "string"
                  ? normalized.backtest.run_id
                  : typeof normalized.evidence.backtest_run_id === "string"
                    ? normalized.evidence.backtest_run_id
                    : undefined,
            })
          : null;
        if (suiteBacktest) {
          setBacktestSummary(suiteBacktest);
          await fetchBacktestArtifacts(suiteBacktest.run_id);
        }
        await Promise.all([
          refreshConsole(),
          fetchReviewData(),
          fetchMemoryData(),
          fetchReflectionData(),
          fetchWakeData(),
        ]);
      } catch (error) {
        setSuiteError(error instanceof Error ? error.message : "训练闭环运行失败");
      } finally {
        setSuiteRunningMode(null);
      }
    },
    [
      fetchBacktestArtifacts,
      fetchMemoryData,
      fetchReflectionData,
      fetchReviewData,
      fetchWakeData,
      refreshConsole,
    ]
  );

  const handleRunBacktest = useCallback(async () => {
    if (!portfolioId || backtestRunning) {
      return;
    }
    setBacktestRunning(true);
    setBacktestError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          portfolio_id: portfolioId,
          start_date: backtestStartDate,
          end_date: backtestEndDate,
          execution_price_mode: "next_open",
        }),
      });
      if (!resp.ok) {
        throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
      }
      const raw = await resp.json();
      const runId = isRecord(raw) && typeof raw.run_id === "string" ? raw.run_id : null;
      if (!runId) {
        throw new Error("回测响应缺少 run_id");
      }
      await fetchBacktestArtifacts(runId);
      setPageTab("backtest");
    } catch (error) {
      setBacktestError(error instanceof Error ? error.message : "回测启动失败");
    } finally {
      setBacktestRunning(false);
    }
  }, [backtestEndDate, backtestRunning, backtestStartDate, fetchBacktestArtifacts, portfolioId]);

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
            const messages = await fetchSessionMessages(sessionId);
            await Promise.all([
              fetchChatSessions(sessionId),
              fetchExecutionActions(sessionId),
              fetchMemoStates(sessionId, messages),
            ]);
            setChatStreaming(false);
            return;
          } else if (eventType === "error") {
            throw new Error(parsed.message || "Agent 回复失败");
          }
        }
      }

      const messages = await fetchSessionMessages(sessionId);
      await Promise.all([
        fetchChatSessions(sessionId),
        fetchExecutionActions(sessionId),
        fetchMemoStates(sessionId, messages),
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
    fetchExecutionActions,
    fetchMemoStates,
    fetchSessionMessages,
    portfolioId,
  ]);

  const handleExecutionAction = useCallback(
    async (request: AgentStrategyExecutionRequest) => {
      if (!portfolioId) {
        return;
      }

      const lookupKey = buildAgentStrategyActionLookupKey(
        request.message_id,
        request.strategy_key
      );
      const pendingState = executionActions[lookupKey];
      setExecutionActions((current) => ({
        ...current,
        [lookupKey]: {
          id: pendingState?.id ?? null,
          decision: pendingState?.decision ?? null,
          status: pendingState?.status ?? null,
          reason: pendingState?.reason ?? null,
          updated_at: pendingState?.updated_at ?? null,
          is_submitting: true,
          error: null,
        },
      }));

      const config = buildStrategyExecutionRequestConfig(
        request.intent,
        {
          portfolio_id: portfolioId,
          session_id: request.session_id,
          message_id: request.message_id,
          strategy_key: request.strategy_key,
          plan: request.plan,
          source_run_id: request.source_run_id ?? null,
          ...(request.intent === "reject" ? { reason: request.reason ?? null } : {}),
        }
      );

      try {
        const resp = await fetch(`${API_BASE}${config.endpoint}`, {
          method: config.method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config.body),
        });

        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }

        const raw = await resp.json().catch(() => null);
        const record = mapExecutionRecord(isRecord(raw) ? raw : {});

        setExecutionActions((current) => ({
          ...current,
          [lookupKey]: record
            ? applyExecutionRecordState(current[lookupKey], record)
            : {
                id: current[lookupKey]?.id ?? null,
                decision: request.intent === "adopt" ? "adopted" : "rejected",
                status: request.intent === "adopt" ? "adopted" : "rejected",
                reason: request.intent === "reject" ? request.reason ?? null : null,
                updated_at: new Date().toISOString(),
                is_submitting: false,
                error: null,
              },
        }));
        fetchExecutionActions(request.session_id).catch(() => {});
      } catch (error) {
        const message = error instanceof Error ? error.message : "策略执行提交失败";
        setExecutionActions((current) => ({
          ...current,
          [lookupKey]: {
            ...(current[lookupKey] ?? {
              id: null,
              decision: null,
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
    [executionActions, fetchExecutionActions, portfolioId]
  );

  const handleSaveMemo = useCallback(
    async (request: AgentStrategyMemoSaveRequest) => {
      if (!portfolioId) {
        return;
      }

      const lookupKey = buildAgentStrategyActionLookupKey(
        request.message_id,
        request.strategy_key
      );
      const pendingState = memoStates[lookupKey];
      setMemoStates((current) => ({
        ...current,
        [lookupKey]: {
          id: pendingState?.id ?? null,
          saved: pendingState?.saved ?? false,
          note: pendingState?.note ?? null,
          updated_at: pendingState?.updated_at ?? null,
          is_submitting: true,
          error: null,
        },
      }));

      const config = buildMemoRequestConfig(portfolioId, request);

      try {
        const resp = await fetch(`${API_BASE}${config.endpoint}`, {
          method: config.method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config.body),
        });

        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }

        const raw = await resp.json().catch(() => null);
        const memo = normalizeStrategyMemos(raw).find(
          (item) =>
            item.message_id === request.message_id
            && item.strategy_key === request.strategy_key
        ) ?? null;
        const state = memo ? mapMemoToState(memo) : null;

        setMemoStates((current) => ({
          ...current,
          [lookupKey]: state
            ? applyMemoState(current[lookupKey], state)
            : {
                id: current[lookupKey]?.id ?? null,
                saved: true,
                note: request.note ?? null,
                updated_at: new Date().toISOString(),
                is_submitting: false,
                error: null,
              },
        }));
        fetchMemoStates(request.session_id).catch(() => {});
      } catch (error) {
        const message = error instanceof Error ? error.message : "策略收藏提交失败";
        setMemoStates((current) => ({
          ...current,
          [lookupKey]: {
            ...(current[lookupKey] ?? {
              id: null,
              saved: false,
              note: null,
              updated_at: null,
            }),
            is_submitting: false,
            error: message,
          },
        }));
      }
    },
    [fetchMemoStates, memoStates, portfolioId]
  );

  const handleArchiveMemo = useCallback(
    async (memoId: string) => {
      if (!portfolioId) {
        return;
      }
      setMemoMutatingId(memoId);
      try {
        const resp = await fetch(`${API_BASE}/api/v1/agent/strategy-memos/${memoId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "archived" }),
        });
        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }
        await fetchMemoStates(activeSessionId);
      } catch (error) {
        setMemoInboxError(error instanceof Error ? error.message : "归档备忘失败");
      } finally {
        setMemoMutatingId(null);
      }
    },
    [activeSessionId, fetchMemoStates, portfolioId]
  );

  const handleDeleteMemo = useCallback(
    async (memoId: string) => {
      if (!portfolioId) {
        return;
      }
      setMemoMutatingId(memoId);
      try {
        const resp = await fetch(`${API_BASE}/api/v1/agent/strategy-memos/${memoId}`, {
          method: "DELETE",
        });
        if (!resp.ok) {
          throw new Error(await readErrorMessage(resp, `HTTP ${resp.status}`));
        }
        await fetchMemoStates(activeSessionId);
      } catch (error) {
        setMemoInboxError(error instanceof Error ? error.message : "删除备忘失败");
      } finally {
        setMemoMutatingId(null);
      }
    },
    [activeSessionId, fetchMemoStates, portfolioId]
  );

  const handleAddWatch = async () => {
    if (!newCode.trim() || !portfolioId) {
      return;
    }
    await fetch(`${API_BASE}/api/v1/agent/watchlist?portfolio_id=${portfolioId}`, {
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
  const wakeSummary = summarizeWatchSignals(watchSignals);
  const visibleInfoDigests = filterInfoDigestsForRun(
    infoDigests,
    activeRun?.id || null,
    wakeDigestMode
  );
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
  const strategyBrain = buildStrategyBrainViewModel({
    state: agentState,
    runs,
    memoryRules: filteredMemoryRules,
    reflectionFeed,
    strategyHistory,
    activeRun,
  });
  const strategySummary = [
    `市场 ${strategyBrain.snapshot.marketViewLabel}`,
    `仓位 ${strategyBrain.snapshot.positionLevelLabel}`,
    `风险 ${strategyBrain.snapshot.riskAlertCount} 项`,
  ].join(" · ");
  const petConsole = buildPetConsoleViewModel({
    currentPortfolioId: portfolioId,
    activeRun,
    ledgerOverview,
    agentState,
    strategySummary,
    suiteResult:
      suiteResult && portfolioId
        ? (suiteResult.requested_portfolio_id ?? suiteResult.portfolio_id) === portfolioId
          ? suiteResult
          : null
        : suiteResult,
  });
  const chatNotices = [sessionError, chatError, executionActionsError, memoStatesError].filter(
    (value): value is string => Boolean(value)
  );
  const petWorkspaceLayout = buildPetWorkspaceLayout();

  return (
    <div className="flex h-screen bg-[#f3eadb] text-slate-950">
      <NavSidebar />
      <div className="ml-12 flex flex-1 flex-col overflow-hidden">
        <div className="border-b border-black/10 bg-[#fffaf1]/90 px-5 py-4 backdrop-blur">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Main Agent Console</div>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
                电子宠物培养台
              </h1>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                在这里对话、训练、派它去模拟盘打仗，也把它丢进历史里考试。
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {portfolioId && (
                <div className="flex items-center gap-2 rounded-2xl border border-black/10 bg-white/80 px-3 py-2">
                  <span className="text-[11px] uppercase tracking-[0.22em] text-slate-400">账户</span>
                  <select
                    value={portfolioId}
                    onChange={(event) => setPortfolioId(event.target.value)}
                    className="bg-transparent text-sm font-medium text-slate-900 outline-none"
                    aria-label="切换虚拟账户"
                  >
                    {portfolios.map((portfolio) => (
                      <option key={portfolio.id} value={portfolio.id}>
                        {portfolio.id} · {portfolio.mode}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={async () => {
                      if (!confirm(`确定删除账户「${portfolioId}」及其所有数据？此操作不可撤销。`)) return;
                      try {
                        const res = await fetch(`${API_BASE}/api/v1/agent/portfolio/${portfolioId}`, { method: "DELETE" });
                        if (!res.ok) {
                          alert(`删除失败: ${res.status}`);
                          return;
                        }
                        window.location.reload();
                      } catch {
                        alert("删除失败，请确认后端已启动");
                      }
                    }}
                    className="ml-1 rounded-full p-1 text-slate-400 transition hover:bg-red-50 hover:text-red-500"
                    title="删除此账户"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </div>
              )}
              {activeRun && (
                <span className={`rounded-full px-3 py-1 text-xs ${statusColor[activeRun.status] || ""}`}>
                  {activeRun.status === "running" ? "运行中..." : activeRun.status}
                </span>
              )}
              <button
                type="button"
                onClick={openCreatePortfolioDialog}
                className="rounded-2xl border border-black/10 bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-50"
              >
                {portfolioId ? "新建账户" : "创建虚拟账户"}
              </button>
              <button
                onClick={handleRun}
                disabled={running || !portfolioId}
                className={`rounded-2xl px-4 py-2.5 text-sm font-medium transition-colors ${
                  running
                    ? "cursor-wait bg-blue-500/15 text-blue-700"
                    : "bg-slate-950 text-white hover:bg-slate-800"
                }`}
              >
                {running ? "运行中..." : "手动运行主脑"}
              </button>
              <button
                onClick={() => handleRunTrainingSuite("smoke")}
                disabled={suiteRunningMode !== null}
                className="rounded-2xl border border-black/10 bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
              >
                {suiteRunningMode === "smoke" ? "Smoke 中..." : "Quick Smoke"}
              </button>
            </div>
          </div>

          <div className="mt-4 inline-flex rounded-2xl border border-black/10 bg-white/70 p-1 text-sm">
            {([
              { id: "pet", label: "宠物" },
              { id: "training", label: "训练" },
              { id: "battle", label: "模拟盘" },
              { id: "backtest", label: "回测" },
            ] as const).map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setPageTab(tab.id)}
                className={`rounded-xl px-4 py-2 transition-colors ${
                  pageTab === tab.id
                    ? "bg-slate-950 text-white"
                    : "text-slate-600 hover:bg-black/5 hover:text-slate-950"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {runError && (
            <div className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-700">
              {runError}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-hidden">
          {!portfolioId ? (
            <div className="flex h-full items-center justify-center p-5">
              <div className="w-full max-w-2xl rounded-[32px] border border-black/10 bg-white/70 p-8 text-center shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
                <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">
                  Portfolio Empty State
                </div>
                <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  请先创建虚拟账户
                </h2>
                <p className="mt-3 text-sm leading-7 text-slate-600">
                  账户建好后，这个宠物就能一边跑虚拟盘，一边继续接受回测训练，不需要再拆成两个模式。
                </p>
                <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={openCreatePortfolioDialog}
                    className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800"
                  >
                    自定义创建
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      const defaultDraft: CreatePortfolioDraft = { id: "paper", mode: "paper", initialCapital: "1000000" };
                      const payloadResult = buildCreatePortfolioPayload(defaultDraft);
                      if (!payloadResult.ok) return;
                      try {
                        await fetch(`${API_BASE}/api/v1/agent/portfolio`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify(payloadResult.value),
                        });
                        window.location.reload();
                      } catch {}
                    }}
                    className="rounded-2xl border border-slate-950 bg-white px-5 py-3 text-sm font-medium text-slate-950 transition hover:bg-slate-50"
                  >
                    一键创建默认账户
                  </button>
                  <span className="text-xs text-slate-400">
                    默认：虚拟盘 + 100 万初始资金
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full overflow-y-auto p-5">
              {pageTab === "pet" && (
                <div className={petWorkspaceLayout.rootClassName}>
                  <div className={petWorkspaceLayout.leftColumnClassName}>
                    <div className="space-y-5">
                      <AgentPetStage
                        viewModel={petConsole}
                        activeRun={activeRun}
                        suiteRunningMode={suiteRunningMode}
                      />
                      <div className="grid gap-5 xl:grid-cols-2">
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
                      </div>
                    </div>

                    <div className="min-h-[340px] flex-1 overflow-hidden rounded-[28px] border border-black/10 bg-[#10141d] p-4 shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
                      <div className="h-full overflow-y-auto pr-1">
                        <StrategyBrainPanel
                          viewModel={strategyBrain}
                          loading={loading}
                          stateError={stateError}
                          memoryLoading={memoryLoading}
                          memoryError={memoryError}
                          reflectionLoading={reflectionLoading}
                          reflectionError={reflectionError}
                          strategyHistoryError={strategyHistoryError}
                        />
                      </div>
                    </div>
                  </div>

                  <div className={petWorkspaceLayout.rightColumnClassName}>
                    <div className="min-h-full overflow-hidden rounded-[28px] border border-black/10 bg-[#090a10] shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
                      <div className="flex h-full min-h-0 flex-col">
                        <div className="border-b border-white/10 px-4 py-3">
                          <div className="inline-flex w-full rounded-xl border border-white/10 bg-white/5 p-1 text-sm">
                            <button
                              type="button"
                              onClick={() => setLeftPanelTab("console")}
                              className={`flex-1 rounded-lg px-3 py-2 transition-colors ${
                                leftPanelTab === "console"
                                  ? "bg-white/15 text-white"
                                  : "text-gray-400 hover:bg-white/10 hover:text-white"
                              }`}
                            >
                              Main Agent Console
                            </button>
                            <button
                              type="button"
                              onClick={() => setLeftPanelTab("memo_inbox")}
                              className={`flex-1 rounded-lg px-3 py-2 transition-colors ${
                                leftPanelTab === "memo_inbox"
                                  ? "bg-white/15 text-white"
                                  : "text-gray-400 hover:bg-white/10 hover:text-white"
                              }`}
                            >
                              Strategy Memo Inbox
                            </button>
                          </div>
                        </div>

                        <div className="min-h-0 flex-1">
                          {leftPanelTab === "console" ? (
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
                              executionActions={executionActions}
                              memoStates={memoStates}
                              onExecutionAction={handleExecutionAction}
                              onSaveMemo={handleSaveMemo}
                            />
                          ) : (
                            <StrategyMemoPanel
                              loading={memoInboxLoading}
                              error={memoInboxError}
                              items={memoInboxItems}
                              mutatingId={memoMutatingId}
                              onArchive={handleArchiveMemo}
                              onDelete={handleDeleteMemo}
                            />
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {pageTab === "training" && (
                <div className="space-y-5">
                  <AgentTrainingPanel
                    runningMode={suiteRunningMode}
                    result={
                      suiteResult && portfolioId
                        ? (suiteResult.requested_portfolio_id ?? suiteResult.portfolio_id) === portfolioId
                          ? suiteResult
                          : null
                        : suiteResult
                    }
                    error={suiteError}
                    onRunDefault={() => handleRunTrainingSuite("default")}
                    onRunSmoke={() => handleRunTrainingSuite("smoke")}
                  />

                  <div className="grid gap-5 xl:grid-cols-2">
                    <ReviewRecordsPanel
                      loading={reviewLoading}
                      error={reviewError}
                      records={filteredReviewRecords}
                      stats={reviewStats}
                      weeklySummaries={weeklySummaries}
                      reviewType={reviewType}
                      onReviewTypeChange={setReviewType}
                    />
                    <MemoryRulesPanel
                      loading={memoryLoading}
                      error={memoryError}
                      rules={filteredMemoryRules}
                      statusFilter={memoryStatus}
                      onStatusFilterChange={setMemoryStatus}
                    />
                    <ReflectionFeedPanel
                      loading={reflectionLoading}
                      error={reflectionError}
                      items={reflectionFeed}
                    />
                    <StrategyHistoryPanel
                      loading={reflectionLoading}
                      error={strategyHistoryError}
                      items={strategyHistory}
                    />
                    <WatchSignalsPanel
                      loading={wakeLoading}
                      error={watchSignalsError}
                      mutationError={wakeMutationError}
                      signals={watchSignals}
                      summary={wakeSummary}
                      form={watchSignalForm}
                      submitting={watchSignalSubmitting}
                      updatingSignalId={watchSignalUpdatingId}
                      onFormChange={handleWatchSignalFormChange}
                      onSubmit={handleCreateWatchSignal}
                      onStatusChange={handleWatchSignalStatusChange}
                    />
                    <InfoDigestsPanel
                      loading={wakeLoading}
                      error={infoDigestsError}
                      items={visibleInfoDigests}
                      mode={wakeDigestMode}
                      selectedRunId={activeRun?.id || null}
                      onModeChange={setWakeDigestMode}
                    />
                  </div>
                </div>
              )}

              {pageTab === "battle" && (
                <div className="grid gap-5 xl:grid-cols-[minmax(300px,0.78fr)_minmax(0,1.22fr)]">
                  <div className="space-y-5">
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
                  </div>
                  <div className="rounded-[28px] border border-black/10 bg-[#10141d] p-4 shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
                    <div className="h-full overflow-y-auto pr-1">
                      <ExecutionLedgerPanel
                        overview={ledgerOverview}
                        loading={loading}
                        error={ledgerError}
                        source={ledgerSource}
                        timeline={equityTimeline}
                        timelineLoading={timelineLoading}
                        timelineError={timelineError}
                        replay={replaySnapshot}
                        replayLoading={replayLoading}
                        replayError={replayError}
                        replayLearning={replayLearning}
                        replayLearningLoading={replayLearningLoading}
                        replayLearningError={replayLearningError}
                        replayDate={replayDate}
                        replayMinDate={equityTimeline?.start_date ?? null}
                        replayMaxDate={equityTimeline?.end_date ?? null}
                        onReplayDateChange={handleReplayDateChange}
                      />
                    </div>
                  </div>
                </div>
              )}

              {pageTab === "backtest" && (
                <div className="space-y-5">
                  <section className="rounded-[28px] border border-black/10 bg-white/80 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.12)]">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.25em] text-slate-500">Backtest Lab</div>
                        <h2 className="mt-2 text-2xl font-semibold text-slate-950">历史回测实验台</h2>
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          把当前 portfolio 丢进历史区间里重放，观察收益、回撤和每日证据。
                        </p>
                      </div>

                      <div className="flex flex-wrap items-end gap-3">
                        <label className="space-y-1 text-xs text-slate-500">
                          <span>开始日期</span>
                          <input
                            type="date"
                            value={backtestStartDate}
                            onChange={(event) => setBacktestStartDate(event.target.value)}
                            className="rounded-xl border border-black/10 bg-white px-3 py-2 text-sm text-slate-950"
                          />
                        </label>
                        <label className="space-y-1 text-xs text-slate-500">
                          <span>结束日期</span>
                          <input
                            type="date"
                            value={backtestEndDate}
                            onChange={(event) => setBacktestEndDate(event.target.value)}
                            className="rounded-xl border border-black/10 bg-white px-3 py-2 text-sm text-slate-950"
                          />
                        </label>
                        <button
                          type="button"
                          onClick={handleRunBacktest}
                          disabled={backtestRunning || !portfolioId}
                          className="rounded-2xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-60"
                        >
                          {backtestRunning ? "回测中..." : "运行回测"}
                        </button>
                      </div>
                    </div>

                    {backtestError && (
                      <div className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-700">
                        {backtestError}
                      </div>
                    )}
                  </section>

                  {backtestSummary ? (
                    <section className="rounded-[28px] border border-black/10 bg-[#111827] p-5 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)]">
                      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs text-slate-400">Run</div>
                          <div className="mt-2 font-mono text-sm">{backtestSummary.run_id}</div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs text-slate-400">状态</div>
                          <div className="mt-2 text-sm">{backtestSummary.status}</div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs text-slate-400">总收益</div>
                          <div className="mt-2 text-sm">{backtestSummary.total_return ?? "--"}</div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs text-slate-400">最大回撤</div>
                          <div className="mt-2 text-sm">{backtestSummary.max_drawdown ?? "--"}</div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs text-slate-400">交易 / 复盘</div>
                          <div className="mt-2 text-sm">
                            {backtestSummary.trade_count ?? "--"} / {backtestSummary.review_count ?? "--"}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs text-slate-400">Memory 变化</div>
                          <div className="mt-2 text-sm">
                            {backtestSummary.memory_added ?? 0}/{backtestSummary.memory_updated ?? 0}/{backtestSummary.memory_retired ?? 0}
                          </div>
                        </div>
                      </div>
                    </section>
                  ) : (
                    <section className="rounded-[28px] border border-dashed border-black/10 bg-white/70 p-5 text-sm text-slate-500">
                      还没有回测结果。先运行一次 backtest，结果会在这里展示。
                    </section>
                  )}

                  <section className="rounded-[28px] border border-black/10 bg-white/80 p-5 shadow-[0_20px_70px_rgba(15,23,42,0.12)]">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-950">日级过程</h3>
                      <p className="mt-1 text-sm text-slate-500">
                        展示回测期间每天是否产生 review 和 memory 变化。
                      </p>
                    </div>

                    <div className="mt-4 space-y-3">
                      {backtestDays.length === 0 ? (
                        <div className="rounded-2xl border border-dashed border-black/10 bg-white/60 p-4 text-sm text-slate-500">
                          暂无 backtest day 记录
                        </div>
                      ) : (
                        backtestDays.map((day) => (
                          <div
                            key={`${day.run_id}-${day.trade_date}`}
                            className="rounded-2xl border border-black/10 bg-white p-4"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div className="font-mono text-sm text-slate-950">{day.trade_date}</div>
                              <div className="flex flex-wrap gap-2 text-xs text-slate-600">
                                <span className="rounded-full border border-black/10 bg-slate-50 px-2.5 py-1">
                                  review {day.review_created ? "yes" : "no"}
                                </span>
                                <span className="rounded-full border border-black/10 bg-slate-50 px-2.5 py-1">
                                  brain {day.brain_run_id ? day.brain_run_id.slice(0, 8) : "--"}
                                </span>
                              </div>
                            </div>
                            <div className="mt-2 text-xs text-slate-500">
                              memory delta: {day.memory_delta ? JSON.stringify(day.memory_delta) : "{}"}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </section>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {portfolioDialogOpen && (
        <CreatePortfolioDialog
          draft={portfolioDraft}
          error={portfolioCreateError}
          submitting={portfolioCreateSubmitting}
          onChange={setPortfolioDraft}
          onClose={closeCreatePortfolioDialog}
          onSubmit={handleCreatePortfolio}
        />
      )}
    </div>
  );
}
