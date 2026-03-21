import { ReviewRecord, ReviewStats, WeeklySummary } from "../types";

interface ReviewRecordsPanelProps {
  loading: boolean;
  error: string | null;
  records: ReviewRecord[];
  stats: ReviewStats | null;
  weeklySummaries: WeeklySummary[];
  reviewType: "all" | "daily" | "weekly";
  onReviewTypeChange: (value: "all" | "daily" | "weekly") => void;
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return `${value.toFixed(2)}%`;
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(2);
}

export default function ReviewRecordsPanel({
  loading,
  error,
  records,
  stats,
  weeklySummaries,
  reviewType,
  onReviewTypeChange,
}: ReviewRecordsPanelProps) {
  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-gray-200">复盘记录</h2>
          <p className="mt-1 text-xs text-gray-500">
            展示 review records、统计摘要与 weekly summaries。
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-white/10 bg-white/5 p-1 text-xs">
          {(["all", "daily", "weekly"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onReviewTypeChange(value)}
              className={`rounded-md px-3 py-1 transition-colors ${
                reviewType === value
                  ? "bg-white/15 text-white"
                  : "text-gray-400 hover:bg-white/10 hover:text-white"
              }`}
            >
              {value === "all" ? "全部" : value}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          加载复盘记录中...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs text-gray-500">总胜率</div>
              <div className="mt-1 text-sm text-white">{formatPercent(stats?.total_win_rate)}</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs text-gray-500">总收益率</div>
              <div className="mt-1 text-sm text-white">{formatPercent(stats?.total_pnl_pct)}</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs text-gray-500">本周胜率</div>
              <div className="mt-1 text-sm text-white">{formatPercent(stats?.weekly_win_rate)}</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs text-gray-500">本周收益率</div>
              <div className="mt-1 text-sm text-white">{formatPercent(stats?.weekly_pnl_pct)}</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="text-xs text-gray-500">复盘数</div>
              <div className="mt-1 text-sm text-white">{stats?.total_reviews ?? records.length}</div>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 text-sm font-medium text-gray-200">周报摘要</div>
            {weeklySummaries.length === 0 ? (
              <div className="text-sm text-gray-500">暂无周报摘要</div>
            ) : (
              <div className="space-y-2">
                {weeklySummaries.map((summary) => (
                  <details key={summary.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
                    <summary className="cursor-pointer text-sm text-gray-200">
                      {summary.week_start || "--"} ~ {summary.week_end || "--"}
                      <span className="ml-2 text-xs text-gray-500">
                        胜率 {formatPercent(summary.win_rate)} / 收益 {formatPercent(summary.total_pnl_pct)}
                      </span>
                    </summary>
                    <div className="mt-3 grid gap-2 text-xs text-gray-400 sm:grid-cols-2">
                      <div>交易数: <span className="text-white">{summary.total_trades ?? "--"}</span></div>
                      <div>胜 / 负: <span className="text-white">{summary.win_count ?? "--"} / {summary.loss_count ?? "--"}</span></div>
                    </div>
                    {summary.insights && (
                      <div className="mt-3 rounded bg-white/5 p-3 text-xs text-gray-300 whitespace-pre-wrap">
                        {summary.insights}
                      </div>
                    )}
                  </details>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 text-sm font-medium text-gray-200">复盘列表</div>
            {records.length === 0 ? (
              <div className="text-sm text-gray-500">暂无复盘记录</div>
            ) : (
              <div className="space-y-2">
                {records.map((record) => (
                  <div key={record.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <span className="font-mono text-white">{record.stock_code || "--"}</span>
                        <span className="ml-2 text-gray-300">{record.stock_name || "未命名标的"}</span>
                        {record.action && (
                          <span className="ml-2 rounded bg-white/10 px-1.5 py-0.5 text-xs text-gray-300">
                            {record.action}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500">
                        {record.review_type || "unknown"} · {record.review_date || record.created_at || "--"}
                      </div>
                    </div>
                    <div className="mt-2 grid gap-2 text-xs text-gray-400 sm:grid-cols-3">
                      <div>决策价: <span className="text-white">{formatNumber(record.decision_price)}</span></div>
                      <div>复盘价: <span className="text-white">{formatNumber(record.review_price)}</span></div>
                      <div>
                        收益率:
                        <span className={`ml-1 ${
                          (record.pnl_pct ?? 0) >= 0 ? "text-green-300" : "text-red-300"
                        }`}>
                          {formatPercent(record.pnl_pct)}
                        </span>
                      </div>
                      <div>持有天数: <span className="text-white">{record.holding_days ?? "--"}</span></div>
                      <div>状态: <span className="text-white">{record.status || "--"}</span></div>
                      <div>Trade: <span className="font-mono text-white">{record.trade_id || "--"}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
