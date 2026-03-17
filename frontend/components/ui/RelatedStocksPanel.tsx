"use client";

/**
 * RelatedStocksPanel v4.0 — 关联+相似股票面板
 *
 * v4.0: 新增"跨簇相似"tab，展示全局最近邻（不限同簇）
 */

import { useState } from "react";
import { useTerrainStore } from "@/stores/useTerrainStore";
import { Link as LinkIcon, Pin } from "lucide-react";
import type { RelatedStock, SimilarStock } from "@/types/terrain";

export default function RelatedStocksPanel() {
  const { selectedStock, hoveredStock, terrainData, setSelectedStock } =
    useTerrainStore();
  const [tab, setTab] = useState<"related" | "similar">("related");

  const activeStock = selectedStock || hoveredStock;

  if (!activeStock) return null;

  const related = activeStock.related_stocks || [];
  const similar = activeStock.similar_stocks || [];
  const isSelected = !!selectedStock && selectedStock.code === activeStock.code;

  if (related.length === 0 && similar.length === 0) return null;

  const activeList = tab === "related" ? related : similar;

  return (
    <div className="overlay fixed bottom-4 right-4 w-[340px] z-20">
      <div className="glass-panel px-4 py-3 max-h-[420px] flex flex-col">
        {/* 标题 */}
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider flex items-center gap-1.5">
            <LinkIcon className="w-3.5 h-3.5" /> 关联股票
          </h3>
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-[var(--text-primary)]">
              {activeStock.name}
            </span>
            <span className="text-[10px] text-[var(--text-tertiary)] font-mono bg-[var(--accent-light)] px-1.5 py-0.5 rounded-full">
              {activeStock.cluster_id === -1 ? "离群" : `簇 #${activeStock.cluster_id}`}
            </span>
            {isSelected && (
              <Pin className="w-3 h-3 text-[var(--accent)]" />
            )}
          </div>
        </div>

        {/* Tab 切换 */}
        {similar.length > 0 && (
          <div className="flex gap-1 mb-2">
            <button
              onClick={() => setTab("related")}
              className={`flex-1 text-[10px] py-1 rounded-lg transition-smooth ${
                tab === "related"
                  ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                  : "text-[var(--text-tertiary)] hover:bg-gray-50"
              }`}
            >
              同簇关联 ({related.length})
            </button>
            <button
              onClick={() => setTab("similar")}
              className={`flex-1 text-[10px] py-1 rounded-lg transition-smooth ${
                tab === "similar"
                  ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                  : "text-[var(--text-tertiary)] hover:bg-gray-50"
              }`}
            >
              跨簇相似 ({similar.length})
            </button>
          </div>
        )}

        {/* 表头 */}
        <div className="flex items-center text-[10px] text-[var(--text-tertiary)] pb-1.5 border-b border-[var(--border)] mb-1">
          <span className="w-[52px]">代码</span>
          <span className="flex-1 min-w-0">名称</span>
          {tab === "similar" && <span className="w-[32px] text-right">簇</span>}
          <span className="w-[64px] text-right">行业</span>
          <span className="w-[52px] text-right">涨跌幅</span>
        </div>

        {/* 列表 */}
        <div className="overflow-y-auto flex-1 min-h-0">
          {activeList.slice(0, 10).map((stock: RelatedStock | SimilarStock) => (
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
              {tab === "similar" && "cluster_id" in stock && (
                <span className="w-[32px] text-right text-[10px] font-mono text-[var(--text-tertiary)]">
                  #{(stock as SimilarStock).cluster_id}
                </span>
              )}
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
          {tab === "related"
            ? `共 ${related.length} 只关联股票 · 按空间距离排序 · 点击切换`
            : `共 ${similar.length} 只跨簇相似股 · 按特征距离排序 · 点击切换`}
        </div>
      </div>
    </div>
  );
}
