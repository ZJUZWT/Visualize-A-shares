"use client";

import { useSectorStore } from "@/stores/useSectorStore";
import { ConstituentTable } from "./ConstituentTable";
import { X, TrendingUp, TrendingDown, Users, DollarSign, BarChart3, Activity } from "lucide-react";
import type { SectorBoardItem, ConstituentItem } from "@/lib/sector-api";

interface SectorDetailPanelProps {
  /** 面板 ID（多面板模式） */
  panelId?: string;
  /** 外部传入的 board（多面板模式） */
  board?: SectorBoardItem;
  /** 外部传入的成分股（多面板模式） */
  constituents?: ConstituentItem[];
  /** 外部传入的 loading 状态 */
  loading?: boolean;
}

function formatLargeNumber(val: number): string {
  const abs = Math.abs(val);
  if (abs >= 1e12) return (val / 1e12).toFixed(2) + "万亿";
  if (abs >= 1e8) return (val / 1e8).toFixed(2) + "亿";
  if (abs >= 1e4) return (val / 1e4).toFixed(1) + "万";
  return val.toFixed(0);
}

export function SectorDetailPanel({ panelId, board: propBoard, constituents: propConstituents, loading: propLoading }: SectorDetailPanelProps) {
  const store = useSectorStore();
  // 优先使用 props，否则从 store 取（向后兼容单面板模式）
  const b = propBoard ?? store.selectedBoard;
  const constituents = propConstituents ?? store.constituents;
  const isLoading = propLoading ?? store.detailLoading;

  const handleClose = () => {
    if (panelId) {
      store.closePanel(panelId);
    } else {
      store.selectBoard(null);
    }
  };

  if (!b) return null;
  const isUp = b.pct_chg >= 0;

  return (
    <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--bg-secondary)] overflow-hidden">
      {/* 标题栏 */}
      <div className="px-4 py-2.5 border-b border-[var(--border)] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            {b.board_name}
          </h2>
          <span
            className="text-xs font-mono font-semibold"
            style={{ color: isUp ? "#ef4444" : "#22c55e" }}
          >
            {isUp ? "+" : ""}{b.pct_chg.toFixed(2)}%
          </span>
          <span className="text-[10px] text-[var(--text-tertiary)]">
            {b.board_code}
          </span>
          {b.prediction_signal && (
            <span
              className="px-1.5 py-0.5 rounded text-[9px] font-medium"
              style={{
                backgroundColor:
                  b.prediction_signal === "bullish" ? "rgba(239,68,68,0.15)" :
                  b.prediction_signal === "bearish" ? "rgba(34,197,94,0.15)" :
                  "rgba(148,163,184,0.15)",
                color:
                  b.prediction_signal === "bullish" ? "#ef4444" :
                  b.prediction_signal === "bearish" ? "#22c55e" :
                  "#94a3b8",
              }}
            >
              {b.prediction_signal === "bullish" ? "看涨" : b.prediction_signal === "bearish" ? "看跌" : "中性"}
            </span>
          )}
        </div>
        <button
          onClick={handleClose}
          className="p-1 rounded hover:bg-[var(--bg-primary)] text-[var(--text-tertiary)]"
        >
          <X size={14} />
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-48 text-sm text-[var(--text-tertiary)]">
          加载详情中...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 divide-x divide-[var(--border)]">
          {/* 左：板块基本信息 */}
          <div className="p-4">
            <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-3">
              板块概况
            </h3>
            <div className="grid grid-cols-2 gap-2.5">
              <InfoCard
                icon={<DollarSign size={12} />}
                label="最新价"
                value={b.close > 0 ? b.close.toFixed(2) : "-"}
              />
              <InfoCard
                icon={isUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                label="涨跌幅"
                value={`${isUp ? "+" : ""}${b.pct_chg.toFixed(2)}%`}
                color={isUp ? "#ef4444" : "#22c55e"}
              />
              <InfoCard
                icon={<BarChart3 size={12} />}
                label="成交额"
                value={b.amount > 0 ? formatLargeNumber(b.amount) : "-"}
              />
              <InfoCard
                icon={<Activity size={12} />}
                label="换手率"
                value={b.turnover_rate > 0 ? `${b.turnover_rate.toFixed(2)}%` : "-"}
              />
              <InfoCard
                icon={<Users size={12} />}
                label="涨/跌家数"
                value={`${b.rise_count} / ${b.fall_count}`}
                color={b.rise_count > b.fall_count ? "#ef4444" : "#22c55e"}
              />
              <InfoCard
                icon={<DollarSign size={12} />}
                label="主力净流入"
                value={b.main_force_net_inflow != null ? formatLargeNumber(b.main_force_net_inflow) : "-"}
                color={b.main_force_net_inflow != null && b.main_force_net_inflow >= 0 ? "#ef4444" : "#22c55e"}
              />
            </div>

            {/* 领涨股 */}
            {b.leading_stock && (
              <div className="mt-3 px-3 py-2 rounded-lg" style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" }}>
                <span className="text-[10px] text-[var(--text-tertiary)]">领涨股</span>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs font-medium text-[var(--text-primary)]">{b.leading_stock}</span>
                  {b.leading_pct_chg !== 0 && (
                    <span
                      className="text-[11px] font-mono"
                      style={{ color: b.leading_pct_chg >= 0 ? "#ef4444" : "#22c55e" }}
                    >
                      {b.leading_pct_chg >= 0 ? "+" : ""}{b.leading_pct_chg.toFixed(2)}%
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* 总市值 */}
            {b.total_mv > 0 && (
              <div className="mt-2 text-[10px] text-[var(--text-tertiary)]">
                总市值：{formatLargeNumber(b.total_mv)}
              </div>
            )}
          </div>

          {/* 右：成分股（占两列） */}
          <div className="p-4 lg:col-span-2">
            <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">
              成分股 · {constituents.length} 只
            </h3>
            <ConstituentTable items={constituents} />
          </div>
        </div>
      )}
    </div>
  );
}

/** 信息卡片 */
function InfoCard({
  icon, label, value, color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div
      className="rounded-lg px-2.5 py-2 flex flex-col gap-0.5"
      style={{ backgroundColor: "rgba(255,255,255,0.02)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center gap-1 text-[var(--text-tertiary)]">
        {icon}
        <span className="text-[9px]">{label}</span>
      </div>
      <span
        className="text-xs font-mono font-medium"
        style={{ color: color ?? "var(--text-primary)" }}
      >
        {value}
      </span>
    </div>
  );
}
