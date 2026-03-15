"use client";

import { useState } from "react";
import type { ThinkingItem } from "@/types/expert";
import { ChevronRight, Network, Wrench, CheckCircle2, Sparkles } from "lucide-react";

interface ThinkingPanelProps {
  thinking: ThinkingItem[];
}

export function ThinkingPanel({ thinking }: ThinkingPanelProps) {
  const [open, setOpen] = useState(false);
  if (thinking.length === 0) return null;

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(v => !v)}
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
        <div className="mb-3 rounded-xl border border-[var(--border)] bg-[var(--bg-primary)]
                        divide-y divide-[var(--border)] overflow-hidden text-xs">
          {thinking.map((item, i) => {
            if (item.type === "graph_recall") return (
              <div key={i} className="px-3 py-2 flex gap-2">
                <Network size={13} className="text-[var(--accent)] shrink-0 mt-0.5" />
                <div>
                  <span className="font-medium text-[var(--text-secondary)]">图谱召回</span>
                  {item.nodes.length === 0
                    ? <span className="text-[var(--text-tertiary)] ml-1">无相关节点</span>
                    : <div className="flex flex-wrap gap-1 mt-1">
                        {item.nodes.map(n => (
                          <span key={n.id}
                            className="px-1.5 py-0.5 rounded-md bg-[var(--accent-light)]
                                       text-[var(--accent)] text-[10px]">
                            {n.label}
                          </span>
                        ))}
                      </div>
                  }
                </div>
              </div>
            );

            if (item.type === "tool_call") return (
              <div key={i} className="px-3 py-2 flex gap-2">
                <Wrench size={13} className="text-amber-500 shrink-0 mt-0.5" />
                <div>
                  <span className="font-medium text-[var(--text-secondary)]">调用引擎</span>
                  <span className="ml-1.5 font-mono text-[10px] text-[var(--text-tertiary)]">
                    {item.data.engine}.{item.data.action}
                  </span>
                </div>
              </div>
            );

            if (item.type === "tool_result") return (
              <div key={i} className="px-3 py-2 flex gap-2">
                <CheckCircle2 size={13} className="text-[var(--green-stock)] shrink-0 mt-0.5" />
                <div>
                  <span className="font-medium text-[var(--text-secondary)]">返回结果</span>
                  <p className="mt-0.5 text-[var(--text-tertiary)] leading-relaxed line-clamp-2">
                    {item.data.summary}
                  </p>
                </div>
              </div>
            );

            if (item.type === "belief_updated") return (
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
