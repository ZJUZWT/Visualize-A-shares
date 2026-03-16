"use client";

import { useState } from "react";
import type { ThinkingItem } from "@/types/expert";
import { ChevronRight, ChevronDown, Network, Wrench, CheckCircle2, Sparkles, Users } from "lucide-react";

interface ThinkingPanelProps {
  thinking: ThinkingItem[];
  color?: string;
}

/** 可折叠的专家回复详情 */
function ExpertReplyDetail({ content, label }: { content: string; label: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!content) return null;

  return (
    <div className="mt-1.5">
      <button
        onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
        className="flex items-center gap-1 text-[10px] text-[var(--accent)] hover:text-[var(--text-secondary)] transition-colors"
      >
        {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        <span>{expanded ? "收起" : "查看"}{label}完整回复</span>
      </button>
      {expanded && (
        <div
          className="mt-1 p-2 rounded-lg bg-[var(--bg-secondary)] text-[11px] text-[var(--text-secondary)]
                      leading-relaxed max-h-[300px] overflow-y-auto whitespace-pre-wrap break-words
                      border border-[var(--border)]"
        >
          {content}
        </div>
      )}
    </div>
  );
}

export function ThinkingPanel({ thinking, color = "var(--accent)" }: ThinkingPanelProps) {
  const [open, setOpen] = useState(false);
  if (thinking.length === 0) return null;

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)]
                   hover:text-[var(--text-secondary)] transition-colors mb-1"
      >
        <ChevronRight
          size={12}
          className={`transition-transform duration-150 ${open ? "rotate-90" : ""}`}
        />
        <span>思考过程</span>
        <span className="px-1.5 py-0.5 rounded-full bg-[var(--bg-primary)] text-[10px]">
          {thinking.length}
        </span>
      </button>

      {open && (
        <div
          className="mb-3 rounded-xl border border-[var(--border)] bg-[var(--bg-primary)]
                      divide-y divide-[var(--border)] overflow-hidden text-xs"
        >
          {thinking.map((item, i) => {
            if (item.type === "graph_recall")
              return (
                <div key={i} className="px-3 py-2 flex gap-2">
                  <Network size={13} className="shrink-0 mt-0.5" style={{ color }} />
                  <div>
                    <span className="font-medium text-[var(--text-secondary)]">图谱召回</span>
                    {!item.nodes || item.nodes.length === 0 ? (
                      <span className="text-[var(--text-tertiary)] ml-1">无相关节点</span>
                    ) : (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {item.nodes.map((n) => (
                          <span
                            key={n.id}
                            className="px-1.5 py-0.5 rounded-md text-[10px]"
                            style={{
                              backgroundColor: color + "15",
                              color,
                            }}
                          >
                            {n.label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );

            if (item.type === "tool_call") {
              const isExpert = item.data.engine === "expert";
              return (
                <div key={i} className="px-3 py-2 flex gap-2">
                  {isExpert ? (
                    <Users size={13} className="text-pink-500 shrink-0 mt-0.5" />
                  ) : (
                    <Wrench size={13} className="text-amber-500 shrink-0 mt-0.5" />
                  )}
                  <div>
                    <span className="font-medium text-[var(--text-secondary)]">
                      {item.data.label || `${item.data.engine}.${item.data.action}`}
                    </span>
                    {isExpert && item.data.params?.question && (
                      <p className="mt-0.5 text-[var(--text-tertiary)] text-[10px] line-clamp-1">
                        &ldquo;{String(item.data.params.question)}&rdquo;
                      </p>
                    )}
                    {!isExpert && (
                      <span className="ml-1.5 font-mono text-[10px] text-[var(--text-tertiary)]">
                        {item.data.engine}.{item.data.action}
                      </span>
                    )}
                  </div>
                </div>
              );
            }

            if (item.type === "tool_result") {
              const isExpert = item.data.engine === "expert";
              return (
                <div key={i} className="px-3 py-2">
                  <div className="flex gap-2">
                    <CheckCircle2 size={13} className={isExpert ? "text-pink-500 shrink-0 mt-0.5" : "text-emerald-500 shrink-0 mt-0.5"} />
                    <div className="flex-1 min-w-0">
                      <span className="font-medium text-[var(--text-secondary)]">
                        {isExpert ? (item.data.label || "专家已回复") : "返回结果"}
                      </span>
                      <p className="mt-0.5 text-[var(--text-tertiary)] leading-relaxed line-clamp-2">
                        {item.data.summary}
                      </p>
                      {/* 专家回复可折叠详情 */}
                      {isExpert && item.data.content && (
                        <ExpertReplyDetail
                          content={item.data.content}
                          label={item.data.label || "专家"}
                        />
                      )}
                    </div>
                  </div>
                </div>
              );
            }

            if (item.type === "belief_updated")
              return (
                <div key={i} className="px-3 py-2 flex gap-2">
                  <Sparkles size={13} className="text-purple-500 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-medium text-[var(--text-secondary)]">信念更新</span>
                    <p className="mt-0.5 text-[var(--text-tertiary)] line-clamp-2">
                      {item.data.new.content}
                    </p>
                  </div>
                </div>
              );

            return null;
          })}
        </div>
      )}
    </div>
  );
}
