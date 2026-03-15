"use client";

import type { RoleState } from "@/types/debate";

interface RoleCardProps {
  role: "bull_expert" | "bear_expert";
  state: RoleState | undefined;
}

const STANCE_LABEL: Record<string, string> = {
  insist: "坚持",
  partial_concede: "部分让步",
  concede: "认输",
};

const STANCE_COLOR: Record<string, string> = {
  insist: "text-[var(--accent)]",
  partial_concede: "text-yellow-500",
  concede: "text-[var(--text-tertiary)]",
};

export default function RoleCard({ role, state }: RoleCardProps) {
  const isBull = role === "bull_expert";
  const color = isBull ? "#EF4444" : "#10B981";
  const label = isBull ? "多头" : "空头";
  const emoji = isBull ? "🐂" : "🐻";
  const conceded = state?.conceded ?? false;

  return (
    <div className={`relative flex flex-col items-center gap-3 p-4 w-52
                     rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)]
                     ${conceded ? "opacity-50" : ""}`}>
      {/* 头像 */}
      <div
        className="w-16 h-16 rounded-full flex items-center justify-center text-3xl"
        style={{ background: `radial-gradient(circle, ${color}33, ${color}88)` }}
      >
        {emoji}
      </div>

      {/* 名称 */}
      <div className="text-sm font-semibold text-[var(--text-primary)]">{label}专家</div>

      {/* Stance */}
      {state?.stance && (
        <span className={`text-xs font-medium ${STANCE_COLOR[state.stance] ?? "text-[var(--text-secondary)]"}`}>
          {STANCE_LABEL[state.stance] ?? state.stance}
        </span>
      )}

      {/* 置信度 */}
      {state && (
        <div className="w-full">
          <div className="flex justify-between text-xs text-[var(--text-tertiary)] mb-1">
            <span>置信度</span>
            <span>{Math.round(state.confidence * 100)}%</span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-[var(--bg-primary)]">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${state.confidence * 100}%`, backgroundColor: color }}
            />
          </div>
        </div>
      )}

      {/* 认输遮罩 */}
      {conceded && (
        <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[var(--bg-primary)]/60">
          <span className="text-2xl">🏳️</span>
        </div>
      )}
    </div>
  );
}
