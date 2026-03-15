"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { DebateHistoryItem, DebateSignal } from "@/types/debate";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const SIGNAL_COLOR: Record<DebateSignal, string> = {
  bullish: "#EF4444",
  bearish: "#10B981",
  neutral: "#9CA3AF",
};

const SIGNAL_LABEL: Record<DebateSignal, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
};

const QUALITY_LABEL: Record<string, string> = {
  consensus: "共识",
  strong_disagreement: "强烈分歧",
  one_sided: "一边倒",
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return `${Math.floor(diff / 60000)} 分钟前`;
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

interface HistoryModalProps {
  onClose: () => void;
  onSelect: (debateId: string) => void;
}

export default function HistoryModal({ onClose, onSelect }: HistoryModalProps) {
  const [items, setItems] = useState<DebateHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/debate/history?limit=20`)
      .then(r => r.json())
      .then(data => setItems(data))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
         onClick={onClose}>
      <div className="relative bg-[var(--bg-secondary)] rounded-xl border border-[var(--border)]
                      w-full max-w-md max-h-[60vh] flex flex-col"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <span className="text-sm font-semibold text-[var(--text-primary)]">历史辩论</span>
          <button onClick={onClose} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
            <X size={16} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1">
          {loading && (
            <div className="flex items-center justify-center py-8 text-sm text-[var(--text-tertiary)]">
              加载中...
            </div>
          )}
          {!loading && items.length === 0 && (
            <div className="flex items-center justify-center py-8 text-sm text-[var(--text-tertiary)]">
              暂无辩论记录
            </div>
          )}
          {items.map(item => {
            const signalColor = item.signal ? SIGNAL_COLOR[item.signal] : "#9CA3AF";
            const signalLabel = item.signal ? SIGNAL_LABEL[item.signal] : "未知";
            return (
              <button
                key={item.debate_id}
                onClick={() => { onSelect(item.debate_id); onClose(); }}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[var(--bg-primary)]
                           border-b border-[var(--border)] last:border-0 text-left transition-colors"
              >
                <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: signalColor }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--text-primary)]">{item.target}</span>
                    <span className="text-xs" style={{ color: signalColor }}>{signalLabel}</span>
                    {item.debate_quality && (
                      <span className="text-xs text-[var(--text-tertiary)]">
                        {QUALITY_LABEL[item.debate_quality] ?? item.debate_quality}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-[var(--text-tertiary)] mt-0.5">
                    {relativeTime(item.created_at)} · {item.rounds_completed} 轮
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
