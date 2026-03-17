"use client";

import { useState } from "react";
import { useSectorStore } from "@/stores/useSectorStore";
import { BoardTypeTab } from "./BoardTypeTab";
import { DatePicker } from "./DatePicker";
import { SectorRankTable } from "./SectorRankTable";
import { SectorHeatMap } from "./SectorHeatMap";
import { SectorDetailPanel } from "./SectorDetailPanel";
import { StockSearchBar } from "./StockSearchBar";
import { RefreshCw } from "lucide-react";

export function SectorDashboard() {
  const { loading, fetchData, selectedBoard, openPanels } = useSectorStore();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 顶部工具栏 */}
      <div className="px-5 py-3 border-b border-[var(--border)] shrink-0 flex items-center gap-4">
        <h1 className="text-base font-semibold text-[var(--text-primary)]">
          📊 板块研究
        </h1>
        <BoardTypeTab />
        <DatePicker />
        <StockSearchBar />
        <button
          onClick={fetchData}
          disabled={loading}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                     bg-[var(--accent)] text-white hover:opacity-90 transition-opacity
                     disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          {loading ? "采集中..." : "采集数据"}
        </button>
      </div>

      {/* 主体 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 上半区：排行列表 + 热力图（固定高度，内部滚动） */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 h-[420px]">
          <SectorRankTable />
          <SectorHeatMap />
        </div>

        {/* 板块详情面板 — 支持多个堆叠 */}
        {openPanels.length > 0 ? (
          openPanels.map((panel) => (
            <SectorDetailPanel
              key={panel.id}
              panelId={panel.id}
              board={panel.board}
              constituents={panel.constituents}
              loading={panel.loading}
            />
          ))
        ) : (
          /* 向后兼容：如果有 selectedBoard 但没有 openPanels */
          selectedBoard && <SectorDetailPanel />
        )}
      </div>
    </div>
  );
}
