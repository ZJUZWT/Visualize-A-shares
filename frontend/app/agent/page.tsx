"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import AgentRunFeed from "./components/AgentRunFeed";
import AgentStatePanel from "./components/AgentStatePanel";
import DecisionRunPanel from "./components/DecisionRunPanel";
import ExecutionLedgerPanel from "./components/ExecutionLedgerPanel";
import {
  AgentState,
  BrainRun,
  LedgerOverview,
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
  const accountSource = isRecord(data.account)
    ? data.account
    : isRecord(data.summary)
      ? data.summary
      : data;
  const positions = Array.isArray(data.positions) ? data.positions : [];
  const pendingPlans = Array.isArray(data.pending_plans)
    ? data.pending_plans
    : Array.isArray(data.plans)
      ? data.plans
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
      position_count: toNumber(accountSource.position_count) ?? positions.length,
      pending_plan_count: toNumber(accountSource.pending_plan_count) ?? pendingPlans.length,
      trade_count: toNumber(accountSource.trade_count) ?? recentTrades.length,
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

export default function AgentPage() {
  const [runs, setRuns] = useState<BrainRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BrainRun | null>(null);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [ledgerOverview, setLedgerOverview] = useState<LedgerOverview | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [stateError, setStateError] = useState<string | null>(null);
  const [ledgerError, setLedgerError] = useState<string | null>(null);
  const [ledgerSource, setLedgerSource] = useState<"overview" | "fallback" | "unavailable" | null>(null);
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

  useEffect(() => {
    refreshConsole();
  }, [refreshConsole]);

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
                <div className="overflow-y-auto p-6">
                  <ExecutionLedgerPanel
                    overview={ledgerOverview}
                    loading={loading}
                    error={ledgerError}
                    source={ledgerSource}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
