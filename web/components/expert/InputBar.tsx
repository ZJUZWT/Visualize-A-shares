/**
 * 输入栏组件
 */

import { useState } from "react";
import { useExpertStore } from "@/stores/useExpertStore";

export function InputBar() {
  const [input, setInput] = useState("");
  const { sendMessage, isStreaming, error } = useExpertStore();

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;
    await sendMessage(input);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-gray-200 p-4 bg-white">
      {error && (
        <div className="mb-2 p-2 bg-red-100 text-red-700 text-sm rounded">
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入您的投资问题..."
          disabled={isStreaming}
          className="flex-1 p-2 border border-gray-300 rounded resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          rows={3}
        />
        <button
          onClick={handleSend}
          disabled={isStreaming || !input.trim()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isStreaming ? "发送中..." : "发送"}
        </button>
      </div>
    </div>
  );
}
