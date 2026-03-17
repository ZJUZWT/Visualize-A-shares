"use client";

import { useSectorStore } from "@/stores/useSectorStore";
import { ConstituentTable } from "./ConstituentTable";
import { SectorTrendChart } from "./SectorTrendChart";
import { X } from "lucide-react";

export function SectorDetailPanel() {
  const { selectedBoard, selectBoard, detailLoading, history, constituents } =
    useSectorStore();

  if (!selectedBoard) return null;

  return (
    <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--bg-secondary)] overflow-hidden">
      {/* 标题栏 */}
      <div className="px-4 py-2.5 border-b border-[var(--border)] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            {selectedBoard.board_name}
          </h2>
          <span
            className="text-xs font-mono"
            style={{ color: selectedBoard.pct_chg >= 0 ? "#ef4444" : "#22c55e" }}
          >
            {selectedBoard.pct_chg >= 0 ? "+" : ""}
            {selectedBoard.pct_chg.toFixed(2)}%
          </span>
          <span className="text-[10px] text-[var(--text-tertiary)]">
            {selectedBoard.board_code}
          </span>
        </div>
        <button
          onClick={() => selectBoard(null)}
          className="p-1 rounded hover:bg-[var(--bg-primary)] text-[var(--text-tertiary)]"
        >
          <X size={14} />
        </button>
      </div>

      {detailLoading ? (
        <div className="flex items-center justify-center h-60 text-sm text-[var(--text-tertiary)]">
          加载详情中...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 divide-x divide-[var(--border)]">
          {/* 左：趋势图 */}
          <div className="p-4">
            <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">
              板块趋势 · K线 + 资金流
            </h3>
            <SectorTrendChart />
          </div>

          {/* 右：成分股 */}
          <div className="p-4">
            <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">
              成分股 · {constituents.length} 只
            </h3>
            <ConstituentTable />
          </div>
        </div>
      )}
    </div>
  );
}
