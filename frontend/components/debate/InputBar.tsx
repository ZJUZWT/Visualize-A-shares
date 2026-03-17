"use client";

import { useState } from "react";
import { Clock, Loader2, Download, CalendarDays } from "lucide-react";
import type { DebateStatus } from "@/types/debate";

interface InputBarProps {
  status: DebateStatus;
  isReplayMode: boolean;
  onStart: (target: string, maxRounds: number, mode: string, asOfDate?: string) => void;
  onHistoryOpen: () => void;
  onStop: () => void;
  onExport?: () => void;
}

export default function InputBar({ status, isReplayMode, onStart, onHistoryOpen, onStop, onExport }: InputBarProps) {
  const [target, setTarget] = useState("");
  const [maxRounds, setMaxRounds] = useState(3);
  const [mode, setMode] = useState<"standard" | "fast">("standard");
  const [asOfDate, setAsOfDate] = useState("");

  const busy = status === "debating" || status === "final_round" || status === "judging";
  const stopping = status === "stopped";
  const isBacktest = asOfDate.length > 0;

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] shadow-md px-5 py-3 flex flex-col gap-2">
      {/* 回测模式标识 */}
      {isBacktest && !busy && (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-400">
          <CalendarDays size={14} />
          <span>回测模式 — 数据将回溯到 <strong>{asOfDate}</strong></span>
          <button
            onClick={() => setAsOfDate("")}
            className="ml-auto text-amber-400/60 hover:text-amber-400 transition-colors"
            title="退出回测模式"
          >
            ✕
          </button>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={onHistoryOpen}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-[var(--text-secondary)]
                     hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)] transition-colors shrink-0"
          title="历史辩论"
        >
          <Clock size={18} />
          <span>历史</span>
        </button>

        {!isReplayMode && (
          <>
            <input
              type="text"
              value={target}
              onChange={e => setTarget(e.target.value)}
              placeholder="股票代码 / 板块名 / 宏观主题"
              disabled={busy}
              className="flex-1 h-10 px-4 rounded-lg text-sm bg-[var(--bg-primary)] border border-[var(--border)]
                         text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]
                         focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
            />

            <select
              value={maxRounds}
              onChange={e => setMaxRounds(Number(e.target.value))}
              disabled={busy}
              className="h-10 px-3 rounded-lg text-sm bg-[var(--bg-primary)] border border-[var(--border)]
                         text-[var(--text-primary)] focus:outline-none disabled:opacity-50 shrink-0"
            >
              {[1, 2, 3, 4, 5].map(n => (
                <option key={n} value={n}>{n} 轮</option>
              ))}
            </select>

            <button
              onClick={() => setMode(m => m === "standard" ? "fast" : "standard")}
              disabled={busy}
              className="h-10 px-3 rounded-lg text-xs font-medium border border-[var(--border)]
                         text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]
                         disabled:opacity-50 transition-colors shrink-0"
              title={mode === "fast" ? "快速模式：压缩数据，加速辩论" : "标准模式：完整数据，深度分析"}
            >
              {mode === "fast" ? "⚡ 快速" : "📊 标准"}
            </button>

            {/* 日期选择器：回测模式 */}
            <div className="relative shrink-0">
              <input
                type="date"
                value={asOfDate}
                onChange={e => setAsOfDate(e.target.value)}
                disabled={busy}
                max={new Date().toISOString().split("T")[0]}
                min="2020-01-01"
                className={`h-10 px-3 rounded-lg text-xs bg-[var(--bg-primary)] border
                           focus:outline-none disabled:opacity-50 transition-colors cursor-pointer
                           ${isBacktest
                             ? "border-amber-500/50 text-amber-400"
                             : "border-[var(--border)] text-[var(--text-tertiary)]"}`}
                title="选择历史日期进入回测模式"
              />
            </div>

            {busy ? (
              <button
                onClick={() => { onStop(); }}
                disabled={stopping}
                className="h-10 px-5 rounded-lg text-sm font-medium bg-red-500 text-white
                           hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
                           flex items-center gap-2 transition-opacity shrink-0"
              >
                {stopping ? <><Loader2 size={14} className="animate-spin" />终止中...</> : "终止辩论"}
              </button>
            ) : (
              <button
                onClick={() => { const t = target.trim(); t && onStart(t, maxRounds, mode, asOfDate || undefined); }}
                disabled={!target.trim()}
                className={`h-10 px-5 rounded-lg text-sm font-medium text-white
                           hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                           flex items-center gap-2 transition-opacity shrink-0
                           ${isBacktest ? "bg-amber-600" : "bg-[var(--accent)]"}`}
              >
                {isBacktest ? "🔍 回测辩论" : "开始辩论"}
              </button>
            )}
          </>
        )}

        {status === "completed" && onExport && (
          <button
            onClick={onExport}
            className="h-10 px-4 rounded-lg text-sm font-medium border border-[var(--border)]
                       text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]
                       flex items-center gap-2 transition-colors shrink-0"
            title="导出 HTML"
          >
            <Download size={15} />
            <span>导出</span>
          </button>
        )}
      </div>
    </div>
  );
}
