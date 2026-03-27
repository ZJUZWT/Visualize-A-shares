import type { TradePlanData } from "@/lib/parseTradePlan";
import {
  AgentStrategyExecutionRequest,
  AgentStrategyExecutionState,
  AgentStrategyMemoSaveRequest,
  AgentStrategyMemoState,
  buildAgentStrategyKey,
} from "../types";
import { mergeStrategyCardState } from "../lib/strategyActionViewModel";

interface AgentStrategyActionCardProps {
  sessionId: string | null;
  messageId: string;
  plan: TradePlanData;
  executionState?: AgentStrategyExecutionState;
  memoState?: AgentStrategyMemoState;
  interactive: boolean;
  onExecutionAction: (request: AgentStrategyExecutionRequest) => Promise<void>;
  onSaveMemo: (request: AgentStrategyMemoSaveRequest) => Promise<void>;
}

const EXECUTION_BADGES: Record<string, string> = {
  adopted: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300",
  rejected: "border-amber-500/30 bg-amber-500/15 text-amber-200",
};

const MEMO_BADGE = "border-sky-500/30 bg-sky-500/15 text-sky-200";

export default function AgentStrategyActionCard({
  sessionId,
  messageId,
  plan,
  executionState,
  memoState,
  interactive,
  onExecutionAction,
  onSaveMemo,
}: AgentStrategyActionCardProps) {
  const strategyKey = buildAgentStrategyKey(plan);
  const directionLabel = plan.direction === "buy" ? "买入" : "卖出";
  const directionStyle =
    plan.direction === "buy"
      ? "border-green-500/30 bg-green-500/15 text-green-300"
      : "border-red-500/30 bg-red-500/15 text-red-300";
  const mergedState = mergeStrategyCardState(executionState, memoState);
  const executionLocked = !interactive || !mergedState.canAdopt;
  const memoLocked = !interactive || !mergedState.canSaveMemo;
  const updatedAt = executionState?.updated_at ?? memoState?.updated_at ?? null;

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
        <div className="flex flex-wrap justify-end gap-2">
          {executionState?.decision && (
            <span
              className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                EXECUTION_BADGES[executionState.decision]
              }`}
            >
              {mergedState.executionLabel}
            </span>
          )}
          {memoState?.saved && (
            <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${MEMO_BADGE}`}>
              {mergedState.memoLabel}
            </span>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-3 text-sm text-gray-300 md:grid-cols-3">
        <div className="rounded-xl bg-white/[0.04] p-3">
          <div className="mb-2 text-xs uppercase tracking-[0.12em] text-gray-500">进场</div>
          <div className="space-y-1.5">
            <div>
              现价 <span className="text-white">{plan.current_price ?? "--"}</span>
            </div>
            <div>
              建议价 <span className="text-cyan-400">{plan.entry_price ?? "--"}</span>
            </div>
            <div>
              胜率赔率{" "}
              <span className="text-amber-400">
                {plan.win_odds ?? "--"}
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

      {executionState?.reason && executionState.decision === "rejected" && (
        <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
          忽略备注: {executionState.reason}
        </div>
      )}

      {memoState?.note && memoState.saved && (
        <div className="mt-3 rounded-xl border border-sky-500/20 bg-sky-500/10 px-3 py-2 text-xs text-sky-100">
          收藏备注: {memoState.note}
        </div>
      )}

      {executionState?.error && (
        <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {executionState.error}
        </div>
      )}

      {memoState?.error && (
        <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {memoState.error}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-white/10 pt-3">
        <span className="text-[11px] text-gray-500">
          {updatedAt
            ? `最近更新 ${new Date(updatedAt).toLocaleString()}`
            : interactive
              ? "可执行到虚拟组合，或仅收藏到备忘录"
              : "消息落库并绑定 session 后才能执行或收藏"}
        </span>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            disabled={executionLocked}
            onClick={() => {
              if (!sessionId) {
                return;
              }
              void onExecutionAction({
                intent: "adopt",
                session_id: sessionId,
                message_id: messageId,
                strategy_key: strategyKey,
                plan,
              });
            }}
            className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
              executionLocked
                ? "cursor-not-allowed bg-white/5 text-gray-500"
                : "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/20"
            }`}
          >
            {executionState?.is_submitting && !executionState.decision
              ? "提交中..."
              : mergedState.executionLabel === "已采纳"
                ? "已采纳"
                : "采纳"}
          </button>
          <button
            type="button"
            disabled={executionLocked}
            onClick={() => {
              if (!sessionId) {
                return;
              }
              const reason = window.prompt("记录忽略备注（可选）", executionState?.reason || "");
              if (reason === null) {
                return;
              }
              void onExecutionAction({
                intent: "reject",
                session_id: sessionId,
                message_id: messageId,
                strategy_key: strategyKey,
                plan,
                reason: reason.trim() || null,
              });
            }}
            className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
              executionLocked
                ? "cursor-not-allowed bg-white/5 text-gray-500"
                : "bg-amber-500/15 text-amber-200 hover:bg-amber-500/20"
            }`}
          >
            {executionState?.is_submitting && !executionState.decision
              ? "提交中..."
              : mergedState.executionLabel === "已忽略"
                ? "已忽略"
                : "忽略"}
          </button>
          <button
            type="button"
            disabled={memoLocked}
            onClick={() => {
              if (!sessionId) {
                return;
              }
              const note = window.prompt("记录收藏备注（可选）", memoState?.note || "");
              if (note === null) {
                return;
              }
              void onSaveMemo({
                session_id: sessionId,
                message_id: messageId,
                strategy_key: strategyKey,
                plan,
                note: note.trim() || null,
              });
            }}
            className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
              memoLocked
                ? "cursor-not-allowed bg-white/5 text-gray-500"
                : "bg-sky-500/15 text-sky-200 hover:bg-sky-500/20"
            }`}
          >
            {memoState?.is_submitting ? "收藏中..." : memoState?.saved ? "已收藏" : "收藏到备忘录"}
          </button>
        </div>
      </div>
    </div>
  );
}
