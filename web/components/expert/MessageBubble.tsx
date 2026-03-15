/**
 * 消息气泡组件 — 含内嵌思考面板
 */

"use client";

import type { ExpertMessage } from "@/types/expert";
import { ThinkingPanel } from "./ThinkingPanel";

interface MessageBubbleProps {
  message: ExpertMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-xs lg:max-w-2xl px-4 py-3 rounded-lg ${
          isUser
            ? "bg-blue-500 text-white rounded-br-none"
            : "bg-gray-100 text-gray-900 rounded-bl-none"
        }`}
      >
        {/* 思考面板（仅专家消息） */}
        {!isUser && <ThinkingPanel thinking={message.thinking} />}

        {/* 正文 */}
        <p className="text-sm whitespace-pre-wrap break-words">
          {message.content}
        </p>

        {/* 流式光标 */}
        {message.isStreaming && (
          <div className="mt-1 flex items-center gap-1">
            <div className="w-1.5 h-1.5 bg-current rounded-full animate-pulse" />
            <span className="text-xs opacity-60">输入中...</span>
          </div>
        )}
      </div>
    </div>
  );
}
