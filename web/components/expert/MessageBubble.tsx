"use client";

import type { ExpertMessage } from "@/types/expert";
import { ThinkingPanel } from "./ThinkingPanel";

interface MessageBubbleProps {
  message: ExpertMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[72%] px-4 py-2.5 rounded-2xl rounded-br-sm
                        bg-[var(--accent)] text-white text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-3">
      {/* 头像 */}
      <div className="shrink-0 w-7 h-7 rounded-lg bg-[var(--accent-light)]
                      flex items-center justify-center mt-0.5">
        <span className="text-[10px] font-bold text-[var(--accent)]">专</span>
      </div>

      <div className="flex-1 min-w-0 max-w-[80%]">
        {/* 思考面板 */}
        {message.thinking.length > 0 && (
          <ThinkingPanel thinking={message.thinking} />
        )}

        {/* 正文 */}
        <div className="text-sm text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap break-words">
          {message.content}
          {message.isStreaming && (
            <span className="inline-block w-0.5 h-3.5 bg-[var(--accent)] ml-0.5 align-middle animate-pulse" />
          )}
        </div>
      </div>
    </div>
  );
}
