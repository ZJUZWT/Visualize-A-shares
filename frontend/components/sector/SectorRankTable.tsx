"use client";

import { useMemo } from "react";
import { useSectorStore } from "@/stores/useSectorStore";
import { ArrowUpDown } from "lucide-react";

function formatAmount(val: number | null): string {
  if (val === null || val === undefined) return "-";
  const abs = Math.abs(val);
  if (abs >= 1e8) return (val / 1e8).toFixed(2) + "亿";
  if (abs >= 1e4) return (val / 1e4).toFixed(1) + "万";
  return val.toFixed(0);
}

function pctColor(pct: number): string {
  if (pct > 0) return "#ef4444";
  if (pct < 0) return "#22c55e";
  return "var(--text-secondary)";
}

function signalBadge(signal: string | null) {
  if (!signal) return null;
  const cfg: Record<string, { bg: string; text: string; label: string }> = {
    bullish: { bg: "#ef444420", text: "#ef4444", label: "看涨" },
    bearish: { bg: "#22c55e20", text: "#22c55e", label: "看跌" },
    neutral: { bg: "#94a3b820", text: "#94a3b8", label: "中性" },
  };
  const c = cfg[signal] || cfg.neutral;
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[10px] font-medium"
      style={{ backgroundColor: c.bg, color: c.text }}
    >
      {c.label}
    </span>
  );
}

export function SectorRankTable() {
  const { boards, sortField, sortDesc, setSortField, selectBoard, selectedBoard, loading } =
    useSectorStore();

  const sorted = useMemo(() => {
    const arr = [...boards];
    arr.sort((a, b) => {
      const va = (a as Record<string, unknown>)[sortField] ?? 0;
      const vb = (b as Record<string, unknown>)[sortField] ?? 0;
      return sortDesc ? Number(vb) - Number(va) : Number(va) - Number(vb);
    });
    return arr;
  }, [boards, sortField, sortDesc]);

  const columns: { key: string; label: string; sortable: boolean }[] = [
    { key: "rank", label: "#", sortable: false },
    { key: "board_name", label: "板块", sortable: false },
    { key: "pct_chg", label: "涨跌幅", sortable: true },
    { key: "main_force_net_inflow", label: "主力净流入", sortable: true },
    { key: "prediction_score", label: "预测", sortable: true },
    { key: "leading_stock", label: "领涨股", sortable: false },
  ];

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden flex flex-col">
      <div className="px-4 py-2.5 border-b border-[var(--border)] flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">板块排行</h2>
        <span className="text-[10px] text-[var(--text-tertiary)]">{boards.length} 个板块</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading && boards.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-sm text-[var(--text-tertiary)]">
            加载中...
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
              <tr className="border-b border-[var(--border)]">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className={`px-3 py-2 text-left font-medium text-[var(--text-tertiary)] ${
                      col.sortable ? "cursor-pointer hover:text-[var(--text-primary)]" : ""
                    }`}
                    onClick={() => col.sortable && setSortField(col.key as typeof sortField)}
                  >
                    <span className="flex items-center gap-1">
                      {col.label}
                      {col.sortable && <ArrowUpDown size={10} />}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((b, i) => (
                <tr
                  key={b.board_code}
                  className={`border-b border-[var(--border)] cursor-pointer transition-colors
                    ${selectedBoard?.board_code === b.board_code
                      ? "bg-[var(--accent-light)]"
                      : "hover:bg-[var(--bg-primary)]"
                    }`}
                  onClick={() => selectBoard(b)}
                >
                  <td className="px-3 py-2 text-[var(--text-tertiary)]">{i + 1}</td>
                  <td className="px-3 py-2 text-[var(--text-primary)] font-medium">{b.board_name}</td>
                  <td className="px-3 py-2 font-mono" style={{ color: pctColor(b.pct_chg) }}>
                    {b.pct_chg > 0 ? "+" : ""}
                    {b.pct_chg.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 font-mono" style={{ color: pctColor(b.main_force_net_inflow ?? 0) }}>
                    {formatAmount(b.main_force_net_inflow)}
                  </td>
                  <td className="px-3 py-2">{signalBadge(b.prediction_signal)}</td>
                  <td className="px-3 py-2 text-[var(--text-secondary)]">
                    {b.leading_stock}
                    {b.leading_pct_chg ? (
                      <span className="ml-1" style={{ color: pctColor(b.leading_pct_chg) }}>
                        {b.leading_pct_chg > 0 ? "+" : ""}{b.leading_pct_chg.toFixed(1)}%
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
