"use client";

import { useState, useRef } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import { ArrowUp, Square, Download, BrainCircuit, MessageSquareMore, FileBarChart } from "lucide-react";

interface InputBarProps {
  onExport?: () => void;
}

export function InputBar({ onExport }: InputBarProps) {
  const [input, setInput] = useState("");
  const {
    sendMessage, stopStreaming, status, error, activeExpert,
    profiles, chatHistories, deepThink, toggleDeepThink,
    useClarification, toggleClarification,
    useTradePlan, toggleTradePlan,
    pendingClarifications,
  } = useExpertStore();
  const isThinking = status === "thinking";
  const pendingClarification = pendingClarifications[activeExpert];
  const isBusy = isThinking || !!pendingClarification;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const profile = profiles.find((p) => p.type === activeExpert);
  const color = profile?.color ?? "#60A5FA";
  const hasMessages = (chatHistories[activeExpert] ?? []).length > 0;

  const handleSend = async () => {
    if (!input.trim() || isBusy) return;
    const msg = input;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendMessage(msg);
  };

  const handleStop = () => {
    stopStreaming();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 输入法正在组合中（如拼音选词、日文假名确认），Enter 交给 IME 处理，不触发发送
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (isThinking) {
        handleStop();
      } else if (!pendingClarification) {
        handleSend();
      }
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  };

  return (
    <div className="px-6 pb-4 pt-2 shrink-0">
      {error && (
        <div className="mb-2 px-3 py-2 rounded-lg bg-red-500/10 text-red-400 text-xs">
          {error}
        </div>
      )}
      <div
        className="flex items-end gap-2 px-4 py-3 rounded-2xl border border-[var(--border)]
                    bg-[var(--bg-secondary)] shadow-[var(--shadow-sm)]
                    focus-within:shadow-[var(--shadow-md)]
                    transition-all duration-150"
        style={
          {
            "--input-focus-color": color,
          } as React.CSSProperties
        }
      >
        {/* 导出按钮 */}
        {hasMessages && !isThinking && onExport && (
          <button
            onClick={onExport}
            className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                       text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]
                       hover:bg-[var(--bg-primary)] transition-all duration-150"
            title="导出对话"
          >
            <Download size={14} />
          </button>
        )}

        {/* 深度思考开关 */}
        <button
          onClick={toggleDeepThink}
          className={`shrink-0 h-8 px-2 rounded-xl flex items-center gap-1 text-[10px] font-medium
                     transition-all duration-150 border
                     ${deepThink
                       ? "border-current bg-current/10 text-opacity-100"
                       : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
                     }`}
          style={deepThink ? { color, borderColor: color + "40", backgroundColor: color + "10" } : undefined}
          title={deepThink ? "深度思考已开启：AI 会多轮查询数据后再回答" : "点击开启深度思考：AI 可以看一步查一步，分析更深入"}
        >
          <BrainCircuit size={13} />
          <span>深度</span>
        </button>

        {/* 澄清开关 */}
        <button
          onClick={toggleClarification}
          className={`shrink-0 h-8 px-2 rounded-xl flex items-center gap-1 text-[10px] font-medium
                     transition-all duration-150 border
                     ${useClarification
                       ? "border-current bg-current/10 text-opacity-100"
                       : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
                     }`}
          style={useClarification ? { color, borderColor: color + "40", backgroundColor: color + "10" } : undefined}
          title={useClarification ? "澄清已开启：AI 会先确认分析方向" : "点击开启澄清：AI 先询问再分析，更精准"}
        >
          <MessageSquareMore size={13} />
          <span>澄清</span>
        </button>

        {/* 策略卡片开关 */}
        <button
          onClick={toggleTradePlan}
          className={`shrink-0 h-8 px-2 rounded-xl flex items-center gap-1 text-[10px] font-medium
                     transition-all duration-150 border
                     ${useTradePlan
                       ? "border-current bg-current/10 text-opacity-100"
                       : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
                     }`}
          style={useTradePlan ? { color, borderColor: color + "40", backgroundColor: color + "10" } : undefined}
          title={useTradePlan ? "策略卡片已开启：AI 会在分析具体股票时生成交易计划" : "点击开启策略卡片：AI 分析具体股票时可生成交易计划"}
        >
          <FileBarChart size={13} />
          <span>策略</span>
        </button>

        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={
            isThinking
              ? "AI 正在思考… 按 Enter 或点击按钮停止"
              : pendingClarification
              ? "请先选择上方的分析方向，然后继续生成"
              : `向${profile?.name ?? "专家"}提问… (Enter 发送，Shift+Enter 换行)`
          }
          rows={1}
          className="flex-1 bg-transparent text-sm text-[var(--text-primary)]
                     placeholder:text-[var(--text-tertiary)] resize-none outline-none
                     leading-relaxed"
          style={{ minHeight: 24, maxHeight: 160 }}
          disabled={!!pendingClarification}
          onFocus={(e) => {
            const parent = e.currentTarget.parentElement;
            if (parent) parent.style.borderColor = color;
          }}
          onBlur={(e) => {
            const parent = e.currentTarget.parentElement;
            if (parent) parent.style.borderColor = "";
          }}
        />

        {/* 思考中：始终显示停止按钮（不管输入框是否有内容） */}
        {isThinking ? (
          <button
            onClick={handleStop}
            className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                       transition-all duration-150 text-white bg-red-500 hover:bg-red-600"
          >
            <Square size={13} className="fill-current" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim() || !!pendingClarification}
            className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                       transition-all duration-150 text-white
                       disabled:opacity-30 disabled:cursor-not-allowed"
            style={{
              backgroundColor: !input.trim() ? "var(--border)" : color,
            }}
          >
            <ArrowUp size={15} strokeWidth={2.5} />
          </button>
        )}
      </div>
      <p className="text-center text-[10px] text-[var(--text-tertiary)] mt-2">
        {pendingClarification && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            请选择一个分析方向
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {deepThink && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            <BrainCircuit size={10} />
            深度思考
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {useClarification && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            <MessageSquareMore size={10} />
            澄清
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {useTradePlan && (
          <span className="inline-flex items-center gap-1 mr-1" style={{ color }}>
            <FileBarChart size={10} />
            策略卡片
            <span className="text-[var(--text-tertiary)]">·</span>
          </span>
        )}
        {activeExpert === "rag"
          ? "投资顾问会主动查询行情数据，并在对话中更新自己的认知"
          : `${profile?.name ?? "专家"}会调用引擎工具获取数据并生成分析`}
      </p>
    </div>
  );
}
