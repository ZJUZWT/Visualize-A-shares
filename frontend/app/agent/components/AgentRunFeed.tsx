import { BrainRun } from "../types";

interface AgentRunFeedProps {
  loading: boolean;
  runs: BrainRun[];
  selectedRunId: string | null;
  onSelectRun: (run: BrainRun) => void;
  statusColor: Record<string, string>;
}

export default function AgentRunFeed({
  loading,
  runs,
  selectedRunId,
  onSelectRun,
  statusColor,
}: AgentRunFeedProps) {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-3 text-xs text-gray-400 font-medium">运行记录</div>
      {loading ? (
        <div className="text-gray-500 text-center py-4 text-sm">加载中...</div>
      ) : runs.length === 0 ? (
        <div className="text-gray-500 text-center py-4 text-sm">暂无运行记录</div>
      ) : (
        runs.map((run) => (
          <button
            key={run.id}
            onClick={() => onSelectRun(run)}
            className={`w-full text-left px-3 py-2 text-sm border-b border-white/5 transition-colors ${
              selectedRunId === run.id ? "bg-white/10" : "hover:bg-white/5"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-gray-300">
                {new Date(run.started_at).toLocaleDateString()}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-xs ${statusColor[run.status] || ""}`}>
                {run.status}
              </span>
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {run.run_type === "manual" ? "手动" : "定时"}
              {run.decisions && ` · ${run.decisions.length} 个决策`}
            </div>
          </button>
        ))
      )}
    </div>
  );
}
