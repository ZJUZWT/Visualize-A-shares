"use client";

import { useState, useRef, useEffect } from "react";
import { useSectorStore } from "@/stores/useSectorStore";
import { fetchStockSectors, type StockSectorInfo } from "@/lib/sector-api";
import type { ConstituentItem } from "@/lib/sector-api";

function formatAmount(val: number): string {
  const abs = Math.abs(val);
  if (abs >= 1e8) return (val / 1e8).toFixed(2) + "亿";
  if (abs >= 1e4) return (val / 1e4).toFixed(1) + "万";
  return val.toFixed(0);
}

interface ConstituentTableProps {
  items?: ConstituentItem[];
}

export function ConstituentTable({ items }: ConstituentTableProps) {
  const storeConstituents = useSectorStore((s) => s.constituents);
  const constituents = items ?? storeConstituents;

  if (constituents.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-xs text-[var(--text-tertiary)]">
        暂无成分股数据
      </div>
    );
  }

  return (
    <div className="overflow-y-auto" style={{ maxHeight: 360 }}>
      <table className="w-full text-[11px]">
        <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
          <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
            <th className="px-2 py-1.5 text-left">代码</th>
            <th className="px-2 py-1.5 text-left">名称</th>
            <th className="px-2 py-1.5 text-right">现价</th>
            <th className="px-2 py-1.5 text-right">涨跌幅</th>
            <th className="px-2 py-1.5 text-right">成交额</th>
            <th className="px-2 py-1.5 text-right">换手</th>
            <th className="px-2 py-1.5 text-right">PE</th>
            <th className="px-2 py-1.5 text-right">PB</th>
          </tr>
        </thead>
        <tbody>
          {constituents.map((s) => (
            <StockRow key={s.code} stock={s} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 单行成分股——支持 hover 弹出关联板块 tooltip */
function StockRow({ stock }: { stock: ConstituentItem }) {
  const [hovering, setHovering] = useState(false);
  const [sectors, setSectors] = useState<StockSectorInfo[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const rowRef = useRef<HTMLTableRowElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { boards, openPanel } = useSectorStore();
  const s = stock;

  const handleMouseEnter = (e: React.MouseEvent) => {
    setHovering(true);
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setTooltipPos({ x: rect.left + rect.width / 2, y: rect.top });

    // 延迟 500ms 后请求板块信息（避免快速划过时频繁请求）
    timerRef.current = setTimeout(async () => {
      if (sectors !== null) return; // 已加载过
      setLoading(true);
      try {
        const data = await fetchStockSectors(s.code, s.name);
        setSectors(data.sectors || []);
      } catch {
        setSectors([]);
      } finally {
        setLoading(false);
      }
    }, 500);
  };

  const handleMouseLeave = () => {
    setHovering(false);
    if (timerRef.current) clearTimeout(timerRef.current);
  };

  const handleSectorClick = (boardCode: string) => {
    const board = boards.find((b) => b.board_code === boardCode);
    if (board) {
      openPanel(board);
    }
  };

  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, []);

  return (
    <>
      <tr
        ref={rowRef}
        className="border-b border-[var(--border)] hover:bg-[var(--bg-primary)] cursor-pointer relative"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        <td className="px-2 py-1.5 font-mono text-[var(--text-secondary)]">
          {s.code}
        </td>
        <td className="px-2 py-1.5 text-[var(--text-primary)]">{s.name}</td>
        <td className="px-2 py-1.5 text-right font-mono text-[var(--text-primary)]">
          {s.price.toFixed(2)}
        </td>
        <td
          className="px-2 py-1.5 text-right font-mono"
          style={{ color: s.pct_chg >= 0 ? "#ef4444" : "#22c55e" }}
        >
          {s.pct_chg >= 0 ? "+" : ""}
          {s.pct_chg.toFixed(2)}%
        </td>
        <td className="px-2 py-1.5 text-right font-mono text-[var(--text-secondary)]">
          {formatAmount(s.amount)}
        </td>
        <td className="px-2 py-1.5 text-right font-mono text-[var(--text-secondary)]">
          {s.turnover_rate.toFixed(1)}%
        </td>
        <td className="px-2 py-1.5 text-right font-mono text-[var(--text-tertiary)]">
          {s.pe_ttm != null ? s.pe_ttm.toFixed(1) : "-"}
        </td>
        <td className="px-2 py-1.5 text-right font-mono text-[var(--text-tertiary)]">
          {s.pb != null ? s.pb.toFixed(2) : "-"}
        </td>
      </tr>

      {/* 关联板块 Tooltip */}
      {hovering && tooltipPos && (sectors !== null || loading) && (
        <tr className="h-0">
          <td colSpan={8} className="p-0 relative">
            <div
              className="absolute z-50 w-60 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)]
                         shadow-lg p-2.5"
              style={{
                bottom: "100%",
                left: "50%",
                transform: "translateX(-50%)",
                marginBottom: 4,
              }}
            >
              <div className="text-[10px] text-[var(--text-tertiary)] mb-1.5">
                {s.name} 所属板块
              </div>
              {loading ? (
                <div className="text-[10px] text-[var(--text-tertiary)] text-center py-2">
                  加载中...
                </div>
              ) : sectors && sectors.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {sectors.map((sec) => (
                    <button
                      key={`${sec.board_code}-${sec.board_type}`}
                      onClick={() => handleSectorClick(sec.board_code)}
                      className="px-2 py-1 rounded text-[10px] border border-[var(--border)]
                                 hover:border-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors"
                    >
                      <span className="text-[var(--text-primary)]">{sec.board_name}</span>
                      <span
                        className="ml-1 font-mono text-[9px]"
                        style={{ color: sec.pct_chg >= 0 ? "#ef4444" : "#22c55e" }}
                      >
                        {sec.pct_chg >= 0 ? "+" : ""}{sec.pct_chg.toFixed(1)}%
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-[10px] text-[var(--text-tertiary)] text-center py-2">
                  未找到关联板块
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
