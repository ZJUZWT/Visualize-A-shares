"use client";

import type { ExpertMessage } from "@/types/expert";
import { useExpertStore } from "@/stores/useExpertStore";
import { ThinkingPanel } from "./ThinkingPanel";
import { AlertCircle, RotateCw, CheckCircle2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { splitByTradePlan, hasTradePlan } from "@/lib/parseTradePlan";
import TradePlanCard from "@/components/plans/TradePlanCard";
import { API_BASE } from "@/lib/api-base";

interface MessageBubbleProps {
  message: ExpertMessage;
  expertColor: string;
  expertIcon: string;
  expertName: string;
}

function ClarificationCard({
  message,
  expertColor,
}: {
  message: ExpertMessage;
  expertColor: string;
}) {
  const { submitClarification, pendingClarifications, activeExpert } = useExpertStore();
  const item = message.thinking.find((thinking) => thinking.type === "clarification_request");
  if (!item || item.type !== "clarification_request") return null;

  const isPending = item.status === "pending";
  const canSubmit = isPending && !!pendingClarifications[activeExpert];

  return (
    <div className="mb-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
      <div className="flex items-start gap-2">
        <div
          className="mt-0.5 h-6 w-6 shrink-0 rounded-lg flex items-center justify-center text-[11px] text-white"
          style={{ backgroundColor: expertColor }}
        >
          ?
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold text-[var(--text-primary)]">
            先确认分析方向
          </p>
          <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
            {item.data.question_summary}
          </p>
          <div className="mt-3 grid gap-2">
            {item.data.options.map((option) => {
              const selected = item.selectedOption?.option_id === option.id;
              return (
                <button
                  key={option.id}
                  onClick={() =>
                    canSubmit &&
                    submitClarification({
                      option_id: option.id,
                      label: option.label,
                      title: option.title,
                      focus: option.focus,
                      skip: false,
                    })
                  }
                  disabled={!canSubmit}
                  className={`w-full rounded-xl border px-3 py-2.5 text-left transition-all duration-150 ${
                    selected
                      ? "border-transparent text-white"
                      : "border-[var(--border)] hover:border-current"
                  } ${!canSubmit ? "opacity-70 cursor-default" : ""}`}
                  style={selected ? { backgroundColor: expertColor } : undefined}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                        selected ? "bg-white/20" : ""
                      }`}
                      style={selected ? undefined : { backgroundColor: expertColor + "15", color: expertColor }}
                    >
                      {option.label}
                    </span>
                    <span className="text-sm font-medium">{option.title}</span>
                    {selected && <CheckCircle2 size={14} className="ml-auto" />}
                  </div>
                  <p className={`mt-1 text-xs leading-relaxed ${selected ? "text-white/80" : "text-[var(--text-tertiary)]"}`}>
                    {option.description}
                  </p>
                </button>
              );
            })}
          </div>

          <button
            onClick={() =>
              canSubmit &&
              submitClarification({
                option_id: item.data.skip_option.id,
                label: item.data.skip_option.label,
                title: item.data.skip_option.title,
                focus: item.data.skip_option.focus,
                skip: true,
              })
            }
            disabled={!canSubmit}
            className={`mt-3 inline-flex items-center rounded-full border px-3 py-1.5 text-xs transition-colors ${
              !canSubmit ? "opacity-70 cursor-default" : "hover:border-current"
            }`}
            style={{
              borderColor: item.status === "skipped" ? expertColor : undefined,
              color: item.status === "skipped" ? expertColor : undefined,
            }}
          >
            {item.status === "skipped" ? "已选择：跳过，直接分析" : item.data.skip_option.title}
          </button>
        </div>
      </div>
    </div>
  );
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
  const thinkingItems = message.thinking.filter((item) => item.type !== "clarification_request");

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
        {/* 思考面板：历史消息默认折叠，流式消息默认展开 */}
        <ClarificationCard message={message} expertColor={expertColor} />

        {thinkingItems.length > 0 && (
          <ThinkingPanel thinking={thinkingItems} color={expertColor} defaultOpen={message.isStreaming} />
        )}

        {/* 正文 */}
        <div className="text-sm text-[var(--text-primary)] leading-relaxed">
          {message.content ? (
            hasTradePlan(message.content) ? (
              splitByTradePlan(message.content).map((segment, i) =>
                segment.type === "text" ? (
                  <MarkdownContent key={i} content={segment.content} />
                ) : segment.plan ? (
                  <div key={i} className="my-3">
                    <TradePlanCard
                      plan={segment.plan}
                      onSave={async (plan) => {
                        await fetch(`${API_BASE}/api/v1/agent/plans`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify(plan),
                        });
                      }}
                    />
                  </div>
                ) : (
                  <MarkdownContent key={i} content={segment.content} />
                )
              )
            ) : (
              <MarkdownContent content={message.content} />
            )
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
