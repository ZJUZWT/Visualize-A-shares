import { StrategyMemoEntry } from "../types";

interface StrategyMemoPanelProps {
  loading: boolean;
  error: string | null;
  items: StrategyMemoEntry[];
  mutatingId: string | null;
  onArchive: (id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

function formatTime(value: string | null) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export default function StrategyMemoPanel({
  loading,
  error,
  items,
  mutatingId,
  onArchive,
  onDelete,
}: StrategyMemoPanelProps) {
  return (
    <section className="flex h-full min-h-0 flex-col bg-[#090a10]">
      <div className="border-b border-white/10 px-4 py-4">
        <h2 className="text-sm font-semibold tracking-[0.18em] text-white uppercase">
          Strategy Memo Inbox
        </h2>
        <p className="mt-1 text-xs leading-5 text-gray-500">
          仅展示收藏策略（saved），支持归档与删除。
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loading ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-gray-500">
            加载备忘录中...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-3 text-sm text-red-200">
            {error}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-gray-500">
            暂无收藏策略。
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((memo) => {
              const plan = memo.plan_snapshot;
              const busy = mutatingId === memo.id;
              return (
                <article
                  key={memo.id}
                  className="rounded-xl border border-white/10 bg-white/[0.03] p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm text-white">{memo.stock_code}</span>
                        <span className="text-sm text-gray-300">{memo.stock_name || "--"}</span>
                        {plan?.direction && (
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[11px] ${
                              plan.direction === "buy"
                                ? "border-green-500/30 bg-green-500/15 text-green-300"
                                : "border-red-500/30 bg-red-500/15 text-red-300"
                            }`}
                          >
                            {plan.direction === "buy" ? "买入" : "卖出"}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-gray-500">
                        来源: {memo.source_agent || "unknown"} · {formatTime(memo.created_at)}
                      </p>
                    </div>
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-gray-400">
                      {memo.status || "saved"}
                    </span>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-400">
                    <div>
                      进场: <span className="text-white">{plan?.entry_price ?? "--"}</span>
                    </div>
                    <div>
                      仓位:{" "}
                      <span className="text-white">
                        {plan?.position_pct === null || plan?.position_pct === undefined
                          ? "--"
                          : `${(plan.position_pct * 100).toFixed(0)}%`}
                      </span>
                    </div>
                    <div>
                      止盈: <span className="text-green-300">{plan?.take_profit ?? "--"}</span>
                    </div>
                    <div>
                      止损: <span className="text-red-300">{plan?.stop_loss ?? "--"}</span>
                    </div>
                  </div>

                  {memo.note && (
                    <p className="mt-3 rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs text-gray-300">
                      备注: {memo.note}
                    </p>
                  )}

                  <div className="mt-3 flex items-center justify-end gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onArchive(memo.id)}
                      className={`rounded-lg px-3 py-1.5 text-xs ${
                        busy
                          ? "cursor-not-allowed bg-white/5 text-gray-500"
                          : "bg-white/10 text-gray-200 hover:bg-white/20"
                      }`}
                    >
                      归档
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onDelete(memo.id)}
                      className={`rounded-lg px-3 py-1.5 text-xs ${
                        busy
                          ? "cursor-not-allowed bg-white/5 text-gray-500"
                          : "bg-red-500/15 text-red-200 hover:bg-red-500/25"
                      }`}
                    >
                      删除
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
