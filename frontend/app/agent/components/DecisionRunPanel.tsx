import { BrainRun } from "../types";

interface DecisionRunPanelProps {
  run: BrainRun | null;
  loading: boolean;
  statusColor: Record<string, string>;
}

function renderSummaryValue(value: unknown) {
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

export default function DecisionRunPanel({ run, loading, statusColor }: DecisionRunPanelProps) {
  if (loading && !run) {
    return (
      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
        加载运行上下文中...
      </section>
    );
  }

  if (!run) {
    return (
      <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
        暂无运行记录，手动运行后这里会显示最近一次决策与分析上下文。
      </section>
    );
  }

  const executionSummaryEntries = run.execution_summary ? Object.entries(run.execution_summary) : [];
  const stateBeforeEntries = run.state_before ? Object.entries(run.state_before) : [];
  const stateAfterEntries = run.state_after ? Object.entries(run.state_after) : [];

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-gray-200">最近运行上下文</h2>
          <p className="text-xs text-gray-500 mt-1">
            读取 brain run，并叠加 decision/state transition/execution summary。
          </p>
        </div>
        <span className={`px-2 py-0.5 rounded text-xs ${statusColor[run.status] || ""}`}>
          {run.status === "running" ? "运行中..." : run.status}
        </span>
      </div>

      <div className="flex flex-wrap gap-4 text-sm text-gray-400">
        <span>开始: {new Date(run.started_at).toLocaleString()}</span>
        {run.completed_at && (
          <span>完成: {new Date(run.completed_at).toLocaleString()}</span>
        )}
        {run.llm_tokens_used > 0 && (
          <span>Token: {run.llm_tokens_used}</span>
        )}
      </div>

      {run.error_message && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
          {run.error_message}
        </div>
      )}

      {executionSummaryEntries.length > 0 && (
        <div className="rounded-lg bg-white/5 p-3">
          <div className="text-xs text-gray-500 mb-2">执行摘要</div>
          <div className="flex flex-wrap gap-2">
            {executionSummaryEntries.map(([key, value]) => (
              <span key={key} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                {key}: <span className="text-white">{renderSummaryValue(value)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {(stateBeforeEntries.length > 0 || stateAfterEntries.length > 0) && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg bg-white/5 p-3">
            <div className="text-xs text-gray-500 mb-2">状态前</div>
            {stateBeforeEntries.length === 0 ? (
              <div className="text-sm text-gray-400">无</div>
            ) : (
              <div className="space-y-1">
                {stateBeforeEntries.map(([key, value]) => (
                  <div key={key} className="text-xs text-gray-300">
                    {key}: <span className="text-white">{renderSummaryValue(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="rounded-lg bg-white/5 p-3">
            <div className="text-xs text-gray-500 mb-2">状态后</div>
            {stateAfterEntries.length === 0 ? (
              <div className="text-sm text-gray-400">无</div>
            ) : (
              <div className="space-y-1">
                {stateAfterEntries.map(([key, value]) => (
                  <div key={key} className="text-xs text-gray-300">
                    {key}: <span className="text-white">{renderSummaryValue(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {run.candidates && run.candidates.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-300 mb-2">
            候选标的 ({run.candidates.length})
          </h3>
          <div className="flex flex-wrap gap-2">
            {run.candidates.map((candidate, index) => (
              <span key={index} className="px-2 py-1 rounded text-xs bg-white/5 border border-white/10">
                <span className="font-mono text-white">{candidate.stock_code}</span>
                <span className="text-gray-400 ml-1">{candidate.stock_name}</span>
                <span
                  className={`ml-1 ${
                    candidate.source === "position"
                      ? "text-blue-400"
                      : candidate.source === "watchlist"
                        ? "text-yellow-400"
                        : "text-green-400"
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
          <h3 className="text-sm font-medium text-gray-300 mb-2">
            决策 ({run.decisions.length})
          </h3>
          <div className="space-y-2">
            {run.decisions.map((decision, index) => {
              const isBuy = decision.action === "buy" || decision.action === "add";
              return (
                <div key={index} className={`rounded-lg border p-3 ${
                  isBuy ? "bg-green-500/5 border-green-500/20" : "bg-red-500/5 border-red-500/20"
                }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono font-bold text-white">{decision.stock_code}</span>
                    <span className="text-gray-300">{decision.stock_name}</span>
                    <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                      isBuy ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                    }`}>
                      {decision.action}
                    </span>
                    {decision.confidence && (
                      <span className="text-xs text-gray-500">
                        信心: {(decision.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-300 grid grid-cols-2 md:grid-cols-4 gap-2">
                    {decision.price && <div>价格: <span className="text-white">{decision.price}</span></div>}
                    {decision.quantity && <div>数量: <span className="text-white">{decision.quantity}</span></div>}
                    {decision.take_profit && <div>止盈: <span className="text-green-400">{decision.take_profit}</span></div>}
                    {decision.stop_loss && <div>止损: <span className="text-red-400">{decision.stop_loss}</span></div>}
                  </div>
                  {decision.reasoning && (
                    <div className="text-xs text-gray-400 mt-1">{decision.reasoning}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {run.thinking_process && (
        <details className="group">
          <summary className="text-sm font-medium text-gray-300 cursor-pointer hover:text-white">
            推理摘要 ▸
          </summary>
          <pre className="mt-2 rounded bg-white/5 p-3 text-xs text-gray-400 whitespace-pre-wrap overflow-hidden">
            {typeof run.thinking_process === "string"
              ? run.thinking_process.slice(0, 800)
              : JSON.stringify(run.thinking_process, null, 1)?.slice(0, 800)}
          </pre>
        </details>
      )}

      {run.analysis_results && run.analysis_results.length > 0 && (
        <details className="group">
          <summary className="text-sm font-medium text-gray-300 cursor-pointer hover:text-white">
            分析详情 ({run.analysis_results.length} 只) ▸
          </summary>
          <div className="mt-2 space-y-2 max-h-96 overflow-y-auto">
            {run.analysis_results.map((analysis, index) => (
              <div key={index} className="bg-white/5 rounded p-2 text-xs">
                <div className="font-mono text-white mb-1">{analysis.stock_code} {analysis.stock_name}</div>
                {analysis.error ? (
                  <div className="text-red-400">{analysis.error}</div>
                ) : (
                  <pre className="text-gray-400 whitespace-pre-wrap overflow-hidden max-h-32">
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
