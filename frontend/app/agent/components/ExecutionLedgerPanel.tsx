import {
  AgentEquityTimeline,
  AgentReplaySnapshot,
  LedgerOverview,
} from "../types";
import {
  buildEquityChartPoints,
  buildEquityPolylinePoints,
  summarizeSelectedEquityPoint,
  summarizeEquityTimeline,
} from "../lib/rightRailTimelineViewModel";
import { buildRightRailPositionGroups } from "../lib/rightRailPositionViewModel";

interface ExecutionLedgerPanelProps {
  overview: LedgerOverview | null;
  loading: boolean;
  error: string | null;
  source: "overview" | "fallback" | "unavailable" | null;
  timeline: AgentEquityTimeline | null;
  timelineLoading: boolean;
  timelineError: string | null;
  replay: AgentReplaySnapshot | null;
  replayLoading: boolean;
  replayError: string | null;
  replayDate: string;
  replayMinDate: string | null;
  replayMaxDate: string | null;
  onReplayDateChange: (value: string) => void;
}

function formatNumber(value: number | null, digits = 2) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatSignedNumber(value: number | null, digits = 2) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value, digits)}`;
}

function formatPercent(value: number | null, digits = 2) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}%`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "--";
  }
  return value.replace("T", " ").slice(0, 16);
}

function renderCardMetric(label: string, value: string, accent?: string) {
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`mt-1 text-sm ${accent ?? "text-white"}`}>{value}</div>
    </div>
  );
}

function renderListMessage(message: string) {
  return <div className="rounded-lg bg-white/5 p-3 text-sm text-gray-500">{message}</div>;
}

export default function ExecutionLedgerPanel({
  overview,
  loading,
  error,
  source,
  timeline,
  timelineLoading,
  timelineError,
  replay,
  replayLoading,
  replayError,
  replayDate,
  replayMinDate,
  replayMaxDate,
  onReplayDateChange,
}: ExecutionLedgerPanelProps) {
  const timelineSummary = summarizeEquityTimeline(timeline);
  const markPolyline = buildEquityPolylinePoints(timeline?.mark_to_market ?? [], 320, 120);
  const realizedPolyline = buildEquityPolylinePoints(timeline?.realized_only ?? [], 320, 120);
  const markPoints = buildEquityChartPoints(
    timeline?.mark_to_market ?? [],
    320,
    120,
    replayDate || null
  );
  const realizedPoints = buildEquityChartPoints(
    timeline?.realized_only ?? [],
    320,
    120,
    replayDate || null
  );
  const selectedPointSummary = summarizeSelectedEquityPoint(
    markPoints,
    realizedPoints,
    replayDate || null
  );
  const groupedPositions = buildRightRailPositionGroups(overview?.positions ?? []);
  const hasTimelineData = Boolean(
    timeline && (timeline.mark_to_market.length > 0 || timeline.realized_only.length > 0)
  );

  return (
    <section className="space-y-4">
      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-medium text-gray-200">执行台账</h2>
            <p className="text-xs text-gray-500 mt-1">
              账户快照保留现有账本读模型，收益曲线与历史回放直接读取 timeline API。
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
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {renderCardMetric("总资产", formatNumber(overview.account.total_asset))}
            {renderCardMetric("现金", formatNumber(overview.account.cash_balance))}
            {renderCardMetric(
              "收益",
              `${formatSignedNumber(overview.account.total_pnl)} (${formatSignedNumber(overview.account.total_pnl_pct)}%)`,
              (overview.account.total_pnl ?? 0) >= 0 ? "text-green-300" : "text-red-300"
            )}
            {renderCardMetric(
              "持仓 / 计划 / 交易",
              `${overview.account.position_count} / ${overview.account.pending_plan_count} / ${overview.account.trade_count}`
            )}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-gray-200">Equity Timeline</h3>
            <p className="mt-1 text-xs text-gray-500">
              同时展示市值口径和已实现口径，直接反映未实现盈亏的影响。
            </p>
          </div>
          {timeline?.end_date ? (
            <span className="text-xs text-gray-500">截至 {timeline.end_date}</span>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
          <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
            当前回放日期 {replayDate || "--"}
          </span>
          <span>
            选中点 {selectedPointSummary.date || "--"}
          </span>
          <span>
            市值口径 {formatNumber(selectedPointSummary.mark_to_market)}
          </span>
          <span>
            已实现口径 {formatNumber(selectedPointSummary.realized_only)}
          </span>
        </div>

        {timelineLoading && !timeline ? (
          <div className="text-sm text-gray-500">加载收益曲线中...</div>
        ) : timelineError ? (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
            {timelineError}
          </div>
        ) : !hasTimelineData ? (
          renderListMessage("暂无收益曲线数据")
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              {renderCardMetric(
                "市值口径总资产",
                formatNumber(timelineSummary.latest_mark_to_market)
              )}
              {renderCardMetric(
                "已实现口径总资产",
                formatNumber(timelineSummary.latest_realized_only)
              )}
              {renderCardMetric(
                "未实现影响",
                formatSignedNumber(timelineSummary.unrealized_delta),
                (timelineSummary.unrealized_delta ?? 0) >= 0 ? "text-amber-300" : "text-red-300"
              )}
            </div>

            <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
              <div className="mb-3 flex items-center gap-4 text-xs text-gray-400">
                <span className="inline-flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  mark_to_market
                </span>
                <span className="inline-flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-amber-300" />
                  realized_only
                </span>
              </div>
              <svg viewBox="0 0 320 120" className="h-36 w-full overflow-visible">
                <polyline
                  points={markPolyline}
                  fill="none"
                  stroke="rgb(52 211 153)"
                  strokeWidth="3"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {markPoints.map((point) => (
                  <g key={`mark-${point.date}`}>
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={point.isSelected ? 5.5 : 2.5}
                      fill="rgb(52 211 153)"
                      stroke={point.isSelected ? "white" : "none"}
                      strokeWidth={point.isSelected ? 2 : 0}
                      opacity={point.isSelected ? 1 : 0.95}
                    />
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={9}
                      fill="transparent"
                      className="cursor-pointer"
                      onClick={() => onReplayDateChange(point.date)}
                    />
                  </g>
                ))}
                <polyline
                  points={realizedPolyline}
                  fill="none"
                  stroke="rgb(252 211 77)"
                  strokeWidth="3"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {realizedPoints.map((point) => (
                  <g key={`realized-${point.date}`}>
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={point.isSelected ? 5.5 : 2.5}
                      fill="rgb(252 211 77)"
                      stroke={point.isSelected ? "white" : "none"}
                      strokeWidth={point.isSelected ? 2 : 0}
                      opacity={point.isSelected ? 1 : 0.95}
                    />
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={9}
                      fill="transparent"
                      className="cursor-pointer"
                      onClick={() => onReplayDateChange(point.date)}
                    />
                  </g>
                ))}
              </svg>
              <div className="mt-2 flex items-center justify-between text-[11px] text-gray-500">
                <span>{timeline?.start_date ?? "--"}</span>
                <span>{timeline?.end_date ?? "--"}</span>
              </div>
            </div>
          </>
        )}
      </section>

      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-gray-200">Historical Replay</h3>
            <p className="mt-1 text-xs text-gray-500">
              回看某一天 AI 的账户状态、当日动作和次日结果。
            </p>
          </div>
          <input
            type="date"
            value={replayDate}
            min={replayMinDate ?? undefined}
            max={replayMaxDate ?? undefined}
            onChange={(event) => onReplayDateChange(event.target.value)}
            className="rounded-lg border border-white/10 bg-slate-950/50 px-3 py-2 text-sm text-gray-200"
          />
        </div>

        {replayLoading && !replay ? (
          <div className="text-sm text-gray-500">加载历史回放中...</div>
        ) : replayError ? (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
            {replayError}
          </div>
        ) : !replay ? (
          renderListMessage("暂无历史回放数据")
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {renderCardMetric("现金", formatNumber(replay.account.cash_balance))}
              {renderCardMetric(
                "市值口径总资产",
                formatNumber(replay.account.total_asset_mark_to_market)
              )}
              {renderCardMetric(
                "已实现口径总资产",
                formatNumber(replay.account.total_asset_realized_only)
              )}
              {renderCardMetric(
                "已实现盈亏",
                formatSignedNumber(replay.account.realized_pnl),
                (replay.account.realized_pnl ?? 0) >= 0 ? "text-green-300" : "text-red-300"
              )}
              {renderCardMetric(
                "未实现盈亏",
                formatSignedNumber(replay.account.unrealized_pnl),
                (replay.account.unrealized_pnl ?? 0) >= 0 ? "text-amber-300" : "text-red-300"
              )}
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="space-y-3">
                <div>
                  <h4 className="mb-2 text-sm font-medium text-gray-300">
                    当日持仓 ({replay.positions.length})
                  </h4>
                  {replay.positions.length === 0 ? (
                    renderListMessage("当日没有持仓")
                  ) : (
                    <div className="space-y-2">
                      {replay.positions.slice(0, 6).map((position) => (
                        <div key={position.id} className="rounded-lg bg-white/5 p-3 text-sm">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <span className="font-mono text-white">{position.stock_code || "--"}</span>
                              <span className="ml-2 text-gray-300">{position.stock_name || "--"}</span>
                            </div>
                            <span className="text-xs text-gray-500">{position.holding_type || "position"}</span>
                          </div>
                          <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-400">
                            <div>数量: <span className="text-white">{position.current_qty ?? "--"}</span></div>
                            <div>成本: <span className="text-white">{formatNumber(position.cost_basis)}</span></div>
                            <div>收盘价: <span className="text-white">{formatNumber(position.close_price)}</span></div>
                            <div>市值: <span className="text-white">{formatNumber(position.market_value)}</span></div>
                            <div className="col-span-2">
                              浮盈亏: <span className={(position.unrealized_pnl ?? 0) >= 0 ? "text-amber-300" : "text-red-300"}>
                                {formatSignedNumber(position.unrealized_pnl)}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <h4 className="mb-2 text-sm font-medium text-gray-300">
                    当日交易 ({replay.trades.length})
                  </h4>
                  {replay.trades.length === 0 ? (
                    renderListMessage("当日没有交易")
                  ) : (
                    <div className="space-y-2">
                      {replay.trades.slice(0, 6).map((trade) => (
                        <div key={trade.id} className="rounded-lg bg-white/5 p-3 text-sm">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <span className="font-mono text-white">{trade.stock_code || "--"}</span>
                              <span className="ml-2 text-gray-300">{trade.stock_name || "--"}</span>
                            </div>
                            <span className="text-xs text-gray-500">{trade.action || "--"}</span>
                          </div>
                          <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-400">
                            <div>数量: <span className="text-white">{trade.quantity ?? "--"}</span></div>
                            <div>价格: <span className="text-white">{formatNumber(trade.price)}</span></div>
                            <div>金额: <span className="text-white">{formatNumber(trade.amount)}</span></div>
                            <div>时间: <span className="text-white">{formatDateTime(trade.created_at)}</span></div>
                          </div>
                          {trade.thesis ? (
                            <p className="mt-2 text-xs text-gray-300">{trade.thesis}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <h4 className="mb-2 text-sm font-medium text-gray-300">
                    当日计划 ({replay.plans.length})
                  </h4>
                  {replay.plans.length === 0 ? (
                    renderListMessage("当日没有计划更新")
                  ) : (
                    <div className="space-y-2">
                      {replay.plans.slice(0, 6).map((plan) => (
                        <div key={plan.id} className="rounded-lg bg-white/5 p-3 text-sm">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <span className="font-mono text-white">{plan.stock_code || "--"}</span>
                              <span className="ml-2 text-gray-300">{plan.stock_name || "--"}</span>
                            </div>
                            <span className="text-xs text-gray-500">
                              {plan.direction || "--"} / {plan.status || "--"}
                            </span>
                          </div>
                          {plan.reasoning ? (
                            <p className="mt-2 text-xs text-gray-300 line-clamp-3">{plan.reasoning}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-lg bg-white/5 p-3 text-sm">
                  <h4 className="text-sm font-medium text-gray-300">AI Context</h4>
                  <div className="mt-3 space-y-3 text-xs text-gray-300">
                    <div>
                      <div className="text-gray-500">Trade Theses</div>
                      {replay.what_ai_knew.trade_theses.length === 0 ? (
                        <div className="mt-1 text-gray-500">--</div>
                      ) : (
                        replay.what_ai_knew.trade_theses.slice(0, 4).map((item, index) => (
                          <div key={`${item}-${index}`} className="mt-1">{item}</div>
                        ))
                      )}
                    </div>
                    <div>
                      <div className="text-gray-500">Plan Reasoning</div>
                      {replay.what_ai_knew.plan_reasoning.length === 0 ? (
                        <div className="mt-1 text-gray-500">--</div>
                      ) : (
                        replay.what_ai_knew.plan_reasoning.slice(0, 3).map((item, index) => (
                          <div key={`${item}-${index}`} className="mt-1">{item}</div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

                <div className="rounded-lg bg-white/5 p-3 text-sm">
                  <h4 className="text-sm font-medium text-gray-300">Outcome</h4>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <div className="text-gray-500">Review Status</div>
                      <div className="mt-1 text-white">
                        {replay.what_happened.review_statuses.length > 0
                          ? replay.what_happened.review_statuses.join(", ")
                          : "--"}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">Next Day Move</div>
                      <div className={`mt-1 ${
                        (replay.what_happened.next_day_move_pct ?? 0) >= 0
                          ? "text-green-300"
                          : "text-red-300"
                      }`}>
                        {formatPercent(replay.what_happened.next_day_move_pct)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </section>

      {overview ? (
        <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
          <div>
            <h3 className="text-sm font-medium text-gray-200">Current Ledger Detail</h3>
            <p className="mt-1 text-xs text-gray-500">
              保留当前时点的持仓、计划和最新交易，便于和历史回放对照。
            </p>
          </div>

          <div className="space-y-3">
            <div>
              <h4 className="mb-2 text-sm font-medium text-gray-300">
                当前持仓 ({overview.positions.length})
              </h4>
              {overview.positions.length === 0 ? (
                renderListMessage("暂无持仓")
              ) : (
                <div className="space-y-4">
                  {groupedPositions.map((group) => (
                    <section key={group.key} className="space-y-2">
                      <div className={`text-xs font-medium ${group.accent}`}>{group.label}</div>
                      <div className="space-y-2">
                        {group.items.map((position) => (
                          <article
                            key={position.id}
                            className="rounded-xl border border-white/10 bg-white/[0.04] p-3 text-sm"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div>
                                  <span className="font-mono text-white">{position.stockCode}</span>
                                  <span className="ml-2 text-gray-300">{position.stockName}</span>
                                </div>
                                <div className="mt-1 text-[11px] text-gray-500">
                                  仓位占比 {formatPercent(
                                    position.positionPct === null ? null : position.positionPct * 100
                                  )} · strategy v{position.strategyVersion ?? "--"}
                                </div>
                              </div>
                              <div className="text-right">
                                <div
                                  className={`inline-flex items-center gap-2 rounded-full px-2 py-1 text-[11px] ${
                                    position.signal.tone === "healthy"
                                      ? "bg-emerald-500/15 text-emerald-200"
                                      : position.signal.tone === "warning"
                                        ? "bg-amber-500/15 text-amber-200"
                                        : "bg-red-500/15 text-red-200"
                                  }`}
                                >
                                  <span
                                    className={`h-2 w-2 rounded-full ${
                                      position.signal.tone === "healthy"
                                        ? "bg-emerald-400"
                                        : position.signal.tone === "warning"
                                          ? "bg-amber-300"
                                          : "bg-red-400"
                                    }`}
                                  />
                                  {position.signal.label}
                                </div>
                                <div className="mt-1 max-w-[220px] text-[11px] leading-4 text-gray-500">
                                  {position.signal.reason}
                                </div>
                              </div>
                            </div>

                            <div className="mt-3 grid gap-2 text-xs text-gray-400 sm:grid-cols-3">
                              <div>数量: <span className="text-white">{position.currentQty ?? "--"}</span></div>
                              <div>成本: <span className="text-white">{formatNumber(position.costBasis)}</span></div>
                              <div>开仓价: <span className="text-white">{formatNumber(position.entryPrice)}</span></div>
                              <div>市值: <span className="text-white">{formatNumber(position.marketValue)}</span></div>
                              <div>
                                浮盈亏:{" "}
                                <span className={(position.unrealizedPnl ?? 0) >= 0 ? "text-amber-300" : "text-red-300"}>
                                  {formatSignedNumber(position.unrealizedPnl)}
                                </span>
                              </div>
                              <div>
                                盈亏比:{" "}
                                <span className={(position.unrealizedPnlPct ?? 0) >= 0 ? "text-amber-300" : "text-red-300"}>
                                  {formatPercent(position.unrealizedPnlPct)}
                                </span>
                              </div>
                            </div>

                            <div className="mt-3 grid gap-2 md:grid-cols-2">
                              {position.highlights.map((highlight) => (
                                <div key={`${position.id}-${highlight.label}`} className="rounded-lg bg-black/10 px-3 py-2">
                                  <div className="text-[11px] text-gray-500">{highlight.label}</div>
                                  <div className="mt-1 text-xs leading-5 text-white">{highlight.value}</div>
                                </div>
                              ))}
                            </div>

                            <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-400">
                              <span className="rounded border border-white/10 px-2 py-1">
                                止盈 {formatNumber(position.takeProfit)}
                              </span>
                              <span className="rounded border border-white/10 px-2 py-1">
                                止损 {formatNumber(position.stopLoss)}
                              </span>
                            </div>
                          </article>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h4 className="mb-2 text-sm font-medium text-gray-300">
                未完成计划 ({overview.pending_plans.length})
              </h4>
              {overview.pending_plans.length === 0 ? (
                renderListMessage("暂无未完成计划")
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
              <h4 className="mb-2 text-sm font-medium text-gray-300">
                最新交易 ({overview.recent_trades.length})
              </h4>
              {overview.recent_trades.length === 0 ? (
                renderListMessage("暂无交易记录")
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
                        <div>时间: <span className="text-white">{formatDateTime(trade.created_at)}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}
    </section>
  );
}
