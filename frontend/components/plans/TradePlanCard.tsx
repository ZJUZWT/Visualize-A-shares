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
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "待执行", color: "bg-yellow-500/20 text-yellow-400" },
  executing: { label: "执行中", color: "bg-blue-500/20 text-blue-400" },
  completed: { label: "已完成", color: "bg-green-500/20 text-green-400" },
  expired: { label: "已过期", color: "bg-gray-500/20 text-gray-400" },
  ignored: { label: "已忽略", color: "bg-gray-500/20 text-gray-400" },
};

export default function TradePlanCard({
  plan,
  onSave,
  savedPlan,
  onStatusChange,
  onDelete,
}: TradePlanCardProps) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const isBuy = plan.direction === "buy";
  const dirLabel = isBuy ? "买入" : "卖出";
  const dirColor = isBuy ? "text-green-400" : "text-red-400";
  const dirBg = isBuy ? "bg-green-500/10 border-green-500/30" : "bg-red-500/10 border-red-500/30";

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
    <div className={`rounded-lg border p-4 ${dirBg} space-y-3`}>
      {/* 顶部：标的 + 方向 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-white">{plan.stock_code}</span>
          <span className="text-gray-300">{plan.stock_name}</span>
          <span className={`px-2 py-0.5 rounded text-xs font-bold ${dirColor} ${isBuy ? "bg-green-500/20" : "bg-red-500/20"}`}>
            {dirLabel}
          </span>
        </div>
        {savedPlan && (
          <span className={`px-2 py-0.5 rounded text-xs ${STATUS_LABELS[savedPlan.status]?.color || ""}`}>
            {STATUS_LABELS[savedPlan.status]?.label || savedPlan.status}
          </span>
        )}
      </div>

      {/* 三栏内容 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
        <div className="space-y-1">
          <div className="text-gray-400 font-medium text-xs">进场策略</div>
          {plan.current_price && <div>现价：<span className="text-white">{plan.current_price}</span></div>}
          {plan.entry_price && <div>建议价：<span className="text-white">{plan.entry_price}</span></div>}
          {plan.entry_method && <div className="text-gray-300">{plan.entry_method}</div>}
          {plan.position_pct && <div>仓位：<span className="text-white">{(plan.position_pct * 100).toFixed(0)}%</span></div>}
        </div>

        <div className="space-y-1">
          <div className="text-gray-400 font-medium text-xs">离场策略</div>
          {plan.take_profit && <div>止盈：<span className="text-green-400">{plan.take_profit}</span></div>}
          {plan.take_profit_method && <div className="text-gray-300">{plan.take_profit_method}</div>}
          {plan.stop_loss && <div>止损：<span className="text-red-400">{plan.stop_loss}</span></div>}
          {plan.stop_loss_method && <div className="text-gray-300">{plan.stop_loss_method}</div>}
        </div>

        <div className="space-y-1">
          <div className="text-gray-400 font-medium text-xs">理由</div>
          <div className="text-gray-200">{plan.reasoning}</div>
          {plan.risk_note && <div className="text-yellow-400/80 text-xs">⚠️ {plan.risk_note}</div>}
          {plan.invalidation && <div className="text-red-400/80 text-xs">❌ {plan.invalidation}</div>}
        </div>
      </div>

      {/* 底部：有效期 + 操作按钮 */}
      <div className="flex items-center justify-between pt-2 border-t border-white/10">
        <div className="text-xs text-gray-500">
          {plan.valid_until && <span>有效期：{plan.valid_until}</span>}
          {savedPlan?.created_at && <span className="ml-3">创建：{new Date(savedPlan.created_at).toLocaleDateString()}</span>}
        </div>
        <div className="flex gap-2">
          {onSave && !savedPlan && (
            <button
              onClick={handleSave}
              disabled={saved || saving}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                saved
                  ? "bg-green-500/20 text-green-400 cursor-default"
                  : "bg-white/10 text-white hover:bg-white/20"
              }`}
            >
              {saved ? "已收藏 ✓" : saving ? "收藏中..." : "📋 收藏到备忘录"}
            </button>
          )}
          {savedPlan && onStatusChange && (
            <select
              value={savedPlan.status}
              onChange={(e) => onStatusChange(savedPlan.id, e.target.value)}
              className="bg-white/10 text-white text-xs rounded px-2 py-1 border border-white/20"
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
              className="px-2 py-1 rounded text-xs text-red-400 hover:bg-red-500/20"
            >
              删除
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
