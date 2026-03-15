"use client";

import { useState } from "react";
import type { ObserverState } from "@/types/debate";
import { ChevronDown, ChevronUp } from "lucide-react";

interface ObserverBarProps {
  observerState: Record<string, ObserverState>;
}

export default function ObserverBar({ observerState }: ObserverBarProps) {
  const retail = observerState["retail_investor"];
  const smart = observerState["smart_money"];

  return (
    <div className="h-16 border-t border-[var(--border)] bg-[var(--bg-secondary)] flex items-center px-4 gap-4">
      <RetailCard state={retail} />
      <SmartMoneyCard state={smart} />
    </div>
  );
}

function RetailCard({ state }: { state: ObserverState | undefined }) {
  const [expanded, setExpanded] = useState(false);
  const score = state?.retail_sentiment_score ?? 0;
  const barColor = score >= 0 ? "#EF4444" : "#10B981";
  const barWidth = `${Math.abs(score) * 50}%`;
  const silent = !state?.speak;

  return (
    <div className="flex-1 flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-tertiary)]">散户情绪</span>
        {silent
          ? <span className="text-xs text-[var(--text-tertiary)]">本轮沉默</span>
          : state?.argument && (
            <button onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-0.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">
              {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
              查看
            </button>
          )
        }
      </div>
      {/* 情绪进度条 */}
      <div className="relative w-full h-1.5 rounded-full bg-[var(--bg-primary)]">
        <div className="absolute top-0 bottom-0 w-px bg-[var(--border)]" style={{ left: "50%" }} />
        <div
          className="absolute top-0 h-full rounded-full transition-all duration-500"
          style={{
            width: barWidth,
            backgroundColor: barColor,
            left: score >= 0 ? "50%" : `calc(50% - ${barWidth})`,
          }}
        />
      </div>
      {expanded && state?.argument && (
        <p className="text-xs text-[var(--text-secondary)] line-clamp-2">{state.argument}</p>
      )}
    </div>
  );
}

function SmartMoneyCard({ state }: { state: ObserverState | undefined }) {
  const [expanded, setExpanded] = useState(false);
  const silent = !state?.speak;

  return (
    <div className="flex-1 flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-tertiary)]">主力动向</span>
        {silent
          ? <span className="text-xs text-[var(--text-tertiary)]">本轮沉默</span>
          : state?.argument && (
            <button onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-0.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">
              {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
              查看
            </button>
          )
        }
      </div>
      <div className="h-1.5" />
      {expanded && state?.argument && (
        <p className="text-xs text-[var(--text-secondary)] line-clamp-2">{state.argument}</p>
      )}
    </div>
  );
}
