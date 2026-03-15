"use client";

import { useState, useRef } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import { ArrowUp, Square } from "lucide-react";

export function InputBar() {
  const [input, setInput] = useState("");
  const { sendMessage, status, error } = useExpertStore();
  const isThinking = status === "thinking";
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = async () => {
    if (!input.trim() || isThinking) return;
    const msg = input;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendMessage(msg);
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
    <div className="px-6 pb-5 pt-3 shrink-0">
      {error && (
        <div className="mb-2 px-3 py-2 rounded-lg bg-[var(--red-light)] text-[var(--red-stock)] text-xs">
          {error}
        </div>
      )}
      <div className="flex items-end gap-2 px-4 py-3 rounded-2xl border border-[var(--border)]
                      bg-[var(--bg-secondary)] shadow-[var(--shadow-sm)]
                      focus-within:border-[var(--accent)] focus-within:shadow-[var(--shadow-md)]
                      transition-all duration-150">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="向专家提问… (Enter 发送，Shift+Enter 换行)"
          disabled={isThinking}
          rows={1}
          className="flex-1 bg-transparent text-sm text-[var(--text-primary)]
                     placeholder:text-[var(--text-tertiary)] resize-none outline-none
                     leading-relaxed disabled:opacity-50"
          style={{ minHeight: 24, maxHeight: 160 }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() && !isThinking}
          className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                     transition-all duration-150
                     disabled:opacity-30 disabled:cursor-not-allowed
                     bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white
                     disabled:bg-[var(--border)] disabled:text-[var(--text-tertiary)]"
        >
          {isThinking
            ? <Square size={13} className="fill-current" />
            : <ArrowUp size={15} strokeWidth={2.5} />
          }
        </button>
      </div>
      <p className="text-center text-[10px] text-[var(--text-tertiary)] mt-2">
        专家可能会主动查询行情数据，并在对话中更新自己的认知
      </p>
    </div>
  );
}
