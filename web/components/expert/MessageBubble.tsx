/**
 * 消息气泡组件
 */

import { ExpertMessage } from "@/stores/useExpertStore";

interface MessageBubbleProps {
  message: ExpertMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
    >
      <div
        className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
          isUser
            ? "bg-blue-500 text-white rounded-br-none"
            : "bg-gray-200 text-gray-900 rounded-bl-none"
        }`}
      >
        <p className="text-sm whitespace-pre-wrap break-words">
          {message.content}
        </p>
        {message.isStreaming && (
          <div className="mt-1 flex items-center gap-1">
            <div className="w-1.5 h-1.5 bg-current rounded-full animate-pulse" />
            <span className="text-xs opacity-70">输入中...</span>
          </div>
        )}
      </div>
    </div>
  );
}
