"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Brain } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DebateEntry } from "@/types/debate";

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1.5">{children}</ol>,
        li: ({ children }) => <li className="leading-6">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children }) => <code className="px-1.5 py-0.5 rounded text-xs bg-[var(--bg-primary)] font-mono">{children}</code>,
        h1: ({ children }) => <h1 className="text-base font-bold mb-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mb-2">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mb-1.5">{children}</h3>,
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

/** 可折叠的思考过程面板 */
function ThinkingBlock({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  if (!content.trim()) return null;
  return (
    <div className="mb-3 rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-primary)]/50">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
      >
        <Brain size={12} className="opacity-60" />
        <span>思考过程</span>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <div className="px-3 pb-3 text-xs text-[var(--text-tertiary)] leading-6 max-h-[300px] overflow-y-auto">
          <MarkdownContent content={content} />
        </div>
      )}
    </div>
  );
}

const ROLE_LABEL: Record<string, string> = {
  bull_expert: "多头专家",
  bear_expert: "空头专家",
  retail_investor: "散户",
  smart_money: "主力",
  judge: "裁判",
};

const ROLE_COLOR: Record<string, string> = {
  bull_expert: "#EF4444",
  bear_expert: "#10B981",
  retail_investor: "#F59E0B",
  smart_money: "#8B5CF6",
  judge: "#6B7280",
};

const STANCE_LABEL: Record<string, string> = {
  insist: "坚持",
  partial_concede: "部分让步",
  concede: "认输",
};

interface SpeechBubbleProps {
  entry: DebateEntry;
}

export default function SpeechBubble({ entry }: SpeechBubbleProps) {
  const [expanded, setExpanded] = useState(false);
  const isObserver = entry.role === "retail_investor" || entry.role === "smart_money";
  const isBull = entry.role === "bull_expert";
  const color = ROLE_COLOR[entry.role] ?? "#9CA3AF";
  const label = ROLE_LABEL[entry.role] ?? entry.role;

  // 观察员：居中气泡
  if (isObserver) {
    if (!entry.speak) return null;
    return (
      <div className="flex justify-center">
        <div className="max-w-[85%] rounded-2xl border border-[var(--border)] bg-[var(--bg-primary)] px-6 py-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs text-[var(--text-tertiary)]">Round {entry.round}</span>
            <span className="text-xs font-semibold" style={{ color }}>{label}</span>
          </div>
          {entry.think_content && <ThinkingBlock content={entry.think_content} />}
          <div className="text-[13px] text-[var(--text-primary)] leading-6">
            <MarkdownContent content={entry.argument} />
          </div>
        </div>
      </div>
    );
  }

  // 辩论者：左右对齐
  const borderSide = isBull ? "border-l-2" : "border-r-2";

  return (
    <div className={`flex ${isBull ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-[78%] rounded-2xl px-6 py-4 bg-[var(--bg-secondary)] ${borderSide}`}
           style={{ borderColor: color }}>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs text-[var(--text-tertiary)]">Round {entry.round}</span>
          <span className="text-[13px] font-semibold" style={{ color }}>{label}</span>
          {entry.stance && entry.stance !== "insist" && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-[var(--bg-primary)] text-[var(--text-tertiary)]">
              {STANCE_LABEL[entry.stance] ?? entry.stance}
            </span>
          )}
          <span className="text-[10px] text-[var(--text-tertiary)] ml-auto">
            置信度 {Math.round(entry.confidence * 100)}%
          </span>
        </div>
        {entry.think_content && <ThinkingBlock content={entry.think_content} />}
        <div className="text-[13px] text-[var(--text-primary)] leading-6">
          <MarkdownContent content={entry.argument} />
        </div>

        {entry.challenges && entry.challenges.length > 0 && (
          <div className="mt-4 pt-3 border-t border-[var(--border)]">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
            >
              {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              质疑 ({entry.challenges.length})
            </button>
            {expanded && (
              <ul className="mt-3 space-y-2.5">
                {entry.challenges.map((c, i) => (
                  <li key={i} className="text-[13px] text-[var(--text-secondary)] pl-4 border-l-2 border-[var(--border)] leading-relaxed">
                    {c}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
