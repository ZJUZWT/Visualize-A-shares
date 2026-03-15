"use client";

import { useState } from "react";
import { useDebateStore } from "@/stores/useDebateStore";
import BullBearArena from "./BullBearArena";
import ObserverBar from "./ObserverBar";
import InputBar from "./InputBar";
import HistoryModal from "./HistoryModal";
import JudgeVerdictOverlay from "./JudgeVerdictOverlay";

export default function DebatePage() {
  const {
    status, transcript, observerState, roleState,
    judgeVerdict, isReplayMode, error,
    startDebate, loadReplay,
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
    <div className="flex flex-col h-full">
      {/* 错误提示 */}
      {error && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* 主体：多头/发言流/空头 */}
      <BullBearArena transcript={transcript} roleState={roleState} />

      {/* 观察员栏 */}
      <ObserverBar observerState={observerState} />

      {/* 输入栏 */}
      <InputBar
        status={status}
        isReplayMode={isReplayMode}
        onStart={startDebate}
        onHistoryOpen={() => setShowHistory(true)}
      />

      {/* 回放模式：静态裁判结果嵌入页面 */}
      {isReplayMode && judgeVerdict && (
        <JudgeVerdictOverlay
          verdict={judgeVerdict}
          isReplay={true}
          onClose={() => {}}
        />
      )}

      {/* 实时模式：裁判揭幕动画 */}
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
        />
      )}
    </div>
  );
}
