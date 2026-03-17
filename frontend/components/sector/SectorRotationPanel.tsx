"use client";

import { useSectorStore } from "@/stores/useSectorStore";

function flowToColor(flow: number): string {
  const intensity = Math.min(Math.abs(flow) / 5e8, 1); // 5亿封顶
  if (flow > 0) {
    return `rgba(239, 68, 68, ${0.2 + intensity * 0.6})`;
  } else if (flow < 0) {
    return `rgba(34, 197, 94, ${0.2 + intensity * 0.6})`;
  }
  return "rgba(148, 163, 184, 0.1)";
}

function trendBadge(signal: string) {
  const cfg: Record<string, { bg: string; text: string; label: string }> = {
    bullish: { bg: "#ef444425", text: "#ef4444", label: "🔺 连续流入" },
    bearish: { bg: "#22c55e25", text: "#22c55e", label: "🔻 连续流出" },
    neutral: { bg: "#94a3b815", text: "#94a3b8", label: "— 震荡" },
  };
  const c = cfg[signal] || cfg.neutral;
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[10px] font-medium whitespace-nowrap"
      style={{ backgroundColor: c.bg, color: c.text }}
    >
      {c.label}
    </span>
  );
}

export function SectorRotationPanel() {
  const { rotationMatrix, topBullish, topBearish } = useSectorStore();

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden">
      <div className="px-4 py-2.5 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
          板块轮动预测
        </h2>
      </div>

      {rotationMatrix.length === 0 ? (
        <div className="flex items-center justify-center h-40 text-sm text-[var(--text-tertiary)]">
          暂无轮动数据（需先采集多日数据）
        </div>
      ) : (
        <div className="p-4 space-y-4">
          {/* 热力矩阵 */}
          <div className="overflow-x-auto">
            <table className="text-[10px] w-full">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left text-[var(--text-tertiary)] font-medium sticky left-0 bg-[var(--bg-secondary)]">
                    板块
                  </th>
                  {rotationMatrix[0]?.daily_dates.map((d) => (
                    <th key={d} className="px-1.5 py-1 text-center text-[var(--text-tertiary)] font-normal">
                      {d.slice(5)}
                    </th>
                  ))}
                  <th className="px-2 py-1 text-center text-[var(--text-tertiary)] font-medium">
                    趋势
                  </th>
                </tr>
              </thead>
              <tbody>
                {rotationMatrix.slice(0, 20).map((row) => (
                  <tr key={row.board_code} className="border-t border-[var(--border)]">
                    <td className="px-2 py-1.5 text-[var(--text-primary)] font-medium whitespace-nowrap sticky left-0 bg-[var(--bg-secondary)]">
                      {row.board_name}
                    </td>
                    {row.daily_flows.map((flow, i) => (
                      <td
                        key={i}
                        className="px-1.5 py-1.5 text-center"
                        style={{ backgroundColor: flowToColor(flow) }}
                        title={`${row.daily_dates[i]}: ${(flow / 1e8).toFixed(2)}亿`}
                      >
                        <span className="text-[9px] text-white/70 font-mono">
                          {Math.abs(flow) >= 1e8
                            ? (flow / 1e8).toFixed(1)
                            : Math.abs(flow) >= 1e4
                              ? (flow / 1e4).toFixed(0) + "w"
                              : ""}
                        </span>
                      </td>
                    ))}
                    <td className="px-2 py-1.5 text-center">{trendBadge(row.trend_signal)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Top5 看涨 / 看跌 */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="text-xs font-medium text-[#ef4444] mb-2">🔺 Top 看涨</h3>
              {topBullish.length === 0 ? (
                <p className="text-[10px] text-[var(--text-tertiary)]">暂无</p>
              ) : (
                <div className="space-y-1">
                  {topBullish.map((b) => (
                    <div
                      key={b.board_code}
                      className="px-2 py-1 rounded bg-[#ef444410] text-xs text-[#ef4444]"
                    >
                      {b.board_name}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div>
              <h3 className="text-xs font-medium text-[#22c55e] mb-2">🔻 Top 看跌</h3>
              {topBearish.length === 0 ? (
                <p className="text-[10px] text-[var(--text-tertiary)]">暂无</p>
              ) : (
                <div className="space-y-1">
                  {topBearish.map((b) => (
                    <div
                      key={b.board_code}
                      className="px-2 py-1 rounded bg-[#22c55e10] text-xs text-[#22c55e]"
                    >
                      {b.board_name}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
