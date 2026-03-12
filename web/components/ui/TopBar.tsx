"use client";

/**
 * TopBar v2.0 — 顶部行情状态条
 * 清爽简约风格
 */

import { useState, useCallback } from "react";
import { useTerrainStore } from "@/stores/useTerrainStore";
import type { StockPoint } from "@/types/terrain";
import { formatZValue } from "@/types/terrain";

export default function TopBar() {
  const { terrainData, setSelectedStock, zMetric } = useTerrainStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<StockPoint[]>([]);

  const handleSearch = useCallback(
    (query: string) => {
      setSearchQuery(query);
      if (!query.trim() || !terrainData) {
        setSearchResults([]);
        return;
      }
      const q = query.toLowerCase();
      const results = terrainData.stocks
        .filter(
          (s) =>
            s.code.toLowerCase().includes(q) ||
            s.name.toLowerCase().includes(q)
        )
        .slice(0, 8);
      setSearchResults(results);
    },
    [terrainData]
  );

  const stats = terrainData
    ? (() => {
        const total = terrainData.stock_count;
        if (zMetric === "rise_prob") {
          // 上涨概率模式：值已减去0.5，>0.05 看涨 / <-0.05 看跌
          const up = terrainData.stocks.filter((s) => s.z > 0.05).length;
          const down = terrainData.stocks.filter((s) => s.z < -0.05).length;
          const flat = total - up - down;
          return { total, up, down, flat };
        }
        const up = terrainData.stocks.filter((s) => s.z > 0).length;
        const down = terrainData.stocks.filter((s) => s.z < 0).length;
        const flat = terrainData.stocks.filter(
          (s) => s.z === 0 || (s.z > -0.01 && s.z < 0.01)
        ).length;
        return { total, up, down, flat };
      })()
    : null;

  return (
    <div className="overlay fixed top-4 left-[280px] right-[260px] flex items-center gap-3">
      {/* 搜索框 */}
      <div className="glass-panel relative">
        <div className="flex items-center px-4 py-2.5">
          <svg
            className="w-4 h-4 text-[var(--text-tertiary)] mr-2 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="搜索股票代码或名称..."
            className="bg-transparent outline-none text-sm text-[var(--text-primary)] 
                       placeholder:text-[var(--text-tertiary)] w-[220px]"
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery("");
                setSearchResults([]);
              }}
              className="text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] ml-1"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* 搜索结果下拉 */}
        {searchResults.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-1.5 glass-panel py-1 max-h-[300px] overflow-y-auto">
            {searchResults.map((stock) => (
              <button
                key={stock.code}
                onClick={() => {
                  setSelectedStock(stock);
                  setSearchQuery("");
                  setSearchResults([]);
                }}
                className="w-full px-4 py-2.5 text-left hover:bg-gray-50 transition-smooth flex items-center justify-between"
              >
                <div>
                  <span className="text-sm font-medium text-[var(--text-primary)]">
                    {stock.name}
                  </span>
                  <span className="text-xs text-[var(--text-tertiary)] ml-2 font-mono">
                    {stock.code}
                  </span>
                </div>
                <span
                  className="text-xs font-mono font-semibold"
                  style={{ color: formatZValue(stock, zMetric).color }}
                >
                  {formatZValue(stock, zMetric).text}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 市场概况 */}
      {stats && (
        <div className="glass-panel px-5 py-2.5 flex items-center gap-5 ml-auto">
          <span className="text-xs text-[var(--text-secondary)]">
            全市场{" "}
            <span className="font-mono font-semibold text-[var(--text-primary)]">
              {stats.total}
            </span>
          </span>
          <div className="flex items-center gap-1 text-xs">
            <span className="text-rise font-medium">▲</span>
            <span className="font-mono font-semibold text-rise">{stats.up}</span>
          </div>
          <div className="flex items-center gap-1 text-xs">
            <span className="text-fall font-medium">▼</span>
            <span className="font-mono font-semibold text-fall">{stats.down}</span>
          </div>
          <div className="flex items-center gap-1 text-xs">
            <span className="text-flat">━</span>
            <span className="font-mono text-flat">{stats.flat}</span>
          </div>
        </div>
      )}
    </div>
  );
}
