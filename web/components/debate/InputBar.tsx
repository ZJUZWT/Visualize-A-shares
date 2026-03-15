"use client";

import { useState } from "react";
import { Clock, Loader2 } from "lucide-react";
import type { DebateStatus } from "@/types/debate";

interface InputBarProps {
  status: DebateStatus;
  isReplayMode: boolean;
  onStart: (code: string, maxRounds: number) => void;
  onHistoryOpen: () => void;
}

export default function InputBar({ status, isReplayMode, onStart, onHistoryOpen }: InputBarProps) {
  const [code, setCode] = useState("");
  const [maxRounds, setMaxRounds] = useState(3);

  if (isReplayMode) return null;

  const busy = status === "debating" || status === "final_round" || status === "judging";

  return (
    <div className="h-14 border-t border-[var(--border)] bg-[var(--bg-secondary)] flex items-center px-4 gap-3">
      <button
        onClick={onHistoryOpen}
        className="p-2 rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)] transition-colors"
        title="历史辩论"
      >
        <Clock size={16} />
      </button>

      <input
        type="text"
        value={code}
        onChange={e => setCode(e.target.value.trim())}
        placeholder="输入股票代码，如 600519"
        disabled={busy}
        className="flex-1 h-8 px-3 rounded-lg text-sm bg-[var(--bg-primary)] border border-[var(--border)]
                   text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]
                   focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
      />

      <select
        value={maxRounds}
        onChange={e => setMaxRounds(Number(e.target.value))}
        disabled={busy}
        className="h-8 px-2 rounded-lg text-sm bg-[var(--bg-primary)] border border-[var(--border)]
                   text-[var(--text-primary)] focus:outline-none disabled:opacity-50"
      >
        {[1, 2, 3, 4, 5].map(n => (
          <option key={n} value={n}>{n} 轮</option>
        ))}
      </select>

      <button
        onClick={() => code && onStart(code, maxRounds)}
        disabled={busy || !code}
        className="h-8 px-4 rounded-lg text-sm font-medium bg-[var(--accent)] text-white
                   hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                   flex items-center gap-2 transition-opacity"
      >
        {busy ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            辩论进行中...
          </>
        ) : "开始辩论"}
      </button>
    </div>
  );
}
