import { BrainRun } from "../types";

interface AgentStatePanelProps {
  run: BrainRun;
}

export default function AgentStatePanel({ run }: AgentStatePanelProps) {
  return (
    <>
      <div className="flex items-center gap-4 text-sm text-gray-400">
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
    </>
  );
}
