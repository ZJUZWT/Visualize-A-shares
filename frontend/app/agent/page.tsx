"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";

interface BrainRun {
  id: string;
  portfolio_id: string;
  run_type: string;
  status: string;
  candidates: any[] | null;
  analysis_results: any[] | null;
  decisions: any[] | null;
  plan_ids: string[] | null;
  trade_ids: string[] | null;
  error_message: string | null;
  llm_tokens_used: number;
  started_at: string;
  completed_at: string | null;
}

interface WatchlistItem {
  id: string;
  stock_code: string;
  stock_name: string;
  reason: string | null;
  added_by: string;
  created_at: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AgentPage() {
  const [runs, setRuns] = useState<BrainRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BrainRun | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
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
    if (!portfolioId) return;
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/brain/runs?portfolio_id=${portfolioId}`);
      if (resp.ok) {
        const data = await resp.json();
        setRuns(data);
        if (data.length > 0 && !selectedRun) setSelectedRun(data[0]);
      }
    } finally {
      setLoading(false);
    }
  }, [portfolioId]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

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
        const poll = setInterval(async () => {
          const r = await fetch(`${API_BASE}/api/v1/agent/brain/runs/${run.id}`);
          if (r.ok) {
            const updated = await r.json();
            setSelectedRun(updated);
            if (updated.status !== "running") {
              clearInterval(poll);
              setRunning(false);
              fetchRuns();
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

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-white">
      <NavSidebar />
      <div className="flex-1 flex flex-col ml-12">
        {/* 顶部状态栏 */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold">🤖 Agent Brain</h1>
            {selectedRun && (
              <span className={`px-2 py-0.5 rounded text-xs ${statusColor[selectedRun.status] || ""}`}>
                {selectedRun.status === "running" ? "运行中..." : selectedRun.status}
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
            <div className="flex-1 overflow-y-auto">
              <div className="p-3 text-xs text-gray-400 font-medium">运行记录</div>
              {loading ? (
                <div className="text-gray-500 text-center py-4 text-sm">加载中...</div>
              ) : runs.length === 0 ? (
                <div className="text-gray-500 text-center py-4 text-sm">暂无运行记录</div>
              ) : (
                runs.map((run) => (
                  <button
                    key={run.id}
                    onClick={() => setSelectedRun(run)}
                    className={`w-full text-left px-3 py-2 text-sm border-b border-white/5 transition-colors ${
                      selectedRun?.id === run.id ? "bg-white/10" : "hover:bg-white/5"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-gray-300">
                        {new Date(run.started_at).toLocaleDateString()}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-xs ${statusColor[run.status] || ""}`}>
                        {run.status}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {run.run_type === "manual" ? "手动" : "定时"}
                      {run.decisions && ` · ${run.decisions.length} 个决策`}
                    </div>
                  </button>
                ))
              )}
            </div>

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
          <div className="flex-1 overflow-y-auto p-6">
            {!selectedRun ? (
              <div className="text-gray-500 text-center py-20">
                {portfolioId ? "选择一条运行记录查看详情，或点击「手动运行」" : "请先创建虚拟账户"}
              </div>
            ) : (
              <div className="space-y-6">
                <div className="flex items-center gap-4 text-sm text-gray-400">
                  <span>开始: {new Date(selectedRun.started_at).toLocaleString()}</span>
                  {selectedRun.completed_at && (
                    <span>完成: {new Date(selectedRun.completed_at).toLocaleString()}</span>
                  )}
                  {selectedRun.llm_tokens_used > 0 && (
                    <span>Token: {selectedRun.llm_tokens_used}</span>
                  )}
                </div>

                {selectedRun.error_message && (
                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
                    {selectedRun.error_message}
                  </div>
                )}

                {selectedRun.candidates && selectedRun.candidates.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">
                      候选标的 ({selectedRun.candidates.length})
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {selectedRun.candidates.map((c: any, i: number) => (
                        <span key={i} className="px-2 py-1 rounded text-xs bg-white/5 border border-white/10">
                          <span className="font-mono text-white">{c.stock_code}</span>
                          <span className="text-gray-400 ml-1">{c.stock_name}</span>
                          <span className={`ml-1 ${
                            c.source === "position" ? "text-blue-400" :
                            c.source === "watchlist" ? "text-yellow-400" : "text-green-400"
                          }`}>
                            ({c.source})
                          </span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {selectedRun.decisions && selectedRun.decisions.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">
                      决策 ({selectedRun.decisions.length})
                    </h3>
                    <div className="space-y-2">
                      {selectedRun.decisions.map((d: any, i: number) => {
                        const isBuy = d.action === "buy" || d.action === "add";
                        return (
                          <div key={i} className={`rounded-lg border p-3 ${
                            isBuy ? "bg-green-500/5 border-green-500/20" : "bg-red-500/5 border-red-500/20"
                          }`}>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-mono font-bold text-white">{d.stock_code}</span>
                              <span className="text-gray-300">{d.stock_name}</span>
                              <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                                isBuy ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                              }`}>
                                {d.action}
                              </span>
                              {d.confidence && (
                                <span className="text-xs text-gray-500">信心: {(d.confidence * 100).toFixed(0)}%</span>
                              )}
                            </div>
                            <div className="text-sm text-gray-300 grid grid-cols-2 md:grid-cols-4 gap-2">
                              {d.price && <div>价格: <span className="text-white">{d.price}</span></div>}
                              {d.quantity && <div>数量: <span className="text-white">{d.quantity}</span></div>}
                              {d.take_profit && <div>止盈: <span className="text-green-400">{d.take_profit}</span></div>}
                              {d.stop_loss && <div>止损: <span className="text-red-400">{d.stop_loss}</span></div>}
                            </div>
                            {d.reasoning && (
                              <div className="text-xs text-gray-400 mt-1">{d.reasoning}</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {selectedRun.plan_ids && selectedRun.plan_ids.length > 0 && (
                  <div className="text-sm text-gray-400">
                    生成 {selectedRun.plan_ids.length} 个交易计划，
                    执行 {selectedRun.trade_ids?.length || 0} 笔交易
                  </div>
                )}

                {selectedRun.analysis_results && selectedRun.analysis_results.length > 0 && (
                  <details className="group">
                    <summary className="text-sm font-medium text-gray-300 cursor-pointer hover:text-white">
                      分析详情 ({selectedRun.analysis_results.length} 只) ▸
                    </summary>
                    <div className="mt-2 space-y-2 max-h-96 overflow-y-auto">
                      {selectedRun.analysis_results.map((a: any, i: number) => (
                        <div key={i} className="bg-white/5 rounded p-2 text-xs">
                          <div className="font-mono text-white mb-1">{a.stock_code} {a.stock_name}</div>
                          {a.error ? (
                            <div className="text-red-400">{a.error}</div>
                          ) : (
                            <pre className="text-gray-400 whitespace-pre-wrap overflow-hidden max-h-32">
                              {typeof a.daily === "string" ? a.daily.slice(0, 300) : JSON.stringify(a.daily, null, 1)?.slice(0, 300)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
