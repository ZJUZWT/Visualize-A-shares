"use client";

import { useSectorStore } from "@/stores/useSectorStore";
import { BoardTypeTab } from "./BoardTypeTab";
import { DatePicker } from "./DatePicker";
import { SectorRankTable } from "./SectorRankTable";
import { SectorHeatMap } from "./SectorHeatMap";
import { SectorDetailPanel } from "./SectorDetailPanel";
import { SectorRotationPanel } from "./SectorRotationPanel";
import { RefreshCw } from "lucide-react";

export function SectorDashboard() {
  const { loading, fetchData, selectedBoard } = useSectorStore();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 顶部工具栏 */}
      <div className="px-5 py-3 border-b border-[var(--border)] shrink-0 flex items-center gap-4">
        <h1 className="text-base font-semibold text-[var(--text-primary)]">
          📊 板块研究
        </h1>
        <BoardTypeTab />
        <DatePicker />
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
        {/* 上半区：排行列表 + 热力图 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ minHeight: 400 }}>
          <SectorRankTable />
          <SectorHeatMap />
        </div>

        {/* 中间：板块详情（点击展开） */}
        {selectedBoard && <SectorDetailPanel />}

        {/* 下半区：轮动预测 */}
        <SectorRotationPanel />
      </div>
    </div>
  );
}
