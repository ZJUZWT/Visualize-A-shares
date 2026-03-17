"use client";

import { useState, useRef } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import { ArrowUp, Square } from "lucide-react";

export function InputBar() {
  const [input, setInput] = useState("");
  const { sendMessage, status, error, activeExpert, profiles } = useExpertStore();
  const isThinking = status === "thinking";
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const profile = profiles.find((p) => p.type === activeExpert);
  const color = profile?.color ?? "#60A5FA";

  const handleSend = async () => {
    if (!input.trim()) return;
    const msg = input;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendMessage(msg);
  };

  const handleStop = () => {
    // sendMessage 内部会处理 abort
    useExpertStore.setState({ status: "idle" });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
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
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={`向${profile?.name ?? "专家"}提问… (Enter 发送，Shift+Enter 换行)`}
          rows={1}
          className="flex-1 bg-transparent text-sm text-[var(--text-primary)]
                     placeholder:text-[var(--text-tertiary)] resize-none outline-none
                     leading-relaxed"
          style={{ minHeight: 24, maxHeight: 160 }}
          onFocus={(e) => {
            const parent = e.currentTarget.parentElement;
            if (parent) parent.style.borderColor = color;
          }}
          onBlur={(e) => {
            const parent = e.currentTarget.parentElement;
            if (parent) parent.style.borderColor = "";
          }}
        />

        {/* 思考中：停止按钮 */}
        {isThinking && !input.trim() ? (
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
            disabled={!input.trim()}
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
        {activeExpert === "rag"
          ? "投资顾问会主动查询行情数据，并在对话中更新自己的认知"
          : `${profile?.name ?? "专家"}会调用引擎工具获取数据并生成分析`}
      </p>
    </div>
  );
}
