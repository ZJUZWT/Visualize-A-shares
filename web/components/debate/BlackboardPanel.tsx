"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, ChevronUp, Loader2, Database, TrendingUp, Newspaper } from "lucide-react";
import type { BlackboardItem } from "@/stores/useDebateStore";

const SOURCE_LABEL: Record<string, string> = {
  public: "公用",
  bull_expert: "多头",
  bear_expert: "空头",
};

const SOURCE_COLOR: Record<string, string> = {
  public: "text-[var(--text-tertiary)] bg-[var(--bg-primary)]",
  bull_expert: "text-red-400 bg-red-500/10",
  bear_expert: "text-emerald-400 bg-emerald-500/10",
};

const ENGINE_ICON: Record<string, ReactNode> = {
  data: <Database size={11} />,
  quant: <TrendingUp size={11} />,
  info: <Newspaper size={11} />,
};

function BlackboardItemRow({ item }: { item: BlackboardItem }) {
  const [open, setOpen] = useState(false);
  const isPending = item.status === "pending";
  const isFailed = item.status === "failed";

  return (
    <div className="border-b border-[var(--border)] last:border-0">
      <button
        onClick={() => !isPending && setOpen(v => !v)}
        disabled={isPending}
        className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-[var(--bg-primary)] transition-colors"
      >
        <span className={`text-[10px] font-medium px-2 py-0.5 rounded shrink-0 ${SOURCE_COLOR[item.source] ?? SOURCE_COLOR.public}`}>
          {SOURCE_LABEL[item.source] ?? item.source}
        </span>
        <span className="text-[var(--text-tertiary)] shrink-0">
          {ENGINE_ICON[item.engine] ?? <Database size={11} />}
        </span>
        <span className="text-xs text-[var(--text-secondary)] flex-1 truncate">{item.title}</span>
        {isPending
          ? <Loader2 size={11} className="animate-spin text-[var(--text-tertiary)] shrink-0" />
          : isFailed
          ? <span className="text-red-400 text-[10px] shrink-0">✗</span>
          : item.result_summary
          ? (open ? <ChevronUp size={11} className="text-[var(--text-tertiary)] shrink-0" />
                  : <ChevronDown size={11} className="text-[var(--text-tertiary)] shrink-0" />)
          : <span className="text-emerald-400 text-[10px] shrink-0">✓</span>
        }
      </button>
      {open && item.result_summary && (
        <div className="px-4 pb-3 text-[11px] text-[var(--text-secondary)] leading-relaxed bg-[var(--bg-primary)] border-t border-[var(--border)] whitespace-pre-wrap break-all">
          {item.result_summary}
        </div>
      )}
    </div>
  );
}

export default function BlackboardPanel({ items }: { items: BlackboardItem[] }) {
  return (
    <div className="w-60 shrink-0 flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)] shrink-0">
        <span className="text-xs font-semibold text-[var(--text-secondary)]">黑板</span>
        <span className="text-[10px] text-[var(--text-tertiary)] ml-2">{items.length} 条数据</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[var(--text-tertiary)] text-xs py-8">
            等待数据...
          </div>
        ) : (
          items.map(item => <BlackboardItemRow key={item.id} item={item} />)
        )}
      </div>
    </div>
  );
}
