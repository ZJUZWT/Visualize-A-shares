import type { TradePlanData } from "@/lib/parseTradePlan";
import {
  AgentStrategyActionRequest,
  AgentStrategyActionState,
  buildAgentStrategyKey,
} from "../types";

interface AgentStrategyActionCardProps {
  sessionId: string | null;
  messageId: string;
  plan: TradePlanData;
  actionState?: AgentStrategyActionState;
  interactive: boolean;
  onAction: (request: AgentStrategyActionRequest) => Promise<void>;
}

const ACTION_BADGES: Record<string, string> = {
  saved: "border-green-500/30 bg-green-500/15 text-green-300",
  ignored: "border-red-500/30 bg-red-500/15 text-red-300",
};

export default function AgentStrategyActionCard({
  sessionId,
  messageId,
  plan,
  actionState,
  interactive,
  onAction,
}: AgentStrategyActionCardProps) {
  const strategyKey = buildAgentStrategyKey(plan);
  const directionLabel = plan.direction === "buy" ? "买入" : "卖出";
  const directionStyle =
    plan.direction === "buy"
      ? "border-green-500/30 bg-green-500/15 text-green-300"
      : "border-red-500/30 bg-red-500/15 text-red-300";
  const isLocked =
    !interactive || Boolean(actionState?.action) || Boolean(actionState?.is_submitting);

  return (
    <div className="rounded-2xl border border-white/10 bg-[#11121a] p-4 shadow-[0_20px_60px_rgba(0,0,0,0.22)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold text-white">{plan.stock_code}</span>
            <span className="text-sm text-gray-300">{plan.stock_name}</span>
            <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${directionStyle}`}>
              {directionLabel}
            </span>
          </div>
          <p className="mt-1 text-xs text-gray-500">结构化交易计划</p>
        </div>
        {actionState?.action && (
          <span
            className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
              ACTION_BADGES[actionState.action]
            }`}
          >
            {actionState.action === "saved" ? "已收藏" : "已忽略"}
          </span>
        )}
      </div>

      <div className="mt-4 grid gap-3 text-sm text-gray-300 md:grid-cols-3">
        <div className="rounded-xl bg-white/[0.04] p-3">
          <div className="mb-2 text-xs uppercase tracking-[0.12em] text-gray-500">进场</div>
          <div className="space-y-1.5">
            <div>
              现价 <span className="text-white">{plan.current_price ?? "--"}</span>
            </div>
            <div>
              建议价 <span className="text-white">{plan.entry_price ?? "--"}</span>
            </div>
            <div>
              仓位{" "}
              <span className="text-white">
                {plan.position_pct === null ? "--" : `${(plan.position_pct * 100).toFixed(0)}%`}
              </span>
            </div>
            {plan.entry_method && <div className="text-xs text-gray-400">{plan.entry_method}</div>}
          </div>
        </div>

        <div className="rounded-xl bg-white/[0.04] p-3">
          <div className="mb-2 text-xs uppercase tracking-[0.12em] text-gray-500">离场</div>
          <div className="space-y-1.5">
            <div>
              止盈 <span className="text-green-300">{plan.take_profit ?? "--"}</span>
            </div>
            <div>
              止损 <span className="text-red-300">{plan.stop_loss ?? "--"}</span>
            </div>
            {plan.take_profit_method && (
              <div className="text-xs text-gray-400">{plan.take_profit_method}</div>
            )}
            {plan.stop_loss_method && (
              <div className="text-xs text-gray-400">{plan.stop_loss_method}</div>
            )}
          </div>
        </div>

        <div className="rounded-xl bg-white/[0.04] p-3">
          <div className="mb-2 text-xs uppercase tracking-[0.12em] text-gray-500">理由</div>
          <div className="space-y-2">
            <p className="text-sm leading-6 text-gray-200">{plan.reasoning}</p>
            {plan.risk_note && <p className="text-xs text-yellow-300">{plan.risk_note}</p>}
            {plan.invalidation && <p className="text-xs text-red-300">{plan.invalidation}</p>}
            {plan.valid_until && <p className="text-xs text-gray-500">有效期: {plan.valid_until}</p>}
          </div>
        </div>
      </div>

      {actionState?.reason && actionState.action === "ignored" && (
        <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          忽略备注: {actionState.reason}
        </div>
      )}

      {actionState?.error && (
        <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {actionState.error}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-white/10 pt-3">
        <span className="text-[11px] text-gray-500">
          {actionState?.updated_at
            ? `最近更新 ${new Date(actionState.updated_at).toLocaleString()}`
            : interactive
              ? "可将策略保存到备忘录"
              : "消息落库并绑定 session 后才能收藏或忽略"}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={isLocked}
            onClick={() => {
              if (!sessionId) {
                return;
              }
              void onAction({
                intent: "save",
                session_id: sessionId,
                message_id: messageId,
                strategy_key: strategyKey,
                plan,
              });
            }}
            className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
              isLocked
                ? "cursor-not-allowed bg-white/5 text-gray-500"
                : "bg-green-500/15 text-green-300 hover:bg-green-500/20"
            }`}
          >
            {actionState?.is_submitting && !actionState.action ? "提交中..." : "收藏策略"}
          </button>
          <button
            type="button"
            disabled={isLocked}
            onClick={() => {
              if (!sessionId) {
                return;
              }
              const note = window.prompt("记录忽略备注（可选）", actionState?.reason || "");
              if (note === null) {
                return;
              }
              void onAction({
                intent: "ignore",
                session_id: sessionId,
                message_id: messageId,
                strategy_key: strategyKey,
                plan,
                note: note.trim() || null,
              });
            }}
            className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
              isLocked
                ? "cursor-not-allowed bg-white/5 text-gray-500"
                : "bg-red-500/15 text-red-300 hover:bg-red-500/20"
            }`}
          >
            忽略策略
          </button>
        </div>
      </div>
    </div>
  );
}
