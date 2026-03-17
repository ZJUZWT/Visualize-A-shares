"use client";

import { useState, useRef, useEffect } from "react";
import { Search, X, Loader2 } from "lucide-react";
import { useSectorStore } from "@/stores/useSectorStore";

export function StockSearchBar() {
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false);
  const {
    stockSearchResults, stockSearchLoading, boards,
    searchStock, clearStockSearch, openPanel,
  } = useSectorStore();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleChange = (val: string) => {
    setInput(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!val.trim()) {
      clearStockSearch();
      setOpen(false);
      return;
    }
    timerRef.current = setTimeout(() => {
      searchStock(val.trim());
      setOpen(true);
    }, 400);
  };

  const handleSelect = (result: typeof stockSearchResults[0]) => {
    const board = boards.find((b) => b.board_code === result.board_code);
    if (board) {
      openPanel(board);
    }
    setOpen(false);
    setInput("");
    clearStockSearch();
  };

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--border)]
                      bg-[var(--bg-secondary)] focus-within:border-[var(--accent)] transition-colors">
        <Search size={13} className="text-[var(--text-tertiary)] shrink-0" />
        <input
          value={input}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={() => stockSearchResults.length > 0 && setOpen(true)}
          placeholder="搜索股票→板块"
          className="bg-transparent text-xs text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]
                     outline-none w-32 focus:w-40 transition-all"
        />
        {stockSearchLoading && <Loader2 size={12} className="animate-spin text-[var(--text-tertiary)]" />}
        {input && (
          <button
            onClick={() => { setInput(""); clearStockSearch(); setOpen(false); }}
            className="text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {/* 搜索结果下拉 */}
      {open && stockSearchResults.length > 0 && (
        <div className="absolute top-full left-0 mt-1 w-80 max-h-64 overflow-y-auto z-50
                        rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)]
                        shadow-lg">
          <div className="px-3 py-2 border-b border-[var(--border)]">
            <span className="text-[10px] text-[var(--text-tertiary)]">
              找到 {stockSearchResults.length} 条匹配
            </span>
          </div>
          {stockSearchResults.map((r, i) => (
            <button
              key={`${r.stock_code}-${r.board_code}-${i}`}
              onClick={() => handleSelect(r)}
              className="w-full text-left px-3 py-2 hover:bg-[var(--bg-primary)]
                         border-b border-[var(--border)] last:border-b-0 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-[var(--text-secondary)]">
                    {r.stock_code}
                  </span>
                  <span className="text-xs text-[var(--text-primary)] font-medium">
                    {r.stock_name}
                  </span>
                </div>
                <span
                  className="text-[10px] font-mono"
                  style={{ color: r.stock_pct_chg >= 0 ? "#ef4444" : "#22c55e" }}
                >
                  {r.stock_pct_chg >= 0 ? "+" : ""}{r.stock_pct_chg.toFixed(2)}%
                </span>
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-[10px] text-[var(--accent)]">
                  → {r.board_name}
                </span>
                <span
                  className="text-[9px] font-mono"
                  style={{ color: r.board_pct_chg >= 0 ? "#ef4444" : "#22c55e" }}
                >
                  ({r.board_pct_chg >= 0 ? "+" : ""}{r.board_pct_chg.toFixed(2)}%)
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
