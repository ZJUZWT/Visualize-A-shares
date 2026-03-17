"use client";

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
  // 资金流强度映射到透明度 0.4 ~ 1.0
  const abs = Math.abs(flow);
  if (abs < 1e6) return 0.5;
  const t = Math.min(abs / 1e9, 1); // 10 亿封顶
  return 0.5 + t * 0.5;
}

export function SectorHeatMap() {
  const { heatmapCells, selectBoard, boards } = useSectorStore();

  if (heatmapCells.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] flex items-center justify-center h-full">
        <span className="text-sm text-[var(--text-tertiary)]">暂无热力图数据</span>
      </div>
    );
  }

  // 计算网格列数
  const cols = Math.min(Math.ceil(Math.sqrt(heatmapCells.length * 1.5)), 12);

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden flex flex-col">
      <div className="px-4 py-2.5 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">板块热力图</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <div
          className="grid gap-1.5"
          style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
        >
          {heatmapCells.map((cell) => {
            const board = boards.find((b) => b.board_code === cell.board_code);
            return (
              <button
                key={cell.board_code}
                className="rounded-lg p-2 text-center transition-transform hover:scale-105 cursor-pointer"
                style={{
                  backgroundColor: pctToColor(cell.pct_chg),
                  opacity: flowOpacity(cell.main_force_net_inflow),
                }}
                onClick={() => board && selectBoard(board)}
                title={`${cell.board_name} ${cell.pct_chg > 0 ? "+" : ""}${cell.pct_chg.toFixed(2)}%`}
              >
                <div className="text-[10px] text-white font-medium truncate leading-tight">
                  {cell.board_name}
                </div>
                <div className="text-[10px] text-white/80 font-mono">
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
