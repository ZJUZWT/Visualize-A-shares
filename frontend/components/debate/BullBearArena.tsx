"use client";

import RoleCard from "./RoleCard";
import TranscriptFeed from "./TranscriptFeed";
import BlackboardPanel from "./BlackboardPanel";
import type { TranscriptItem, BlackboardItem } from "@/stores/useDebateStore";
import type { RoleState, JudgeVerdict } from "@/types/debate";

interface BullBearArenaProps {
  transcript: TranscriptItem[];
  roleState: Record<string, RoleState>;
  verdict: JudgeVerdict | null;
  blackboardItems: BlackboardItem[];
}

export default function BullBearArena({ transcript, roleState, verdict, blackboardItems }: BullBearArenaProps) {
  return (
    <div className="flex flex-1 overflow-hidden gap-3">
      {/* 多头区 */}
      <div className="w-52 shrink-0 flex items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)]">
        <RoleCard role="bull_expert" state={roleState["bull_expert"]} />
      </div>

      {/* 中间发言流 */}
      <div className="flex-1 rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-auto">
        <TranscriptFeed transcript={transcript} verdict={verdict} />
      </div>

      {/* 空头区 */}
      <div className="w-52 shrink-0 flex items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)]">
        <RoleCard role="bear_expert" state={roleState["bear_expert"]} />
      </div>

      {/* 黑板面板 */}
      <BlackboardPanel items={blackboardItems} />
    </div>
  );
}
