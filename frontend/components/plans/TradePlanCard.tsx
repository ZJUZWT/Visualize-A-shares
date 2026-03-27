"use client";

import { useState } from "react";
import { TradePlanData } from "@/lib/parseTradePlan";

interface TradePlanCardProps {
  plan: TradePlanData;
  onSave?: (plan: TradePlanData) => Promise<void>;
  savedPlan?: {
    id: string;
    status: string;
    created_at: string;
  };
  onStatusChange?: (id: string, status: string) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  /** "warm" = 暖色投顾风（plans 页面），"dark" = 暗色嵌入（专家对话） */
  variant?: "warm" | "dark";
}

/* ── 两套配色 token ──────────────────────────────── */
const palette = {
  warm: {
    card: "bg-white/80 border-black/10 shadow-[0_2px_12px_rgba(15,23,42,0.06)] hover:shadow-[0_4px_20px_rgba(15,23,42,0.10)]",
    title: "text-slate-950",
    subtitle: "text-slate-500",
    label: "text-slate-400",
    body: "text-slate-700",
    detail: "text-slate-600",
    detailLabel: "text-slate-400",
    price: "text-slate-900",
    entry: "text-blue-600",
    tp: "text-emerald-600",
    sl: "text-red-500",
    divider: "border-black/5",
    dirBuy: "bg-emerald-100 text-emerald-700",
    dirSell: "bg-red-100 text-red-600",
    winOdds: "border-amber-200 bg-amber-50 text-amber-700",
    statusPending: "bg-amber-100 text-amber-700",
    statusExecuting: "bg-blue-100 text-blue-700",
    statusCompleted: "bg-emerald-100 text-emerald-700",
    statusDefault: "bg-slate-100 text-slate-500",
    risk: "text-amber-600",
    invalid: "text-red-500",
    btnPrimary: "border border-black/10 bg-white text-slate-700 hover:bg-slate-50",
    btnSaved: "bg-emerald-100 text-emerald-700",
    btnDelete: "text-red-500 hover:bg-red-50",
    select: "border-black/10 bg-white text-slate-700 focus:ring-slate-950/10",
    date: "text-slate-400",
  },
  dark: {
    card: "bg-white/[0.06] border-white/10 shadow-none hover:bg-white/[0.09]",
    title: "text-white",
    subtitle: "text-gray-400",
    label: "text-gray-500",
    body: "text-gray-200",
    detail: "text-gray-400",
    detailLabel: "text-gray-500",
    price: "text-white",
    entry: "text-cyan-400",
    tp: "text-green-400",
    sl: "text-red-400",
    divider: "border-white/5",
    dirBuy: "bg-green-500/20 text-green-400",
    dirSell: "bg-red-500/20 text-red-400",
    winOdds: "border-amber-500/20 bg-amber-500/15 text-amber-400",
    statusPending: "bg-yellow-500/20 text-yellow-400",
    statusExecuting: "bg-blue-500/20 text-blue-400",
    statusCompleted: "bg-green-500/20 text-green-400",
    statusDefault: "bg-gray-500/20 text-gray-400",
    risk: "text-yellow-400/80",
    invalid: "text-red-400/80",
    btnPrimary: "bg-white/10 text-white hover:bg-white/20",
    btnSaved: "bg-green-500/20 text-green-400",
    btnDelete: "text-red-400 hover:bg-red-500/20",
    select: "border-white/20 bg-white/10 text-white focus:ring-white/20",
    date: "text-gray-500",
  },
};

function getStatusColor(status: string, t: typeof palette.warm) {
  switch (status) {
    case "pending": return t.statusPending;
    case "executing": return t.statusExecuting;
    case "completed": return t.statusCompleted;
    default: return t.statusDefault;
  }
}

const STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  executing: "执行中",
  completed: "已完成",
  expired: "已过期",
  ignored: "已忽略",
};

/** 将 "15.2 / 14.5 / 13.8" 拆成多行价格项 */
function parsePriceLevels(raw: string | null): string[] {
  if (!raw) return [];
  return raw.split(/\s*[/／]\s*/).map(s => s.trim()).filter(Boolean);
}

export default function TradePlanCard({
  plan,
  onSave,
  savedPlan,
  onStatusChange,
  onDelete,
  variant = "warm",
}: TradePlanCardProps) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const t = palette[variant];

  const isBuy = plan.direction === "buy";
  const dirLabel = isBuy ? "买入" : "卖出";

  const entryLevels = parsePriceLevels(plan.entry_price);
  const tpLevels = parsePriceLevels(plan.take_profit);

  const handleSave = async () => {
    if (!onSave || saved || saving) return;
    setSaving(true);
    try {
      await onSave(plan);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={`rounded-[20px] border p-5 transition ${t.card}`}>
      {/* 顶部：标的 + 方向 + 胜率赔率 + 状态 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className={`font-mono text-lg font-bold ${t.title}`}>{plan.stock_code}</span>
          <span className={`text-sm ${t.subtitle}`}>{plan.stock_name}</span>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${isBuy ? t.dirBuy : t.dirSell}`}>
            {dirLabel}
          </span>
          {plan.win_odds && (
            <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${t.winOdds}`}>
              🎯 {plan.win_odds}
            </span>
          )}
        </div>
        {savedPlan && (
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${getStatusColor(savedPlan.status, t)}`}>
            {STATUS_LABEL[savedPlan.status] || savedPlan.status}
          </span>
        )}
      </div>

      {/* 价格区 */}
      <div className="mt-3.5 space-y-2 text-sm">
        {plan.current_price != null && (
          <div className="flex items-center gap-2">
            <span className={`w-14 shrink-0 text-xs ${t.label}`}>现价</span>
            <span className={`font-mono font-semibold ${t.price}`}>{plan.current_price}</span>
          </div>
        )}

        {entryLevels.length > 0 && (
          <div className="flex items-start gap-2">
            <span className={`mt-0.5 w-14 shrink-0 text-xs ${t.label}`}>建议价</span>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {entryLevels.map((p, i) => (
                <span key={i} className={`font-mono font-semibold ${t.entry}`}>
                  {p}
                  {entryLevels.length > 1 && <span className={`ml-1 text-xs font-normal ${t.label}`}>({i === 0 ? "首仓" : i === entryLevels.length - 1 ? "底仓" : `第${i + 1}档`})</span>}
                </span>
              ))}
            </div>
          </div>
        )}

        {tpLevels.length > 0 && (
          <div className="flex items-start gap-2">
            <span className={`mt-0.5 w-14 shrink-0 text-xs ${t.label}`}>止盈</span>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {tpLevels.map((p, i) => (
                <span key={i} className={`font-mono font-semibold ${t.tp}`}>
                  {p}
                  {tpLevels.length > 1 && <span className={`ml-1 text-xs font-normal ${t.label}`}>(第{i + 1}档)</span>}
                </span>
              ))}
            </div>
          </div>
        )}

        {plan.stop_loss != null && (
          <div className="flex items-center gap-2">
            <span className={`w-14 shrink-0 text-xs ${t.label}`}>止损</span>
            <span className={`font-mono font-semibold ${t.sl}`}>{plan.stop_loss}</span>
          </div>
        )}
      </div>

      {/* 策略说明 */}
      {(plan.entry_method || plan.take_profit_method || plan.stop_loss_method) && (
        <div className={`mt-3 space-y-1 border-t ${t.divider} pt-3 text-xs ${t.detail}`}>
          {plan.entry_method && (
            <div><span className={t.detailLabel}>买入方式：</span>{plan.entry_method}</div>
          )}
          {plan.take_profit_method && (
            <div><span className={t.detailLabel}>止盈方式：</span>{plan.take_profit_method}</div>
          )}
          {plan.stop_loss_method && (
            <div><span className={t.detailLabel}>止损方式：</span>{plan.stop_loss_method}</div>
          )}
        </div>
      )}

      {/* 理由 + 风险 */}
      <div className={`mt-3 space-y-1.5 border-t ${t.divider} pt-3 text-sm`}>
        <div className={`leading-relaxed ${t.body}`}>{plan.reasoning}</div>
        {plan.risk_note && <div className={`text-xs ${t.risk}`}>⚠️ {plan.risk_note}</div>}
        {plan.invalidation && <div className={`text-xs ${t.invalid}`}>❌ {plan.invalidation}</div>}
      </div>

      {/* 底部：有效期 + 操作按钮 */}
      <div className={`mt-3 flex items-center justify-between border-t ${t.divider} pt-3`}>
        <div className={`text-xs ${t.date}`}>
          {plan.valid_until && <span>有效期：{plan.valid_until}</span>}
          {savedPlan?.created_at && <span className="ml-3">创建：{new Date(savedPlan.created_at).toLocaleDateString()}</span>}
        </div>
        <div className="flex items-center gap-2">
          {onSave && !savedPlan && (
            <button
              onClick={handleSave}
              disabled={saved || saving}
              className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-colors ${
                saved ? `${t.btnSaved} cursor-default` : t.btnPrimary
              }`}
            >
              {saved ? "已收藏 ✓" : saving ? "收藏中..." : "📋 收藏到备忘录"}
            </button>
          )}
          {savedPlan && onStatusChange && (
            <select
              value={savedPlan.status}
              onChange={(e) => onStatusChange(savedPlan.id, e.target.value)}
              className={`rounded-xl border px-2 py-1.5 text-xs outline-none focus:ring-2 ${t.select}`}
            >
              <option value="pending">待执行</option>
              <option value="executing">执行中</option>
              <option value="completed">已完成</option>
              <option value="expired">已过期</option>
              <option value="ignored">已忽略</option>
            </select>
          )}
          {savedPlan && onDelete && (
            <button
              onClick={() => onDelete(savedPlan.id)}
              className={`rounded-xl px-2 py-1.5 text-xs transition ${t.btnDelete}`}
            >
              删除
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
