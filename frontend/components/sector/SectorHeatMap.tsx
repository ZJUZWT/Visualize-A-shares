"use client";

import { useMemo } from "react";
import { useSectorStore } from "@/stores/useSectorStore";

function pctToColor(pct: number): string {
  // 红涨绿跌，强度映射
  const intensity = Math.min(Math.abs(pct) / 5, 1); // 5% 封顶
  if (pct > 0) {
    const r = Math.round(220 + intensity * 35);
    const g = Math.round(50 - intensity * 30);
    const b = Math.round(50 - intensity * 30);
    return `rgb(${r},${g},${b})`;
  } else if (pct < 0) {
    const r = Math.round(30 - intensity * 20);
    const g = Math.round(160 + intensity * 60);
    const b = Math.round(50 - intensity * 20);
    return `rgb(${r},${g},${b})`;
  }
  return "#374151";
}

function flowOpacity(flow: number): number {
  const abs = Math.abs(flow);
  if (abs < 1e6) return 0.5;
  const t = Math.min(abs / 1e9, 1);
  return 0.5 + t * 0.5;
}

export function SectorHeatMap() {
  const { heatmapCells, openPanel, boards } = useSectorStore();

  // 去重（基础名去掉罗马数字后缀）
  const cells = useMemo(() => {
    const seen = new Set<string>();
    return heatmapCells.filter((c) => {
      const base = c.board_name.replace(/[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$/, "").trim();
      if (seen.has(base)) return false;
      seen.add(base);
      return true;
    });
  }, [heatmapCells]);

  if (cells.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] flex items-center justify-center h-full">
        <span className="text-sm text-[var(--text-tertiary)]">暂无热力图数据</span>
      </div>
    );
  }

  const cols = Math.min(Math.ceil(Math.sqrt(cells.length * 1.5)), 12);

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-[var(--border)] shrink-0 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">板块热力图</h2>
        <span className="text-[10px] text-[var(--text-tertiary)]">
          {cells.length} 个板块
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 min-h-0">
        <div
          className="grid gap-1"
          style={{
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          }}
        >
          {cells.map((cell) => {
            const board = boards.find((b) => b.board_code === cell.board_code);
            return (
              <button
                key={cell.board_code}
                className="rounded-md p-1.5 text-center transition-transform hover:scale-105 cursor-pointer overflow-hidden"
                style={{
                  backgroundColor: pctToColor(cell.pct_chg),
                  opacity: flowOpacity(cell.main_force_net_inflow),
                }}
                onClick={() => board && openPanel(board)}
                title={`${cell.board_name} ${cell.pct_chg > 0 ? "+" : ""}${cell.pct_chg.toFixed(2)}%`}
              >
                <div className="text-[9px] text-white font-medium truncate leading-tight">
                  {cell.board_name}
                </div>
                <div className="text-[9px] text-white/80 font-mono">
                  {cell.pct_chg > 0 ? "+" : ""}
                  {cell.pct_chg.toFixed(1)}%
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
