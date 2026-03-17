"use client";

import type { ExpertMessage } from "@/types/expert";
import { useExpertStore } from "@/stores/useExpertStore";
import { ThinkingPanel } from "./ThinkingPanel";
import { AlertCircle, RotateCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MessageBubbleProps {
  message: ExpertMessage;
  expertColor: string;
  expertIcon: string;
  expertName: string;
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => (
          <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => (
          <strong className="font-semibold text-[var(--text-primary)]">
            {children}
          </strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children }) => (
          <code className="px-1.5 py-0.5 rounded text-xs bg-[var(--bg-primary)] font-mono">
            {children}
          </code>
        ),
        h1: ({ children }) => (
          <h1 className="text-base font-bold mb-2">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-sm font-bold mb-1.5">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-semibold mb-1">{children}</h3>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="text-xs border-collapse w-full">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="border-b border-[var(--border)]">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1 text-left text-[var(--text-secondary)] font-medium">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-2 py-1 text-[var(--text-primary)]">{children}</td>
        ),
        tr: ({ children }) => (
          <tr className="border-b border-[var(--border)] last:border-b-0">{children}</tr>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export function MessageBubble({
  message,
  expertColor,
  expertIcon,
  expertName,
}: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    const isFailed = message.sendStatus === "failed";
    const isPending = message.sendStatus === "pending";
    return (
      <div className="flex justify-end items-end gap-2">
        {/* 发送失败：红色感叹号 + 点击重试 */}
        {isFailed && (
          <button
            onClick={() => useExpertStore.getState().retryMessage(message.id)}
            className="shrink-0 flex items-center gap-1 text-red-500 hover:text-red-400 transition-colors mb-1"
            title="发送失败，点击重试"
          >
            <AlertCircle size={16} />
            <RotateCw size={12} />
          </button>
        )}
        {isPending && (
          <span className="shrink-0 mb-1">
            <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white/80 rounded-full animate-spin" />
          </span>
        )}
        <div
          className={`max-w-[72%] px-4 py-2.5 rounded-2xl rounded-br-sm
                      text-white text-sm leading-relaxed ${isFailed ? "opacity-60" : ""}`}
          style={{ backgroundColor: expertColor }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-3">
      {/* 头像 */}
      <div
        className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5 text-xs"
        style={{ backgroundColor: expertColor + "20" }}
      >
        {expertIcon}
      </div>

      <div className="flex-1 min-w-0 max-w-[80%]">
        {/* 思考面板 */}
        {message.thinking.length > 0 && (
          <ThinkingPanel thinking={message.thinking} color={expertColor} />
        )}

        {/* 正文 */}
        <div className="text-sm text-[var(--text-primary)] leading-relaxed">
          {message.content ? (
            <MarkdownContent content={message.content} />
          ) : message.isStreaming ? (
            <span className="inline-flex items-center gap-1.5 text-[var(--text-tertiary)] text-xs">
              <span className="inline-flex gap-[3px]" style={{ color: expertColor }}>
                <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
              </span>
              正在思考
            </span>
          ) : null}
          {message.isStreaming && message.content && (
            <span
              className="inline-block w-0.5 h-3.5 ml-0.5 align-middle animate-pulse"
              style={{ backgroundColor: expertColor }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
