import { AgentState, BrainRun } from "../types";

interface AgentStatePanelProps {
  state: AgentState | null;
  run: BrainRun | null;
  loading: boolean;
  error: string | null;
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

export default function AgentStatePanel({ state, run, loading, error }: AgentStatePanelProps) {
  const marketViewEntries = state?.market_view ? Object.entries(state.market_view) : [];
  const sectorPreferences = state?.sector_preferences ?? [];
  const riskAlerts = state?.risk_alerts ?? [];

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-gray-200">当前状态</h2>
          <p className="text-xs text-gray-500 mt-1">
            读取 `/api/v1/agent/state`，展示稳定状态快照。
          </p>
        </div>
        {state?.updated_at && (
          <span className="text-xs text-gray-500">
            更新: {new Date(state.updated_at).toLocaleString()}
          </span>
        )}
      </div>

      {loading && !state ? (
        <div className="text-sm text-gray-500">加载状态中...</div>
      ) : error ? (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500">仓位水平</div>
              <div className="mt-1 text-sm text-white">{renderValue(state?.position_level)}</div>
            </div>
            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500">来源 Run</div>
              <div className="mt-1 text-sm text-white font-mono">
                {state?.source_run_id || run?.id || "未关联"}
              </div>
            </div>
          </div>

          <div className="rounded-lg bg-white/5 p-3">
            <div className="text-xs text-gray-500 mb-2">市场观点</div>
            {marketViewEntries.length === 0 ? (
              <div className="text-sm text-gray-400">暂无市场观点</div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {marketViewEntries.map(([key, value]) => (
                  <span key={key} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                    {key}: <span className="text-white">{renderValue(value)}</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500 mb-2">行业偏好</div>
              {sectorPreferences.length === 0 ? (
                <div className="text-sm text-gray-400">暂无行业偏好</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {sectorPreferences.map((item, index) => (
                    <span key={index} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                      {renderValue(item)}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-lg bg-white/5 p-3">
              <div className="text-xs text-gray-500 mb-2">风险提醒</div>
              {riskAlerts.length === 0 ? (
                <div className="text-sm text-gray-400">暂无风险提醒</div>
              ) : (
                <div className="space-y-2">
                  {riskAlerts.map((item, index) => (
                    <div key={index} className="rounded border border-yellow-500/20 bg-yellow-500/10 px-2 py-1 text-xs text-yellow-100">
                      {renderValue(item)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
