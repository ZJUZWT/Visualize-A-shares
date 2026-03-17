"use client";

import { useSectorStore } from "@/stores/useSectorStore";

function formatAmount(val: number): string {
  const abs = Math.abs(val);
  if (abs >= 1e8) return (val / 1e8).toFixed(2) + "亿";
  if (abs >= 1e4) return (val / 1e4).toFixed(1) + "万";
  return val.toFixed(0);
}

export function ConstituentTable() {
  const { constituents } = useSectorStore();

  if (constituents.length === 0) {
    return (
      <div className="flex items-center justify-center h-[280px] text-xs text-[var(--text-tertiary)]">
        暂无成分股数据
      </div>
    );
  }

  return (
    <div className="overflow-y-auto" style={{ maxHeight: 280 }}>
      <table className="w-full text-[11px]">
        <thead className="sticky top-0 bg-[var(--bg-secondary)]">
          <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
            <th className="px-2 py-1.5 text-left">代码</th>
            <th className="px-2 py-1.5 text-left">名称</th>
            <th className="px-2 py-1.5 text-right">现价</th>
            <th className="px-2 py-1.5 text-right">涨跌幅</th>
            <th className="px-2 py-1.5 text-right">成交额</th>
            <th className="px-2 py-1.5 text-right">换手</th>
          </tr>
        </thead>
        <tbody>
          {constituents.map((s) => (
            <tr
              key={s.code}
              className="border-b border-[var(--border)] hover:bg-[var(--bg-primary)]"
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
