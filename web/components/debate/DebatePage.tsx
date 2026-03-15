"use client";

import { useState } from "react";
import { useDebateStore } from "@/stores/useDebateStore";
import BullBearArena from "./BullBearArena";
import InputBar from "./InputBar";
import HistoryModal from "./HistoryModal";
import JudgeVerdictOverlay from "./JudgeVerdictOverlay";

export default function DebatePage() {
  const {
    status, transcript, observerState, roleState,
    judgeVerdict, isReplayMode, error,
    startDebate, loadReplay, reset,
  } = useDebateStore();

  const [showHistory, setShowHistory] = useState(false);
  const [showVerdict, setShowVerdict] = useState(true);

  // 收到新裁决时自动展示
  const prevVerdictRef = useState<string | null>(null);
  if (judgeVerdict && judgeVerdict.debate_id !== prevVerdictRef[0]) {
    prevVerdictRef[0] = judgeVerdict.debate_id;
    if (!isReplayMode) setShowVerdict(true);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden gap-3">
      {/* 错误提示 */}
      {error && (
        <div className="px-5 py-3 bg-red-500/10 border-b border-red-500/20 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* 主体：多头/发言流/空头 — flex-1 撑满剩余空间 */}
      <BullBearArena
        transcript={transcript}
        roleState={roleState}
        verdict={isReplayMode ? judgeVerdict : null}
        observerState={observerState}
      />

      {/* 输入栏 — 始终在底部 */}
      <InputBar
        status={status}
        isReplayMode={isReplayMode}
        onStart={startDebate}
        onHistoryOpen={() => setShowHistory(true)}
      />

      {/* 实时模式：裁判揭幕动画（全屏遮罩） */}
      {!isReplayMode && judgeVerdict && showVerdict && (
        <JudgeVerdictOverlay
          verdict={judgeVerdict}
          isReplay={false}
          onClose={() => setShowVerdict(false)}
        />
      )}

      {/* 历史弹窗 */}
      {showHistory && (
        <HistoryModal
          onClose={() => setShowHistory(false)}
          onSelect={loadReplay}
          onNew={() => { reset(); setShowHistory(false); }}
        />
      )}
    </div>
  );
}
