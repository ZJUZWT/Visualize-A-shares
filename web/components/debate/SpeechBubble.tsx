"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { DebateEntry } from "@/types/debate";

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children }) => <code className="px-1 py-0.5 rounded text-xs bg-black/10 font-mono">{children}</code>,
        h1: ({ children }) => <h1 className="text-base font-bold mb-1">{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mb-1">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mb-1">{children}</h3>,
      }}
    >
      {content}
    </ReactMarkdown>
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
        <div className="max-w-[85%] rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] px-4 py-3">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-xs text-[var(--text-tertiary)]">Round {entry.round}</span>
            <span className="text-xs font-semibold" style={{ color }}>{label}</span>
          </div>
          <div className="text-sm text-[var(--text-primary)] leading-relaxed">
            <MarkdownContent content={entry.argument} />
          </div>
        </div>
      </div>
    );
  }

  // 辩论者：左右对齐
  const bgColor = isBull ? "bg-red-500/5" : "bg-emerald-500/5";
  const borderSide = isBull ? "border-l-2" : "border-r-2";

  return (
    <div className={`flex ${isBull ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-[78%] rounded-xl p-4 ${bgColor} ${borderSide}`}
           style={{ borderColor: color }}>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-[var(--text-tertiary)]">Round {entry.round}</span>
          <span className="text-sm font-semibold" style={{ color }}>{label}</span>
        </div>
        <div className="text-sm text-[var(--text-primary)] leading-7">
          <MarkdownContent content={entry.argument} />
        </div>

        {entry.challenges && entry.challenges.length > 0 && (
          <div className="mt-3">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
            >
              {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              质疑 ({entry.challenges.length})
            </button>
            {expanded && (
              <ul className="mt-2 space-y-2">
                {entry.challenges.map((c, i) => (
                  <li key={i} className="text-sm text-[var(--text-secondary)] pl-3 border-l-2 border-[var(--border)] leading-relaxed">
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
