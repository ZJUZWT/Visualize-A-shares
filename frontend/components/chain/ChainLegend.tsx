"use client";

import { IMPACT_COLORS } from "@/types/chain";

const LEGEND_ITEMS = [
  { color: IMPACT_COLORS.source, label: "冲击源 / 中心", shape: "circle" },
  { color: IMPACT_COLORS.benefit, label: "🔴 利好/涨价", shape: "circle" },
  { color: IMPACT_COLORS.hurt, label: "🟢 利空/跌价", shape: "circle" },
  { color: IMPACT_COLORS.neutral, label: "未受冲击", shape: "circle" },
  { color: "#fbbf24", label: "用户设置的冲击", shape: "ring" },
];

const TYPE_LEGEND = [
  { icon: "⚗️", label: "原材料", color: "#64748b" },
  { icon: "🏭", label: "行业", color: "#64748b" },
  { icon: "🏢", label: "公司", color: "#6366f1" },
  { icon: "🌍", label: "宏观因素", color: "#8b5cf6" },
  { icon: "💰", label: "大宗商品", color: "#d97706" },
  { icon: "🚢", label: "物流", color: "#06b6d4" },
];

const EDGE_LEGEND = [
  { color: "rgba(239,68,68,0.5)", style: "solid" as const, width: 2, label: "利好/涨价传导" },
  { color: "rgba(34,197,94,0.5)", style: "solid" as const, width: 2, label: "利空/跌价传导" },
  { color: "rgba(100,116,139,0.3)", style: "solid" as const, width: 1, label: "待冲击" },
  { color: "rgba(148,163,184,0.4)", style: "dashed" as const, width: 1, label: "替代/竞争" },
];

export default function ChainLegend() {
  return (
    <div
      className="absolute top-4 left-4 p-3 rounded-xl border border-[var(--border)] z-10
                 backdrop-blur-md text-xs"
      style={{ background: "rgba(15, 23, 42, 0.8)" }}
    >
      <div className="text-[10px] font-semibold text-[var(--text-secondary)] mb-2">
        冲击状态
      </div>
      <div className="space-y-1.5">
        {LEGEND_ITEMS.map(({ color, label, shape }) => (
          <div key={label} className="flex items-center gap-2">
            {shape === "ring" ? (
              <span
                className="w-3 h-3 rounded-full shrink-0 border-2"
                style={{ borderColor: color }}
              />
            ) : (
              <span
                className="w-3 h-3 rounded-full shrink-0"
                style={{ background: color }}
              />
            )}
            <span className="text-[var(--text-secondary)]">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 pt-2 border-t border-[var(--border)]">
        <div className="text-[10px] font-semibold text-[var(--text-secondary)] mb-1.5">
          节点类型
        </div>
        <div className="space-y-1">
          {TYPE_LEGEND.map(({ icon, label, color }) => (
            <div key={label} className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full shrink-0"
                style={{ background: color }}
              />
              <span className="text-[var(--text-secondary)]">{icon} {label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-2 pt-2 border-t border-[var(--border)] space-y-1.5">
        {EDGE_LEGEND.map(({ color, style, width, label }) => (
          <div key={label} className="flex items-center gap-2">
            <svg width="20" height="8" className="shrink-0">
              <line
                x1="0" y1="4" x2="20" y2="4"
                stroke={color}
                strokeWidth={width}
                strokeDasharray={style === "dashed" ? "3,3" : "none"}
              />
            </svg>
            <span className="text-[var(--text-secondary)]">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
