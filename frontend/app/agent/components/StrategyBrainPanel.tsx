import type { StrategyBrainViewModel } from "../lib/strategyBrainViewModel";

interface StrategyBrainPanelProps {
  viewModel: StrategyBrainViewModel;
  loading: boolean;
  stateError: string | null;
  memoryLoading: boolean;
  memoryError: string | null;
  reflectionLoading: boolean;
  reflectionError: string | null;
  strategyHistoryError: string | null;
}

function renderValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "未设置";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function renderMetric(label: string, value: string, accent?: string) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500">{label}</div>
      <div className={`mt-2 text-sm ${accent ?? "text-white"}`}>{value}</div>
    </div>
  );
}

export default function StrategyBrainPanel({
  viewModel,
  loading,
  stateError,
  memoryLoading,
  memoryError,
  reflectionLoading,
  reflectionError,
  strategyHistoryError,
}: StrategyBrainPanelProps) {
  const errors = [stateError, memoryError, reflectionError, strategyHistoryError].filter(
    (value): value is string => Boolean(value)
  );

  return (
    <section className="space-y-6">
      <section className="rounded-2xl border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.12),transparent_38%),linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01))] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-white">
              Strategy Brain
            </h2>
            <p className="mt-1 text-sm leading-6 text-gray-400">
              把当前策略状态、信念、决策链和反思演化收成一条完整主线。
            </p>
          </div>
          {viewModel.snapshot.activeRun && (
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-gray-300">
              {viewModel.snapshot.activeRun.runType} · {viewModel.snapshot.activeRun.status}
            </span>
          )}
        </div>

        {errors.length > 0 && (
          <div className="mt-4 space-y-2">
            {errors.map((error, index) => (
              <div
                key={`${error}-${index}`}
                className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200"
              >
                {error}
              </div>
            ))}
          </div>
        )}

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {renderMetric("市场观点", viewModel.snapshot.marketViewLabel)}
          {renderMetric("仓位水平", viewModel.snapshot.positionLevelLabel)}
          {renderMetric("行业偏好", `${viewModel.snapshot.sectorPreferenceCount} 项`)}
          {renderMetric("风险提醒", `${viewModel.snapshot.riskAlertCount} 项`)}
        </div>

        {viewModel.snapshot.activeRun && (
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            {renderMetric("最近 Run", viewModel.snapshot.activeRun.id, "font-mono text-cyan-200")}
            {renderMetric("决策数", String(viewModel.snapshot.activeRun.decisionCount))}
            {renderMetric("Token", String(viewModel.snapshot.activeRun.tokenCount))}
            {renderMetric(
              "完成时间",
              viewModel.snapshot.activeRun.completedAt || viewModel.snapshot.activeRun.startedAt
            )}
          </div>
        )}

        {(loading || memoryLoading || reflectionLoading) && (
          <div className="mt-4 text-sm text-gray-500">Strategy Brain 数据同步中...</div>
        )}
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-medium text-gray-200">Belief Ledger</h3>
          <p className="mt-1 text-xs text-gray-500">当前信念、分类、置信度和验证情况。</p>
        </div>
        {viewModel.beliefs.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
            暂无信念规则
          </div>
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {viewModel.beliefs.map((belief) => (
              <article key={belief.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm leading-6 text-white">{belief.title}</div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] ${
                      belief.statusTone === "strong"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-white/10 text-gray-400"
                    }`}
                  >
                    {belief.status}
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-400">
                  <span className="rounded border border-white/10 px-2 py-1">{belief.category}</span>
                  {belief.sourceRunId && (
                    <span className="rounded border border-white/10 px-2 py-1 font-mono">
                      {belief.sourceRunId}
                    </span>
                  )}
                </div>

                <div className="mt-4">
                  <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
                    <span>置信度</span>
                    <span className="text-white">{belief.confidencePct}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/10">
                    <div
                      className="h-2 rounded-full bg-cyan-400"
                      style={{ width: `${Math.max(0, Math.min(100, belief.confidencePct))}%` }}
                    />
                  </div>
                </div>

                <div className="mt-4 grid gap-2 text-xs text-gray-400 sm:grid-cols-2">
                  <div>验证次数: <span className="text-white">{belief.verifyCount}</span></div>
                  <div>验证胜场: <span className="text-white">{belief.verifyWin}</span></div>
                  <div>创建时间: <span className="text-white">{belief.createdAt || "--"}</span></div>
                  <div>退役时间: <span className="text-white">{belief.retiredAt || "--"}</span></div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-medium text-gray-200">Decision Timeline</h3>
          <p className="mt-1 text-xs text-gray-500">最近 run 的决策链、状态变化和执行结果。</p>
        </div>
        {viewModel.timeline.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
            暂无决策时间线
          </div>
        ) : (
          <div className="space-y-3">
            {viewModel.timeline.map((node) => (
              <article key={node.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm text-white">{node.title}</div>
                    <div className="mt-1 text-xs text-gray-500">{node.occurredAt || "--"}</div>
                  </div>
                  <div className="flex flex-wrap gap-2 text-[11px] text-gray-300">
                    <span className="rounded border border-white/10 px-2 py-1">
                      决策 {node.decisionCount}
                    </span>
                    <span className="rounded border border-white/10 px-2 py-1">
                      候选 {node.candidateCount}
                    </span>
                    <span className="rounded border border-white/10 px-2 py-1">
                      交易 {node.tradeCount}
                    </span>
                  </div>
                </div>

                {node.deltaSummary.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {node.deltaSummary.map((delta) => (
                      <span key={delta} className="rounded border border-cyan-500/20 bg-cyan-500/5 px-2 py-1 text-xs text-cyan-100">
                        {delta}
                      </span>
                    ))}
                  </div>
                )}

                {node.decisions.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {node.decisions.map((decision) => (
                      <div key={`${node.id}-${decision.stockCode}-${decision.action}`} className="rounded-lg border border-white/10 bg-black/10 p-3">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-mono text-white">{decision.stockCode}</span>
                          <span className="text-gray-300">{decision.stockName}</span>
                          <span className="rounded bg-white/10 px-2 py-0.5 text-[11px] text-gray-200">
                            {decision.action}
                          </span>
                          {decision.confidencePct !== null && (
                            <span className="text-[11px] text-gray-500">
                              信心 {decision.confidencePct}%
                            </span>
                          )}
                        </div>
                        {decision.reasoning && (
                          <div className="mt-2 text-xs leading-5 text-gray-400">{decision.reasoning}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {node.thinkingSummary && (
                  <details className="mt-3 group">
                    <summary className="cursor-pointer text-xs text-gray-400 hover:text-white">
                      推理摘要 ▸
                    </summary>
                    <div className="mt-2 rounded-lg bg-black/10 p-3 text-xs leading-6 text-gray-300">
                      {node.thinkingSummary}
                    </div>
                  </details>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-medium text-gray-200">Reflection & Evolution</h3>
          <p className="mt-1 text-xs text-gray-500">复盘总结与策略变迁的连续视图。</p>
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
          <div className="space-y-3">
            {viewModel.evolution.reflectionCards.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
                暂无反思记录
              </div>
            ) : (
              viewModel.evolution.reflectionCards.map((card) => (
                <article key={card.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="text-sm text-white">{card.title}</div>
                  <p className="mt-2 text-sm leading-6 text-gray-300">{card.summary}</p>
                  {Object.keys(card.metrics).length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {Object.entries(card.metrics).map(([key, value]) => (
                        <span key={key} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                          {key}: <span className="text-white">{renderValue(value)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </article>
              ))
            )}
          </div>

          <div className="space-y-3">
            {viewModel.evolution.strategyNodes.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
                暂无策略演化记录
              </div>
            ) : (
              viewModel.evolution.strategyNodes.map((node) => (
                <article key={node.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-xs text-white">{node.runId || "run:unknown"}</span>
                    <span className="text-xs text-gray-500">{node.occurredAt || "--"}</span>
                  </div>
                  <div className="mt-3 grid gap-2 text-xs text-gray-400">
                    <div>市场观点: <span className="text-white">{node.marketViewLabel}</span></div>
                    <div>仓位水平: <span className="text-white">{node.positionLevel}</span></div>
                    <div>行业偏好: <span className="text-white">{node.sectorPreferenceCount}</span></div>
                    <div>风险提醒: <span className="text-white">{node.riskAlertCount}</span></div>
                  </div>
                  {Object.keys(node.executionCounters).length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {Object.entries(node.executionCounters).map(([key, value]) => (
                        <span key={key} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                          {key}: <span className="text-white">{renderValue(value)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </article>
              ))
            )}
          </div>
        </div>
      </section>
    </section>
  );
}
