"use client";

/**
 * AI 分析结果面板 — SSE 流式展示 Multi-Agent 分析进度和结果
 */

import { useState, useCallback } from "react";
import { useTerrainStore } from "@/stores/useTerrainStore";
import { Brain, TrendingUp, TrendingDown, Minus, AlertTriangle, Loader2, CheckCircle2, XCircle, X } from "lucide-react";

interface AgentStatus {
  agent: string;
  status: "pending" | "running" | "done" | "failed";
  signal?: string;
  confidence?: number;
  score?: number;
  error?: string;
}

interface AnalysisReport {
  target: string;
  overall_signal: string;
  overall_score: number;
  verdicts: Array<{
    agent_role: string;
    signal: string;
    score: number;
    confidence: number;
    evidence: Array<{ factor: string; value: string; impact: string; weight: number }>;
    risk_flags: string[];
  }>;
  conflicts: string[];
  summary: string;
  risk_level: string;
}

const AGENT_LABELS: Record<string, string> = {
  fundamental: "基本面",
  info: "消息面",
  quant: "技术面",
};

const SIGNAL_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; label: string }> = {
  bullish: { icon: TrendingUp, color: "text-red-500", label: "看多" },
  bearish: { icon: TrendingDown, color: "text-green-500", label: "看空" },
  neutral: { icon: Minus, color: "text-gray-500", label: "中性" },
};

export default function AnalysisPanel() {
  const { selectedStock } = useTerrainStore();
  const [isOpen, setIsOpen] = useState(false);
  const [phase, setPhase] = useState<string>("");
  const [agents, setAgents] = useState<Record<string, AgentStatus>>({
    fundamental: { agent: "fundamental", status: "pending" },
    info: { agent: "info", status: "pending" },
    quant: { agent: "quant", status: "pending" },
  });
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const handleSSEEvent = useCallback((event: string, data: Record<string, unknown>) => {
    if (event === "phase") {
      setPhase(data.step as string);
      if (data.step === "parallel_analysis" && data.status === "running") {
        setAgents((prev) => {
          const next = { ...prev };
          for (const a of (data.agents as string[]) || []) {
            next[a] = { ...next[a], status: "running" };
          }
          return next;
        });
      }
    } else if (event === "agent_done") {
      setAgents((prev) => ({
        ...prev,
        [data.agent as string]: {
          agent: data.agent as string,
          status: data.status === "failed" ? "failed" : "done",
          signal: data.signal as string | undefined,
          confidence: data.confidence as number | undefined,
          score: data.score as number | undefined,
          error: data.error as string | undefined,
        },
      }));
    } else if (event === "result") {
      setReport(data.report as AnalysisReport);
    } else if (event === "error") {
      setError(data.message as string);
    }
  }, []);

  const runAnalysis = useCallback(async () => {
    if (!selectedStock) return;
    setIsRunning(true);
    setIsOpen(true);
    setReport(null);
    setError(null);
    setAgents({
      fundamental: { agent: "fundamental", status: "pending" },
      info: { agent: "info", status: "pending" },
      quant: { agent: "quant", status: "pending" },
    });

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const resp = await fetch(`${apiBase}/api/v1/analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trigger_type: "user",
          target: selectedStock.code,
          target_type: "stock",
          depth: "standard",
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        setError((err as { detail?: string }).detail || "请求失败");
        setIsRunning(false);
        return;
      }

      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ") && eventType) {
            try {
              const data = JSON.parse(line.slice(6));
              handleSSEEvent(eventType, data);
            } catch {
              console.warn("SSE parse error:", line);
            }
            eventType = "";
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "网络错误";
      setError(msg);
    } finally {
      setIsRunning(false);
    }
  }, [selectedStock, handleSSEEvent]);

  const SignalBadge = ({ signal }: { signal: string }) => {
    const cfg = SIGNAL_CONFIG[signal] || SIGNAL_CONFIG.neutral;
    const Icon = cfg.icon;
    return (
      <span className={`inline-flex items-center gap-1 text-xs font-medium ${cfg.color}`}>
        <Icon className="w-3 h-3" /> {cfg.label}
      </span>
    );
  };

  // 触发按钮（选中股票时显示在右上角）
  if (!selectedStock) return null;

  return (
    <>
      {/* 触发按钮 */}
      {!isOpen && (
        <button
          onClick={runAnalysis}
          className="overlay fixed top-16 right-4 z-20 glass-panel px-3 py-2 flex items-center gap-1.5 text-xs font-medium hover:bg-[var(--bg-primary)] transition-colors"
        >
          <Brain className="w-3.5 h-3.5 text-[var(--accent)]" />
          AI 分析 {selectedStock.name}
        </button>
      )}

      {/* 分析面板 */}
      {isOpen && (
        <div className="overlay fixed top-16 right-4 w-[360px] z-20 glass-panel max-h-[calc(100vh-100px)] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-[var(--accent)]" />
              <span className="text-sm font-medium">AI 分析</span>
              <span className="text-xs text-[var(--text-secondary)]">{selectedStock.name || selectedStock.code}</span>
            </div>
            <button onClick={() => setIsOpen(false)} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
            {/* Agent 进度 */}
            {isRunning && (
              <div className="space-y-2">
                {Object.values(agents).map((a) => (
                  <div key={a.agent} className="flex items-center justify-between p-2 rounded-lg bg-[var(--bg-primary)]">
                    <span className="text-xs font-medium">{AGENT_LABELS[a.agent] || a.agent}</span>
                    <div className="flex items-center gap-2">
                      {a.status === "pending" && <span className="text-xs text-[var(--text-tertiary)]">等待中</span>}
                      {a.status === "running" && <Loader2 className="w-3 h-3 animate-spin text-[var(--accent)]" />}
                      {a.status === "done" && (
                        <>
                          <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                          {a.signal && <SignalBadge signal={a.signal} />}
                        </>
                      )}
                      {a.status === "failed" && <XCircle className="w-3 h-3 text-red-400" />}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 结果 */}
            {report && (
              <div className="space-y-3">
                {/* 总评 */}
                <div className="p-3 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium">综合评分</span>
                    <SignalBadge signal={report.overall_signal} />
                  </div>
                  <div className="text-2xl font-bold font-mono">
                    {report.overall_score > 0 ? "+" : ""}{report.overall_score.toFixed(2)}
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] mt-1">{report.summary}</p>
                </div>

                {/* 冲突提示 */}
                {report.conflicts.length > 0 && (
                  <div className="p-2 rounded-lg bg-amber-50 border border-amber-200">
                    <div className="flex items-center gap-1 text-xs text-amber-700 font-medium mb-1">
                      <AlertTriangle className="w-3 h-3" /> 多空分歧
                    </div>
                    {report.conflicts.map((c, i) => (
                      <p key={i} className="text-xs text-amber-600">{c}</p>
                    ))}
                  </div>
                )}

                {/* 各 Agent 详情 */}
                {report.verdicts.map((v) => (
                  <div key={v.agent_role} className="p-3 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium">{AGENT_LABELS[v.agent_role] || v.agent_role}</span>
                      <div className="flex items-center gap-2">
                        <SignalBadge signal={v.signal} />
                        <span className="text-xs text-[var(--text-tertiary)]">{(v.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                    {v.evidence.length > 0 && (
                      <div className="space-y-1 mt-2">
                        {v.evidence.slice(0, 4).map((e, i) => (
                          <div key={i} className="flex items-center justify-between text-xs">
                            <span className="text-[var(--text-secondary)]">{e.factor}</span>
                            <span className={e.impact === "positive" ? "text-red-500" : e.impact === "negative" ? "text-green-500" : "text-gray-400"}>
                              {e.value}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    {v.risk_flags.length > 0 && (
                      <div className="mt-2 text-xs text-amber-600">
                        {v.risk_flags.map((f, i) => <span key={i} className="mr-2">! {f}</span>)}
                      </div>
                    )}
                  </div>
                ))}

                {/* 重新分析 */}
                <button onClick={runAnalysis} className="w-full text-center text-xs py-2 rounded-lg border border-[var(--border)] hover:bg-[var(--bg-primary)] transition-colors">
                  重新分析
                </button>
              </div>
            )}

            {/* 错误 */}
            {error && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-center">
                <p className="text-sm text-red-600 mb-2">{error}</p>
                <button onClick={runAnalysis} className="text-xs py-1 px-3 rounded border border-red-300 hover:bg-red-100 transition-colors">
                  重试
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
