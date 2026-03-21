import { BrainRun } from "../types";

interface DecisionRunPanelProps {
  run: BrainRun;
}

export default function DecisionRunPanel({ run }: DecisionRunPanelProps) {
  return (
    <>
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
    </>
  );
}
