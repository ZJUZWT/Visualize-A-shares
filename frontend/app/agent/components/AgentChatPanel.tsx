"use client";

import { useEffect, useRef } from "react";
import {
  AgentChatEntry,
  AgentStrategyActionLookup,
  AgentStrategyActionRequest,
  BrainRun,
  WatchlistItem,
} from "../types";
import AgentChatComposer from "./AgentChatComposer";
import AgentChatMessage from "./AgentChatMessage";

interface AgentChatPanelProps {
  portfolioReady: boolean;
  messages: AgentChatEntry[];
  notices: string[];
  isStreaming: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
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
  strategyActions: AgentStrategyActionLookup;
  onStrategyAction: (request: AgentStrategyActionRequest) => Promise<void>;
}

export default function AgentChatPanel({
  portfolioReady,
  messages,
  notices,
  isStreaming,
  draft,
  onDraftChange,
  onSend,
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
  strategyActions,
  onStrategyAction,
}: AgentChatPanelProps) {
  const tailRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    tailRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isStreaming]);

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#090a10]">
      <div className="border-b border-white/10 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold tracking-[0.18em] text-white uppercase">
              Agent Chat
            </h2>
            <p className="mt-1 text-xs leading-5 text-gray-500">
              对话优先，结构化策略会在消息流里直接出现，可立即采纳或否决。
            </p>
          </div>
          <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-gray-400">
            {portfolioReady ? "Portfolio Ready" : "Portfolio Missing"}
          </span>
        </div>
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
              <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
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
          {messages.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm leading-6 text-gray-500">
              从这里直接跟 Agent 对话。它返回的 `【交易计划】...【/交易计划】` 会被拆成可操作的策略卡片。
            </div>
          ) : (
            messages.map((message) => (
              <AgentChatMessage
                key={message.id}
                message={message}
                strategyActions={strategyActions}
                onStrategyAction={onStrategyAction}
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
