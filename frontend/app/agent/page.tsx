"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import AgentRunFeed from "./components/AgentRunFeed";
import AgentStatePanel from "./components/AgentStatePanel";
import DecisionRunPanel from "./components/DecisionRunPanel";
import ExecutionLedgerPanel from "./components/ExecutionLedgerPanel";
import { BrainRun, WatchlistItem } from "./types";

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
            <AgentRunFeed
              loading={loading}
              runs={runs}
              selectedRunId={selectedRun?.id || null}
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
          <div className="flex-1 overflow-y-auto p-6">
            {!selectedRun ? (
              <div className="text-gray-500 text-center py-20">
                {portfolioId ? "选择一条运行记录查看详情，或点击「手动运行」" : "请先创建虚拟账户"}
              </div>
            ) : (
              <div className="space-y-6">
                <AgentStatePanel run={selectedRun} />
                <DecisionRunPanel run={selectedRun} />
                <ExecutionLedgerPanel run={selectedRun} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
