"use client";

/**
 * RelatedStocksPanel v3.1 — 关联股票面板
 *
 * 悬停/选中某只股票时，在右下角显示同簇中距离最近的关联股票列表。
 * 点击列表中的股票可直接切换选中。
 */

import { useTerrainStore } from "@/stores/useTerrainStore";
import type { RelatedStock } from "@/types/terrain";

export default function RelatedStocksPanel() {
  const { selectedStock, hoveredStock, terrainData, setSelectedStock } =
    useTerrainStore();

  // 优先显示选中股票的关联，否则显示悬停股票的
  const activeStock = selectedStock || hoveredStock;

  if (
    !activeStock ||
    !activeStock.related_stocks ||
    activeStock.related_stocks.length === 0
  ) {
    return null;
  }

  const related = activeStock.related_stocks;
  const isSelected = !!selectedStock && selectedStock.code === activeStock.code;

  return (
    <div className="overlay fixed bottom-4 right-4 w-[340px] z-20">
      <div className="glass-panel px-4 py-3 max-h-[420px] flex flex-col">
        {/* 标题 */}
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
            🔗 关联股票
          </h3>
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-[var(--text-primary)]">
              {activeStock.name}
            </span>
            <span className="text-[10px] text-[var(--text-tertiary)] font-mono bg-[var(--accent-light)] px-1.5 py-0.5 rounded-full">
              簇 #{activeStock.cluster_id}
            </span>
            {isSelected && (
              <span className="text-[10px] text-[var(--accent)]">📌</span>
            )}
          </div>
        </div>

        {/* 表头 */}
        <div className="flex items-center text-[10px] text-[var(--text-tertiary)] pb-1.5 border-b border-[var(--border)] mb-1">
          <span className="w-[52px]">代码</span>
          <span className="flex-1 min-w-0">名称</span>
          <span className="w-[64px] text-right">行业</span>
          <span className="w-[52px] text-right">涨跌幅</span>
        </div>

        {/* 列表 */}
        <div className="overflow-y-auto flex-1 min-h-0">
          {related.slice(0, 10).map((stock: RelatedStock) => (
            <button
              key={stock.code}
              onClick={() => {
                const fullStock = terrainData?.stocks.find(
                  (s) => s.code === stock.code
                );
                if (fullStock) setSelectedStock(fullStock);
              }}
              className="flex items-center w-full text-xs py-1.5 px-1 rounded-lg hover:bg-gray-50 transition-smooth group"
            >
              <span className="w-[52px] font-mono text-[var(--text-tertiary)] text-[10px] group-hover:text-[var(--accent)]">
                {stock.code}
              </span>
              <span className="flex-1 min-w-0 text-[var(--text-primary)] truncate text-left">
                {stock.name}
              </span>
              <span className="w-[64px] text-right text-[var(--text-secondary)] text-[10px] truncate">
                {stock.industry}
              </span>
              <span
                className={`w-[52px] text-right font-mono font-medium text-[11px] ${
                  stock.pct_chg > 0
                    ? "text-rise"
                    : stock.pct_chg < 0
                    ? "text-fall"
                    : "text-[var(--text-tertiary)]"
                }`}
              >
                {stock.pct_chg > 0 ? "+" : ""}
                {stock.pct_chg.toFixed(2)}%
              </span>
            </button>
          ))}
        </div>

        {/* 底部提示 */}
        <div className="text-[10px] text-[var(--text-tertiary)] mt-2 pt-1.5 border-t border-[var(--border)]">
          共 {related.length} 只关联股票 · 按空间距离排序 · 点击切换
        </div>
      </div>
    </div>
  );
}
