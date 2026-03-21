"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import AgentRunFeed from "./components/AgentRunFeed";
import AgentStatePanel from "./components/AgentStatePanel";
import DecisionRunPanel from "./components/DecisionRunPanel";
import ExecutionLedgerPanel from "./components/ExecutionLedgerPanel";
import ReviewRecordsPanel from "./components/ReviewRecordsPanel";
import MemoryRulesPanel from "./components/MemoryRulesPanel";
import {
  AgentConsoleTab,
  AgentState,
  BrainRun,
  LedgerOverview,
  MemoryRule,
  ReviewRecord,
  ReviewStats,
  WeeklySummary,
  WatchlistItem,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

function buildLedgerFallback(portfolioId: string, portfolio: unknown, plans: unknown, trades: unknown): LedgerOverview {
  const portfolioData = isRecord(portfolio) ? portfolio : {};
  const config = isRecord(portfolioData.config) ? portfolioData.config : {};
  const positions = Array.isArray(portfolioData.positions) ? portfolioData.positions : [];
  const planList = Array.isArray(plans) ? plans : [];
  const tradeList = Array.isArray(trades) ? trades : [];
  const pendingPlans = planList.filter((plan) => isRecord(plan) && plan.status !== "completed" && plan.status !== "expired");

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
      pnl_pct: toNumber(data.pnl_pct),
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
  const average = (values: number[]) => (values.length === 0 ? null : values.reduce((sum, value) => sum + value, 0) / values.length);

  return {
    total_win_rate:
      toNumber(data.total_win_rate)
      ?? toNumber(data.win_rate)
      ?? (totalReviews > 0 ? (winCount / totalReviews) * 100 : null),
    total_pnl_pct:
      toNumber(data.total_pnl_pct)
      ?? average(records.map((record) => record.pnl_pct).filter((value): value is number => value !== null && value !== undefined)),
    weekly_win_rate:
      toNumber(data.weekly_win_rate)
      ?? (weeklyRecords.length > 0 ? (weeklyWinCount / weeklyRecords.length) * 100 : null),
    weekly_pnl_pct:
      toNumber(data.weekly_pnl_pct)
      ?? average(weeklyRecords.map((record) => record.pnl_pct).filter((value): value is number => value !== null && value !== undefined)),
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
      win_rate: toNumber(data.win_rate),
      total_pnl_pct: toNumber(data.total_pnl_pct),
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

export default function AgentPage() {
  const [runs, setRuns] = useState<BrainRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BrainRun | null>(null);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [ledgerOverview, setLedgerOverview] = useState<LedgerOverview | null>(null);
  const [reviewRecords, setReviewRecords] = useState<ReviewRecord[]>([]);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [weeklySummaries, setWeeklySummaries] = useState<WeeklySummary[]>([]);
  const [memoryRules, setMemoryRules] = useState<MemoryRule[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [stateError, setStateError] = useState<string | null>(null);
  const [ledgerError, setLedgerError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [ledgerSource, setLedgerSource] = useState<"overview" | "fallback" | "unavailable" | null>(null);
  const [activeTab, setActiveTab] = useState<AgentConsoleTab>("runs");
  const [reviewType, setReviewType] = useState<"all" | "daily" | "weekly">("all");
  const [memoryStatus, setMemoryStatus] = useState<"all" | "active" | "retired">("all");
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/agent/portfolio`)
      .then((r) => r.json())
      .then((data) => {
        if (data.length > 0) setPortfolioId(data[0].id);
      })
      .catch(() => {});
  }, []);

  const fetchRuns = useCallback(async () => {
    if (!portfolioId) {
      return [];
    }
    const data = await fetchJson<BrainRun[]>(`${API_BASE}/api/v1/agent/brain/runs?portfolio_id=${portfolioId}`);
    setRuns(data);
    setSelectedRun((current) => {
      if (data.length === 0) {
        return null;
      }
      if (!current) {
        return data[0];
      }
      const matched = data.find((run) => run.id === current.id);
      return matched || data[0];
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
      const data = await fetchJson<unknown>(`${API_BASE}/api/v1/agent/ledger/overview?portfolio_id=${portfolioId}`);
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
        setLedgerError("执行台账暂不可用，`ledger/overview` 尚未就绪且 fallback 读取失败。");
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
          `${API_BASE}/api/v1/agent/review/records?portfolio_id=${portfolioId}`,
          `${API_BASE}/api/v1/agent/reviews?days=30`,
        ]),
        fetchFirstAvailable<unknown>([
          `${API_BASE}/api/v1/agent/review/stats?portfolio_id=${portfolioId}`,
          `${API_BASE}/api/v1/agent/reviews/stats?days=30`,
        ]),
        fetchFirstAvailable<unknown>([
          `${API_BASE}/api/v1/agent/review/weekly?portfolio_id=${portfolioId}&limit=10`,
          `${API_BASE}/api/v1/agent/reviews/weekly?limit=10`,
        ]),
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
      setReviewError("复盘读接口暂不可用，review records / stats / weekly summaries 尚未就绪。");
    } finally {
      setReviewLoading(false);
    }
  }, [portfolioId]);

  const fetchMemoryData = useCallback(async () => {
    setMemoryLoading(true);
    try {
      const raw = await fetchFirstAvailable<unknown>([
        `${API_BASE}/api/v1/agent/review/memories`,
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

  const fetchWatchlist = useCallback(async () => {
    const resp = await fetch(`${API_BASE}/api/v1/agent/watchlist`);
    if (resp.ok) setWatchlist(await resp.json());
  }, []);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  const handleRun = async () => {
    if (!portfolioId || running) return;
    setRunning(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/brain/run?portfolio_id=${portfolioId}`, {
        method: "POST",
      });
      if (resp.ok) {
        const run = await resp.json();
        setSelectedRun(run);
        setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
        const poll = setInterval(async () => {
          const r = await fetch(`${API_BASE}/api/v1/agent/brain/runs/${run.id}`);
          if (r.ok) {
            const updated = await r.json();
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
          }
        }, 3000);
      }
    } catch {
      setRunning(false);
    }
  };

  const handleAddWatch = async () => {
    if (!newCode.trim()) return;
    await fetch(`${API_BASE}/api/v1/agent/watchlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stock_code: newCode.trim(), stock_name: newName.trim() || newCode.trim() }),
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

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-white">
      <NavSidebar />
      <div className="flex-1 flex flex-col ml-12">
        {/* 顶部状态栏 */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold">🤖 Agent Brain</h1>
            {activeRun && (
              <span className={`px-2 py-0.5 rounded text-xs ${statusColor[activeRun.status] || ""}`}>
                {activeRun.status === "running" ? "运行中..." : activeRun.status}
              </span>
            )}
          </div>
          <button
            onClick={handleRun}
            disabled={running || !portfolioId}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              running
                ? "bg-blue-500/20 text-blue-400 cursor-wait"
                : "bg-white/10 text-white hover:bg-white/20"
            }`}
          >
            {running ? "运行中..." : "▶ 手动运行"}
          </button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* 左侧：运行记录 + 关注列表 */}
          <div className="w-72 border-r border-white/10 flex flex-col">
            <AgentRunFeed
              loading={loading}
              runs={runs}
              selectedRunId={activeRun?.id || null}
              onSelectRun={setSelectedRun}
              statusColor={statusColor}
            />

            {/* 关注列表 */}
            <div className="border-t border-white/10">
              <div className="p-3 text-xs text-gray-400 font-medium">关注列表</div>
              <div className="px-3 pb-2 flex gap-1">
                <input
                  type="text"
                  placeholder="代码"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white w-20"
                />
                <input
                  type="text"
                  placeholder="名称"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white w-20"
                />
                <button onClick={handleAddWatch} className="bg-white/10 rounded px-2 py-1 text-xs hover:bg-white/20">+</button>
              </div>
              <div className="max-h-40 overflow-y-auto">
                {watchlist.map((w) => (
                  <div key={w.id} className="flex items-center justify-between px-3 py-1 text-xs">
                    <span>
                      <span className="font-mono text-white">{w.stock_code}</span>
                      <span className="text-gray-400 ml-1">{w.stock_name}</span>
                    </span>
                    <button onClick={() => handleRemoveWatch(w.id)} className="text-red-400 hover:text-red-300">×</button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 右侧：运行详情 */}
          <div className="flex-1 overflow-hidden">
            {!portfolioId ? (
              <div className="text-gray-500 text-center py-20 w-full">
                请先创建虚拟账户
              </div>
            ) : (
              <div className="grid h-full grid-cols-1 xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
                <div className="overflow-y-auto border-r border-white/10 p-6">
                  <div className="space-y-6">
                    <div className="inline-flex rounded-xl border border-white/10 bg-white/5 p-1 text-sm">
                      {([
                        { key: "runs", label: "运行记录" },
                        { key: "reviews", label: "复盘记录" },
                        { key: "memory", label: "经验规则" },
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
                    ) : (
                      <MemoryRulesPanel
                        loading={memoryLoading}
                        error={memoryError}
                        rules={filteredMemoryRules}
                        statusFilter={memoryStatus}
                        onStatusFilterChange={setMemoryStatus}
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
                  ) : (
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-400">
                      经验规则 tab 为只读规则库视图，不展示执行台账。
                    </div>
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
