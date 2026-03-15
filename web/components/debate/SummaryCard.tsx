"use client";

import type { PartialSummary } from "@/types/debate";

const SIGNAL_COLOR = { bullish: "#EF4444", bearish: "#10B981", neutral: "#9CA3AF" };
const SIGNAL_LABEL = { bullish: "看多", bearish: "看空", neutral: "中性" };

export default function SummaryCard({ summary }: { summary: PartialSummary }) {
  const color = summary.signal ? SIGNAL_COLOR[summary.signal] : "#9CA3AF";
  const label = summary.signal ? SIGNAL_LABEL[summary.signal] : "中性";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden mt-4">
      <div className="h-1.5" style={{ backgroundColor: color }} />
      <div className="px-5 py-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold" style={{ color }}>{label}</span>
          <span className="text-xs text-[var(--text-tertiary)] px-2 py-0.5 rounded-full bg-[var(--bg-primary)]">
            中途终止总结
          </span>
        </div>
        <p className="text-sm text-[var(--text-primary)] leading-relaxed">{summary.summary}</p>
      </div>
    </div>
  );
}
