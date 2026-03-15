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
    <div className={`relative flex flex-col items-center gap-4 p-5 w-full
                     rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)]
                     ${conceded ? "opacity-50" : ""}`}>
      {/* 头像 */}
      <div
        className="w-20 h-20 rounded-full flex items-center justify-center text-4xl"
        style={{ background: `radial-gradient(circle, ${color}33, ${color}88)` }}
      >
        {emoji}
      </div>

      {/* 名称 */}
      <div className="text-base font-semibold text-[var(--text-primary)]">{label}专家</div>

      {/* Stance */}
      {state?.stance && (
        <span className={`text-sm font-medium px-3 py-1 rounded-full bg-[var(--bg-primary)] ${STANCE_COLOR[state.stance] ?? "text-[var(--text-secondary)]"}`}>
          {STANCE_LABEL[state.stance] ?? state.stance}
        </span>
      )}

      {/* 置信度 */}
      {state && (
        <div className="w-full space-y-1.5">
          <div className="flex justify-between text-sm text-[var(--text-tertiary)]">
            <span>置信度</span>
            <span className="font-medium" style={{ color }}>{Math.round(state.confidence * 100)}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-[var(--bg-primary)]">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${state.confidence * 100}%`, backgroundColor: color }}
            />
          </div>
        </div>
      )}

      {/* 认输遮罩 */}
      {conceded && (
        <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-[var(--bg-primary)]/60">
          <span className="text-3xl">🏳️</span>
        </div>
      )}
    </div>
  );
}
