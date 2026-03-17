"use client";

import { useState, useMemo, useCallback } from "react";
import type { ExpertMessage, ExpertProfile } from "@/types/expert";
import { exportChatHtml } from "@/lib/exportChatHtml";
import { X, Download, Check, CheckCheck, RotateCcw } from "lucide-react";

interface ExportChatModalProps {
  messages: ExpertMessage[];
  profile: ExpertProfile;
  sessionTitle?: string;
  onClose: () => void;
}

/**
 * 将消息列表按"轮次"分组：一个 user + 紧跟的 expert 为一轮。
 * 连续的同角色消息也各自成轮（兜底处理）。
 */
function groupIntoRounds(messages: ExpertMessage[]): ExpertMessage[][] {
  const rounds: ExpertMessage[][] = [];
  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];
    if (msg.role === "user") {
      const round: ExpertMessage[] = [msg];
      // 后面连续的 expert 消息都属于同一轮
      while (i + 1 < messages.length && messages[i + 1].role === "expert") {
        i++;
        round.push(messages[i]);
      }
      rounds.push(round);
    } else {
      // 孤立的 expert 消息（如系统消息、错误重试）
      rounds.push([msg]);
    }
    i++;
  }
  return rounds;
}

export function ExportChatModal({
  messages,
  profile,
  sessionTitle,
  onClose,
}: ExportChatModalProps) {
  const rounds = useMemo(() => groupIntoRounds(messages), [messages]);
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(rounds.map((_, i) => i))
  );

  const allSelected = selected.size === rounds.length;
  const noneSelected = selected.size === 0;

  const toggleRound = useCallback((idx: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelected(new Set(rounds.map((_, i) => i)));
  }, [rounds]);

  const deselectAll = useCallback(() => {
    setSelected(new Set());
  }, []);

  const handleExport = useCallback(() => {
    // 按原始顺序收集选中的消息
    const selectedMessages: ExpertMessage[] = [];
    const sortedIndexes = [...selected].sort((a, b) => a - b);
    for (const idx of sortedIndexes) {
      selectedMessages.push(...rounds[idx]);
    }
    exportChatHtml(selectedMessages, profile, sessionTitle);
    onClose();
  }, [selected, rounds, profile, sessionTitle, onClose]);

  /** 截断预览文本 */
  const truncate = (s: string, len: number) =>
    s.length > len ? s.slice(0, len) + "…" : s;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
    >
      <div
        className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-2xl border border-[var(--border)] shadow-2xl"
        style={{ background: "var(--bg-secondary)" }}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)] shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)] flex items-center gap-2">
              <Download size={15} style={{ color: profile.color }} />
              导出对话
            </h2>
            <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">
              勾选要导出的对话轮次，支持选择性导出
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[var(--bg-primary)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* 操作栏 */}
        <div className="flex items-center gap-2 px-5 py-2.5 border-b border-[var(--border)] shrink-0">
          <button
            onClick={allSelected ? deselectAll : selectAll}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium
                       border border-[var(--border)] hover:border-[var(--text-tertiary)]
                       text-[var(--text-secondary)] transition-all duration-150"
          >
            {allSelected ? <RotateCcw size={11} /> : <CheckCheck size={11} />}
            {allSelected ? "取消全选" : "全选"}
          </button>
          <span className="text-[10px] text-[var(--text-tertiary)] ml-auto">
            已选 {selected.size} / {rounds.length} 轮
          </span>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
          {rounds.map((round, idx) => {
            const isSelected = selected.has(idx);
            const userMsg = round.find(m => m.role === "user");
            const expertMsg = round.find(m => m.role === "expert");

            return (
              <button
                key={idx}
                onClick={() => toggleRound(idx)}
                className={`w-full text-left px-3 py-2.5 rounded-xl transition-all duration-150 flex gap-3 items-start group
                  ${isSelected
                    ? "bg-[var(--bg-primary)] border border-[var(--border)]"
                    : "hover:bg-[var(--bg-primary)]/50 border border-transparent"
                  }`}
              >
                {/* 勾选框 */}
                <div
                  className={`shrink-0 w-4.5 h-4.5 mt-0.5 rounded-md flex items-center justify-center transition-all duration-150
                    ${isSelected
                      ? "text-white"
                      : "border border-[var(--border)] group-hover:border-[var(--text-tertiary)]"
                    }`}
                  style={{
                    width: 18, height: 18,
                    backgroundColor: isSelected ? profile.color : "transparent",
                    borderColor: isSelected ? profile.color : undefined,
                  }}
                >
                  {isSelected && <Check size={11} strokeWidth={3} />}
                </div>

                {/* 消息摘要 */}
                <div className="flex-1 min-w-0">
                  {userMsg && (
                    <div className="text-xs text-[var(--text-primary)] font-medium">
                      <span className="text-[var(--text-tertiary)] mr-1.5">Q:</span>
                      {truncate(userMsg.content, 60)}
                    </div>
                  )}
                  {expertMsg && expertMsg.content && (
                    <div className="text-[11px] text-[var(--text-tertiary)] mt-1 line-clamp-2 leading-relaxed">
                      <span className="mr-1.5" style={{ color: profile.color }}>A:</span>
                      {truncate(expertMsg.content.replace(/\n/g, " "), 80)}
                    </div>
                  )}
                  {expertMsg && !expertMsg.content && (
                    <div className="text-[11px] text-[var(--text-tertiary)] mt-1 italic">
                      （无回复内容）
                    </div>
                  )}
                  {!userMsg && expertMsg && (
                    <div className="text-xs text-[var(--text-primary)] font-medium">
                      <span style={{ color: profile.color }}>
                        {profile.icon}
                      </span>{" "}
                      {truncate(expertMsg.content.replace(/\n/g, " "), 80)}
                    </div>
                  )}
                  {/* 思考过程标签 */}
                  {expertMsg && expertMsg.thinking.length > 0 && (
                    <div className="mt-1 flex items-center gap-1">
                      <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-[var(--bg-primary)] text-[var(--text-tertiary)]">
                        🧠 {expertMsg.thinking.length} 项思考过程
                      </span>
                    </div>
                  )}
                </div>

                {/* 轮次标签 */}
                <span className="shrink-0 text-[9px] text-[var(--text-tertiary)] tabular-nums mt-0.5">
                  #{idx + 1}
                </span>
              </button>
            );
          })}
        </div>

        {/* 底部操作栏 */}
        <div className="flex items-center justify-between px-5 py-3.5 border-t border-[var(--border)] shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg text-xs text-[var(--text-secondary)]
                       border border-[var(--border)] hover:bg-[var(--bg-primary)] transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleExport}
            disabled={noneSelected}
            className="px-4 py-1.5 rounded-lg text-xs text-white font-medium
                       transition-all duration-150
                       disabled:opacity-30 disabled:cursor-not-allowed"
            style={{
              backgroundColor: noneSelected ? "var(--border)" : profile.color,
            }}
          >
            <span className="flex items-center gap-1.5">
              <Download size={12} />
              导出 {selected.size} 轮对话
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
