import { LedgerOverview } from "../types";

interface ExecutionLedgerPanelProps {
  overview: LedgerOverview | null;
  loading: boolean;
  error: string | null;
  source: "overview" | "fallback" | "unavailable" | null;
}

function formatNumber(value: number | null, digits = 2) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(digits);
}

export default function ExecutionLedgerPanel({
  overview,
  loading,
  error,
  source,
}: ExecutionLedgerPanelProps) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-gray-200">执行台账</h2>
          <p className="text-xs text-gray-500 mt-1">
            优先读取 `/api/v1/agent/ledger/overview`，缺失时回退到现有账本接口。
          </p>
        </div>
        {source && source !== "unavailable" && (
          <span className="text-xs text-gray-500">
            {source === "overview" ? "source: overview" : "source: fallback"}
          </span>
        )}
      </div>

      {loading && !overview ? (
        <div className="text-sm text-gray-500">加载台账中...</div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      ) : !overview ? (
        <div className="text-sm text-gray-500">暂无台账数据</div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500">总资产</div>
              <div className="mt-1 text-sm text-white">{formatNumber(overview.account.total_asset)}</div>
            </div>
            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500">现金</div>
              <div className="mt-1 text-sm text-white">{formatNumber(overview.account.cash_balance)}</div>
            </div>
            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500">收益</div>
              <div className={`mt-1 text-sm ${
                (overview.account.total_pnl ?? 0) >= 0 ? "text-green-300" : "text-red-300"
              }`}>
                {formatNumber(overview.account.total_pnl)} ({formatNumber(overview.account.total_pnl_pct)}%)
              </div>
            </div>
            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500">持仓 / 计划 / 交易</div>
              <div className="mt-1 text-sm text-white">
                {overview.account.position_count} / {overview.account.pending_plan_count} / {overview.account.trade_count}
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div>
              <h3 className="mb-2 text-sm font-medium text-gray-300">当前持仓 ({overview.positions.length})</h3>
              {overview.positions.length === 0 ? (
                <div className="rounded-lg bg-white/5 p-3 text-sm text-gray-500">暂无持仓</div>
              ) : (
                <div className="space-y-2">
                  {overview.positions.slice(0, 6).map((position) => (
                    <div key={position.id} className="rounded-lg bg-white/5 p-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <span className="font-mono text-white">{position.stock_code}</span>
                          <span className="ml-2 text-gray-300">{position.stock_name}</span>
                        </div>
                        <span className="text-xs text-gray-500">{position.holding_type || position.status || "open"}</span>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-400">
                        <div>数量: <span className="text-white">{position.current_qty ?? "--"}</span></div>
                        <div>成本: <span className="text-white">{formatNumber(position.cost_basis ?? null)}</span></div>
                        <div>开仓价: <span className="text-white">{formatNumber(position.entry_price ?? null)}</span></div>
                        <div>日期: <span className="text-white">{position.entry_date || "--"}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium text-gray-300">未完成计划 ({overview.pending_plans.length})</h3>
              {overview.pending_plans.length === 0 ? (
                <div className="rounded-lg bg-white/5 p-3 text-sm text-gray-500">暂无未完成计划</div>
              ) : (
                <div className="space-y-2">
                  {overview.pending_plans.slice(0, 6).map((plan) => (
                    <div key={plan.id} className="rounded-lg bg-white/5 p-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <span className="font-mono text-white">{plan.stock_code}</span>
                          <span className="ml-2 text-gray-300">{plan.stock_name}</span>
                        </div>
                        <span className="text-xs text-gray-500">{plan.direction} / {plan.status}</span>
                      </div>
                      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-400">
                        <div>入场: <span className="text-white">{formatNumber(plan.entry_price ?? null)}</span></div>
                        <div>止盈: <span className="text-green-300">{formatNumber(plan.take_profit ?? null)}</span></div>
                        <div>止损: <span className="text-red-300">{formatNumber(plan.stop_loss ?? null)}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium text-gray-300">最新交易 ({overview.recent_trades.length})</h3>
              {overview.recent_trades.length === 0 ? (
                <div className="rounded-lg bg-white/5 p-3 text-sm text-gray-500">暂无交易记录</div>
              ) : (
                <div className="space-y-2">
                  {overview.recent_trades.slice(0, 8).map((trade) => (
                    <div key={trade.id} className="rounded-lg bg-white/5 p-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <span className="font-mono text-white">{trade.stock_code}</span>
                          <span className="ml-2 text-gray-300">{trade.stock_name}</span>
                        </div>
                        <span className="text-xs text-gray-500">{trade.action}</span>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-400">
                        <div>数量: <span className="text-white">{trade.quantity ?? "--"}</span></div>
                        <div>价格: <span className="text-white">{formatNumber(trade.price ?? null)}</span></div>
                        <div>金额: <span className="text-white">{formatNumber(trade.amount ?? null)}</span></div>
                        <div>时间: <span className="text-white">{trade.created_at || "--"}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
