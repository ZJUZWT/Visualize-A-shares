"use client";

import { useEffect, useRef } from "react";
import {
  AgentChatEntry,
  AgentChatSession,
  AgentStrategyExecutionLookup,
  AgentStrategyExecutionRequest,
  AgentStrategyMemoLookup,
  AgentStrategyMemoSaveRequest,
  BrainRun,
  WatchlistItem,
} from "../types";
import AgentChatComposer from "./AgentChatComposer";
import AgentChatMessage from "./AgentChatMessage";

interface AgentChatPanelProps {
  portfolioReady: boolean;
  sessions: AgentChatSession[];
  activeSessionId: string | null;
  sessionsLoading: boolean;
  messagesLoading: boolean;
  messages: AgentChatEntry[];
  notices: string[];
  isStreaming: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  runs: BrainRun[];
  selectedRunId: string | null;
  onSelectRun: (run: BrainRun) => void;
  statusColor: Record<string, string>;
  watchlist: WatchlistItem[];
  newCode: string;
  newName: string;
  onNewCodeChange: (value: string) => void;
  onNewNameChange: (value: string) => void;
  onAddWatch: () => void;
  onRemoveWatch: (id: string) => void;
  executionActions: AgentStrategyExecutionLookup;
  memoStates: AgentStrategyMemoLookup;
  onExecutionAction: (request: AgentStrategyExecutionRequest) => Promise<void>;
  onSaveMemo: (request: AgentStrategyMemoSaveRequest) => Promise<void>;
}

function formatSessionLabel(session: AgentChatSession) {
  if (session.title && session.title.trim()) {
    return session.title;
  }
  if (session.updated_at) {
    return new Date(session.updated_at).toLocaleString();
  }
  return session.id;
}

export default function AgentChatPanel({
  portfolioReady,
  sessions,
  activeSessionId,
  sessionsLoading,
  messagesLoading,
  messages,
  notices,
  isStreaming,
  draft,
  onDraftChange,
  onSend,
  onCreateSession,
  onSelectSession,
  runs,
  selectedRunId,
  onSelectRun,
  statusColor,
  watchlist,
  newCode,
  newName,
  onNewCodeChange,
  onNewNameChange,
  onAddWatch,
  onRemoveWatch,
  executionActions,
  memoStates,
  onExecutionAction,
  onSaveMemo,
}: AgentChatPanelProps) {
  const tailRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    tailRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isStreaming, activeSessionId]);

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#090a10]">
      <div className="border-b border-white/10 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold tracking-[0.18em] text-white uppercase">
              Agent Chat
            </h2>
            <p className="mt-1 text-xs leading-5 text-gray-500">
              使用持久化 session 管理对话，刷新后仍可继续当前聊天与策略动作状态。
            </p>
          </div>
          <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-gray-400">
            {portfolioReady ? "Portfolio Ready" : "Portfolio Missing"}
          </span>
        </div>
      </div>

      <div className="border-b border-white/10 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">会话列表</div>
          <button
            type="button"
            onClick={onCreateSession}
            disabled={!portfolioReady || sessionsLoading || isStreaming}
            className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
              portfolioReady && !sessionsLoading && !isStreaming
                ? "bg-white/10 text-white hover:bg-white/20"
                : "cursor-not-allowed bg-white/5 text-gray-500"
            }`}
          >
            新会话
          </button>
        </div>
        {sessionsLoading ? (
          <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-gray-500">
            加载会话中...
          </div>
        ) : sessions.length === 0 ? (
          <div className="mt-3 rounded-xl border border-dashed border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-gray-500">
            还没有持久化会话。点击“新会话”或直接发送第一条消息。
          </div>
        ) : (
          <div className="mt-3 max-h-44 space-y-2 overflow-y-auto pr-1">
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => onSelectSession(session.id)}
                className={`w-full rounded-xl border px-3 py-2 text-left transition-colors ${
                  session.id === activeSessionId
                    ? "border-white/20 bg-white/10"
                    : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
                }`}
              >
                <div className="truncate text-sm text-white">{formatSessionLabel(session)}</div>
                <div className="mt-1 flex items-center justify-between gap-3 text-xs text-gray-500">
                  <span>{session.updated_at ? new Date(session.updated_at).toLocaleString() : "--"}</span>
                  <span>{session.message_count ?? 0} 条消息</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="border-b border-white/10 px-4 py-4">
        <div className="space-y-4">
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-[0.16em] text-gray-500">
              最近运行
            </div>
            {runs.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-gray-500">
                暂无运行记录，手动运行后这里会同步最近的 brain run。
              </div>
            ) : (
              <div className="max-h-40 space-y-2 overflow-y-auto pr-1">
                {runs.map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => onSelectRun(run)}
                    className={`w-full rounded-xl border px-3 py-2 text-left transition-colors ${
                      selectedRunId === run.id
                        ? "border-white/20 bg-white/10"
                        : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm text-white">
                        {new Date(run.started_at).toLocaleString()}
                      </span>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] ${statusColor[run.status] || "bg-white/10 text-gray-300"}`}>
                        {run.status}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {run.run_type === "manual" ? "手动运行" : "定时运行"}
                      {run.decisions ? ` · ${run.decisions.length} 个决策` : ""}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="mb-2 text-[11px] uppercase tracking-[0.16em] text-gray-500">
              关注列表
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="代码"
                value={newCode}
                onChange={(event) => onNewCodeChange(event.target.value)}
                className="w-20 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-white outline-none placeholder:text-gray-600"
              />
              <input
                type="text"
                placeholder="名称"
                value={newName}
                onChange={(event) => onNewNameChange(event.target.value)}
                className="min-w-0 flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-white outline-none placeholder:text-gray-600"
              />
              <button
                type="button"
                onClick={onAddWatch}
                className="rounded-xl bg-white/10 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-white/20"
              >
                添加
              </button>
            </div>
            {watchlist.length === 0 ? (
              <div className="mt-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-gray-500">
                还没有关注标的。
              </div>
            ) : (
              <div className="mt-2 flex flex-wrap gap-2">
                {watchlist.map((item) => (
                  <span
                    key={item.id}
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-gray-300"
                  >
                    <span className="font-mono text-white">{item.stock_code}</span>
                    <span>{item.stock_name}</span>
                    <button
                      type="button"
                      onClick={() => onRemoveWatch(item.id)}
                      className="text-red-300 transition-colors hover:text-red-200"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-4">
          {!activeSessionId && messages.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm leading-6 text-gray-500">
              选一个已有 session，或直接发送消息开始新的持久化对话。
            </div>
          ) : messagesLoading ? (
            <div className="rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-5 text-sm leading-6 text-gray-500">
              加载会话消息中...
            </div>
          ) : messages.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm leading-6 text-gray-500">
              当前 session 还没有消息。直接发送问题，Agent 会把回复和策略卡持久化到这个会话里。
            </div>
          ) : (
            messages.map((message) => (
              <AgentChatMessage
                key={message.id}
                message={message}
                executionActions={executionActions}
                memoStates={memoStates}
                onExecutionAction={onExecutionAction}
                onSaveMemo={onSaveMemo}
              />
            ))
          )}
          <div ref={tailRef} />
        </div>
      </div>

      {notices.length > 0 && (
        <div className="space-y-2 border-t border-white/10 px-4 py-3">
          {notices.map((notice, index) => (
            <div
              key={`${notice}-${index}`}
              className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200"
            >
              {notice}
            </div>
          ))}
        </div>
      )}

      <AgentChatComposer
        value={draft}
        disabled={!portfolioReady}
        isStreaming={isStreaming}
        onChange={onDraftChange}
        onSubmit={onSend}
      />
    </section>
  );
}
