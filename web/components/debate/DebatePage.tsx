"use client";

import { useState, useEffect, useRef } from "react";
import { useDebateStore } from "@/stores/useDebateStore";
import { exportDebateHtml } from "@/lib/exportDebateHtml";
import BullBearArena from "./BullBearArena";
import InputBar from "./InputBar";
import HistoryModal from "./HistoryModal";
import JudgeVerdictOverlay from "./JudgeVerdictOverlay";
import StopConfirmModal from "./StopConfirmModal";
import SummaryCard from "./SummaryCard";
import type { PartialSummary } from "@/types/debate";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function DebatePage() {
  const {
    status, transcript, roleState, blackboardItems,
    judgeVerdict, isReplayMode, error, currentTarget,
    startDebate, loadReplay, reset, stopDebate,
  } = useDebateStore();

  const [showHistory, setShowHistory] = useState(false);
  const [showVerdict, setShowVerdict] = useState(true);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [partialSummary, setPartialSummary] = useState<PartialSummary | null>(null);

  // 收到新裁决时自动展示
  const prevVerdictRef = useRef<string | null>(null);
  if (judgeVerdict && judgeVerdict.debate_id !== prevVerdictRef.current) {
    prevVerdictRef.current = judgeVerdict.debate_id;
    if (!isReplayMode) setShowVerdict(true);
  }

  // 终止后拉取中途总结
  useEffect(() => {
    if (status !== "stopped" || !currentTarget) return;
    setPartialSummary(null);
    const { transcript } = useDebateStore.getState();
    fetch(`${API_BASE}/api/v1/debate/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: currentTarget, transcript }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setPartialSummary(data as PartialSummary); })
      .catch(() => {});
  }, [status, currentTarget]);

  const handleStopConfirm = () => {
    setShowStopConfirm(false);
    stopDebate();
  };

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
        verdict={judgeVerdict}
        blackboardItems={blackboardItems}
      />

      {/* 中途终止总结 */}
      {status === "stopped" && partialSummary && (
        <SummaryCard summary={partialSummary} />
      )}

      {/* 输入栏 — 始终在底部 */}
      <InputBar
        status={status}
        isReplayMode={isReplayMode}
        onStart={startDebate}
        onHistoryOpen={() => setShowHistory(true)}
        onStop={() => setShowStopConfirm(true)}
        onExport={() => exportDebateHtml(
          currentTarget ?? "",
          transcript,
          blackboardItems,
          judgeVerdict,
        )}
      />

      {/* 终止确认弹窗 */}
      <StopConfirmModal
        open={showStopConfirm}
        onConfirm={handleStopConfirm}
        onCancel={() => setShowStopConfirm(false)}
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
