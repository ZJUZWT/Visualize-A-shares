"use client";

import { useEffect, useRef } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import { MessageBubble } from "./MessageBubble";
import { BrainCircuit } from "lucide-react";

export function ChatArea() {
  const { messages } = useExpertStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      {messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full gap-4 select-none">
          <div className="w-12 h-12 rounded-2xl bg-[var(--accent-light)] flex items-center justify-center">
            <BrainCircuit size={24} className="text-[var(--accent)]" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-[var(--text-primary)]">投资专家</p>
            <p className="text-xs text-[var(--text-tertiary)] mt-1 max-w-xs leading-relaxed">
              有自己世界观、会主动查资料、能被你说服的 A 股投资顾问
            </p>
          </div>
          <div className="flex flex-wrap gap-2 justify-center mt-2">
            {["宁德时代近期走势如何？", "A股政策面有什么变化？", "新能源板块值得关注吗？"].map(q => (
              <SuggestChip key={q} text={q} />
            ))}
          </div>
        </div>
      ) : (
        <>
          {messages.map(msg => <MessageBubble key={msg.id} message={msg} />)}
          <div ref={bottomRef} />
        </>
      )}
    </div>
  );
}

function SuggestChip({ text }: { text: string }) {
  const { sendMessage, status } = useExpertStore();
  return (
    <button
      onClick={() => status === "idle" && sendMessage(text)}
      className="px-3 py-1.5 text-xs text-[var(--text-secondary)] border border-[var(--border)]
                 rounded-full hover:border-[var(--accent)] hover:text-[var(--accent)]
                 hover:bg-[var(--accent-light)] transition-all duration-150"
    >
      {text}
    </button>
  );
}
