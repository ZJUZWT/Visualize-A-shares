import { BrainRun } from "../types";

interface DecisionRunPanelProps {
  run: BrainRun | null;
  loading: boolean;
  statusColor: Record<string, string>;
}

const BRAIN_STEPS = [
  { key: "scanning", label: "扫描信号" },
  { key: "selecting", label: "筛选标的" },
  { key: "analyzing", label: "分析标的" },
  { key: "digesting", label: "生成摘要" },
  { key: "deciding", label: "综合决策" },
  { key: "executing", label: "执行计划" },
] as const;

function getStepIndex(step: string | null): number {
  if (!step) return -1;
  return BRAIN_STEPS.findIndex((s) => s.key === step);
}

function renderSummaryValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "—";
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

function StepProgressBar({ currentStep }: { currentStep: string | null }) {
  const activeIdx = getStepIndex(currentStep);

  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="text-xs text-slate-400 mb-2">运行进度</div>
      <div className="flex items-center gap-1">
        {BRAIN_STEPS.map((step, idx) => {
          const isCompleted = activeIdx > idx;
          const isActive = activeIdx === idx;
          const isPending = activeIdx < idx;

          return (
            <div key={step.key} className="flex items-center gap-1 flex-1 min-w-0">
              <div className="flex flex-col items-center gap-1 flex-1 min-w-0">
                <div
                  className={`
                    w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium shrink-0
                    ${isCompleted ? "bg-emerald-500 text-white" : ""}
                    ${isActive ? "bg-blue-500 text-white animate-pulse" : ""}
                    ${isPending ? "bg-slate-200 text-slate-400" : ""}
                  `}
                >
                  {isCompleted ? "✓" : idx + 1}
                </div>
                <span
                  className={`text-[10px] leading-tight text-center truncate w-full
                    ${isCompleted ? "text-emerald-600 font-medium" : ""}
                    ${isActive ? "text-blue-600 font-medium" : ""}
                    ${isPending ? "text-slate-400" : ""}
                  `}
                >
                  {step.label}
                </span>
              </div>
              {idx < BRAIN_STEPS.length - 1 && (
                <div
                  className={`h-0.5 w-2 shrink-0 rounded-full mt-[-14px]
                    ${isCompleted ? "bg-emerald-300" : "bg-slate-200"}
                  `}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function DecisionRunPanel({ run, loading, statusColor }: DecisionRunPanelProps) {
  if (loading && !run) {
    return (
      <section className="rounded-[20px] border border-black/10 bg-white/80 p-5 text-sm text-slate-400 shadow-[0_2px_12px_rgba(15,23,42,0.06)]">
        加载运行上下文中...
      </section>
    );
  }

  if (!run) {
    return (
      <section className="rounded-[20px] border border-black/10 bg-white/80 p-5 text-sm text-slate-400 shadow-[0_2px_12px_rgba(15,23,42,0.06)]">
        暂无运行记录，手动运行后这里会显示最近一次决策与分析上下文。
      </section>
    );
  }

  const isRunning = run.status === "running";
  const executionSummaryEntries = run.execution_summary ? Object.entries(run.execution_summary) : [];
  const stateBeforeEntries = run.state_before ? Object.entries(run.state_before) : [];
  const stateAfterEntries = run.state_after ? Object.entries(run.state_after) : [];

  return (
    <section className="rounded-[20px] border border-black/10 bg-white/80 p-5 shadow-[0_2px_12px_rgba(15,23,42,0.06)] space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">最近运行上下文</h2>
          <p className="text-xs text-slate-400 mt-1">
            最近一次决策过程、候选标的和执行结果
          </p>
        </div>
        <span className={`px-2 py-0.5 rounded-full text-xs ${statusColor[run.status] || ""}`}>
          {isRunning ? "运行中..." : run.status}
        </span>
      </div>

      {/* 运行中显示进度条 */}
      {isRunning && <StepProgressBar currentStep={run.current_step} />}

      <div className="flex flex-wrap gap-4 text-xs text-slate-400">
        <span>开始: {new Date(run.started_at).toLocaleString()}</span>
        {run.completed_at && (
          <span>完成: {new Date(run.completed_at).toLocaleString()}</span>
        )}
        {run.llm_tokens_used > 0 && (
          <span>Token: {run.llm_tokens_used}</span>
        )}
      </div>

      {run.error_message && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-600">
          {run.error_message}
        </div>
      )}

      {executionSummaryEntries.length > 0 && (
        <div className="rounded-xl bg-slate-50 p-3">
          <div className="text-xs text-slate-400 mb-2">执行摘要</div>
          <div className="flex flex-wrap gap-2">
            {executionSummaryEntries.map(([key, value]) => (
              <span key={key} className="rounded-lg border border-black/10 bg-white px-2 py-1 text-xs text-slate-500">
                {key}: <span className="font-medium text-slate-900">{renderSummaryValue(value)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {(stateBeforeEntries.length > 0 || stateAfterEntries.length > 0) && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-xs text-slate-400 mb-2">状态前</div>
            {stateBeforeEntries.length === 0 ? (
              <div className="text-sm text-slate-400">无</div>
            ) : (
              <div className="space-y-1">
                {stateBeforeEntries.map(([key, value]) => (
                  <div key={key} className="text-xs text-slate-500">
                    {key}: <span className="font-medium text-slate-900">{renderSummaryValue(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-xs text-slate-400 mb-2">状态后</div>
            {stateAfterEntries.length === 0 ? (
              <div className="text-sm text-slate-400">无</div>
            ) : (
              <div className="space-y-1">
                {stateAfterEntries.map(([key, value]) => (
                  <div key={key} className="text-xs text-slate-500">
                    {key}: <span className="font-medium text-slate-900">{renderSummaryValue(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {run.candidates && run.candidates.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2">
            候选标的 ({run.candidates.length})
          </h3>
          <div className="flex flex-wrap gap-2">
            {run.candidates.map((candidate, index) => (
              <span key={index} className="rounded-lg border border-black/10 bg-slate-50 px-2 py-1 text-xs">
                <span className="font-mono font-medium text-slate-900">{candidate.stock_code}</span>
                <span className="text-slate-400 ml-1">{candidate.stock_name}</span>
                <span
                  className={`ml-1 ${
                    candidate.source === "position"
                      ? "text-blue-600"
                      : candidate.source === "watchlist"
                        ? "text-amber-600"
                        : "text-emerald-600"
                  }`}
                >
                  ({candidate.source})
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {run.decisions && run.decisions.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2">
            决策 ({run.decisions.length})
          </h3>
          <div className="space-y-2">
            {run.decisions.map((decision, index) => {
              const isBuy = decision.action === "buy" || decision.action === "add";
              return (
                <div key={index} className={`rounded-xl border p-3 ${
                  isBuy ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"
                }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono font-bold text-slate-900">{decision.stock_code}</span>
                    <span className="text-slate-500">{decision.stock_name}</span>
                    <span className={`rounded-full px-1.5 py-0.5 text-xs font-bold ${
                      isBuy ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"
                    }`}>
                      {decision.action}
                    </span>
                    {decision.confidence && (
                      <span className="text-xs text-slate-400">
                        信心: {(decision.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-slate-600 grid grid-cols-2 md:grid-cols-4 gap-2">
                    {decision.price && <div>价格: <span className="font-medium text-slate-900">{decision.price}</span></div>}
                    {decision.quantity && <div>数量: <span className="font-medium text-slate-900">{decision.quantity}</span></div>}
                    {decision.take_profit && <div>止盈: <span className="font-medium text-emerald-600">{decision.take_profit}</span></div>}
                    {decision.stop_loss && <div>止损: <span className="font-medium text-red-500">{decision.stop_loss}</span></div>}
                  </div>
                  {decision.reasoning && (
                    <div className="text-xs text-slate-400 mt-1">{decision.reasoning}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {run.thinking_process && (
        <details className="group">
          <summary className="text-sm font-medium text-slate-600 cursor-pointer hover:text-slate-900">
            推理摘要 ▸
          </summary>
          <pre className="mt-2 rounded-xl bg-slate-50 p-3 text-xs text-slate-500 whitespace-pre-wrap overflow-hidden">
            {typeof run.thinking_process === "string"
              ? run.thinking_process.slice(0, 800)
              : JSON.stringify(run.thinking_process, null, 1)?.slice(0, 800)}
          </pre>
        </details>
      )}

      {run.analysis_results && run.analysis_results.length > 0 && (
        <details className="group">
          <summary className="text-sm font-medium text-slate-600 cursor-pointer hover:text-slate-900">
            分析详情 ({run.analysis_results.length} 只) ▸
          </summary>
          <div className="mt-2 space-y-2 max-h-96 overflow-y-auto">
            {run.analysis_results.map((analysis, index) => (
              <div key={index} className="rounded-xl bg-slate-50 p-2 text-xs">
                <div className="font-mono font-medium text-slate-900 mb-1">{analysis.stock_code} {analysis.stock_name}</div>
                {analysis.error ? (
                  <div className="text-red-500">{analysis.error}</div>
                ) : (
                  <pre className="text-slate-500 whitespace-pre-wrap overflow-hidden max-h-32">
                    {typeof analysis.daily === "string"
                      ? analysis.daily.slice(0, 300)
                      : JSON.stringify(analysis.daily, null, 1)?.slice(0, 300)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
