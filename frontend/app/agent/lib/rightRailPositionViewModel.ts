import type { LedgerPosition } from "../types";

const GROUP_META: Record<string, { label: string; accent: string; order: number }> = {
  long_term: { label: "📅 长线", accent: "text-cyan-200", order: 0 },
  mid_term: { label: "📊 中线", accent: "text-emerald-200", order: 1 },
  short_term: { label: "⚡ 短线", accent: "text-amber-200", order: 2 },
  day_trade: { label: "🔄 做T", accent: "text-fuchsia-200", order: 3 },
  other: { label: "其他", accent: "text-gray-200", order: 9 },
};

function numberOrNull(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringOrNull(value: unknown) {
  return typeof value === "string" && value.trim() ? value : null;
}

function pushHighlight(
  items: Array<{ label: string; value: string }>,
  label: string,
  value: unknown
) {
  const text = stringOrNull(value);
  if (text) {
    items.push({ label, value: text });
  } else {
    const numeric = numberOrNull(value);
    if (numeric !== null) {
      items.push({ label, value: String(numeric) });
    }
  }
}

function buildHighlights(position: LedgerPosition) {
  const details = position.latest_strategy?.details ?? {};
  const holdingType = position.holding_type ?? "other";
  const highlights: Array<{ label: string; value: string }> = [];

  if (holdingType === "long_term") {
    pushHighlight(highlights, "基本面锚点", details["fundamental_anchor"]);
    pushHighlight(highlights, "离场条件", details["exit_condition"]);
    pushHighlight(highlights, "调仓触发", details["rebalance_trigger"]);
  } else if (holdingType === "mid_term") {
    pushHighlight(highlights, "趋势指标", details["trend_indicator"]);
    pushHighlight(highlights, "加仓位", details["add_position_price"]);
    pushHighlight(highlights, "减仓位", details["half_exit_price"]);
    pushHighlight(highlights, "催化剂", details["target_catalyst"]);
  } else if (holdingType === "short_term") {
    pushHighlight(highlights, "持有天数", details["hold_days"]);
    pushHighlight(highlights, "次日计划", details["next_day_plan"]);
    pushHighlight(highlights, "量能条件", details["volume_condition"]);
  } else if (holdingType === "day_trade") {
    pushHighlight(highlights, "底仓数量", details["t_core_qty"]);
    pushHighlight(highlights, "低吸价", details["t_buy_price"]);
    pushHighlight(highlights, "高抛价", details["t_sell_price"]);
  }

  if (highlights.length === 0) {
    pushHighlight(highlights, "策略", position.latest_strategy?.reasoning ?? "暂无策略细节");
  }

  return highlights.slice(0, 4);
}

function buildSignal(signal: LedgerPosition["status_signal"], reason: string | null | undefined) {
  if (signal === "danger") {
    return {
      tone: "danger" as const,
      label: "触发风险",
      reason: reason || "已触发风险阈值",
    };
  }
  if (signal === "warning") {
    return {
      tone: "warning" as const,
      label: "接近阈值",
      reason: reason || "接近策略阈值",
    };
  }
  return {
    tone: "healthy" as const,
    label: "正常",
    reason: reason || "策略阈值仍处于正常观察区间",
  };
}

export function buildRightRailPositionGroups(positions: LedgerPosition[]) {
  const grouped = new Map<string, Array<{
    id: string;
    stockCode: string;
    stockName: string;
    entryPrice: number | null;
    currentQty: number | null;
    costBasis: number | null;
    marketValue: number | null;
    unrealizedPnl: number | null;
    unrealizedPnlPct: number | null;
    positionPct: number | null;
    signal: { tone: "healthy" | "warning" | "danger"; label: string; reason: string };
    highlights: Array<{ label: string; value: string }>;
    strategyVersion: number | null;
    takeProfit: number | null;
    stopLoss: number | null;
  }>>();

  for (const position of positions) {
    const key = position.holding_type && GROUP_META[position.holding_type] ? position.holding_type : "other";
    const list = grouped.get(key) ?? [];
    list.push({
      id: position.id,
      stockCode: position.stock_code,
      stockName: position.stock_name,
      entryPrice: position.entry_price ?? null,
      currentQty: position.current_qty ?? null,
      costBasis: position.cost_basis ?? null,
      marketValue: position.market_value ?? null,
      unrealizedPnl: position.unrealized_pnl ?? null,
      unrealizedPnlPct: position.unrealized_pnl_pct ?? null,
      positionPct: position.position_pct ?? null,
      signal: buildSignal(position.status_signal, position.status_reason),
      highlights: buildHighlights(position),
      strategyVersion: position.latest_strategy?.version ?? null,
      takeProfit: position.latest_strategy?.take_profit ?? null,
      stopLoss: position.latest_strategy?.stop_loss ?? null,
    });
    grouped.set(key, list);
  }

  return Array.from(grouped.entries())
    .sort((a, b) => (GROUP_META[a[0]]?.order ?? 99) - (GROUP_META[b[0]]?.order ?? 99))
    .map(([key, items]) => ({
      key,
      label: GROUP_META[key]?.label ?? GROUP_META.other.label,
      accent: GROUP_META[key]?.accent ?? GROUP_META.other.accent,
      items,
    }));
}
