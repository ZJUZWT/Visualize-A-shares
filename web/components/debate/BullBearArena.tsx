"use client";

import RoleCard from "./RoleCard";
import TranscriptFeed from "./TranscriptFeed";
import type { TranscriptItem } from "@/stores/useDebateStore";
import type { RoleState } from "@/types/debate";

interface BullBearArenaProps {
  transcript: TranscriptItem[];
  roleState: Record<string, RoleState>;
}

export default function BullBearArena({ transcript, roleState }: BullBearArenaProps) {
  return (
    <div className="flex flex-1 overflow-hidden">
      {/* 多头区 */}
      <div className="w-52 shrink-0 flex items-center justify-center p-4 border-r border-[var(--border)]">
        <RoleCard role="bull_expert" state={roleState["bull_expert"]} />
      </div>

      {/* 中间发言流 */}
      <TranscriptFeed transcript={transcript} />

      {/* 空头区 */}
      <div className="w-52 shrink-0 flex items-center justify-center p-4 border-l border-[var(--border)]">
        <RoleCard role="bear_expert" state={roleState["bear_expert"]} />
      </div>
    </div>
  );
}
