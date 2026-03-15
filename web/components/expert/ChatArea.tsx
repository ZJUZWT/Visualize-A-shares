/**
 * 聊天区域组件
 */

import { useEffect, useRef } from "react";
import { useExpertStore } from "@/stores/useExpertStore";
import { MessageBubble } from "./MessageBubble";

export function ChatArea() {
  const { messages } = useExpertStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-2">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full text-gray-400">
          <div className="text-center">
            <p className="text-lg font-semibold mb-2">投资专家 Agent</p>
            <p className="text-sm">开始对话，获取专业投资建议</p>
          </div>
        </div>
      ) : (
        <>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </>
      )}
    </div>
  );
}
