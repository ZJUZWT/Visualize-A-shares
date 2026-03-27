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
    <section className="rounded-[20px] border border-black/10 bg-white/80 p-5 shadow-[0_2px_12px_rgba(15,23,42,0.06)] space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">当前状态</h2>
          <p className="text-xs text-slate-400 mt-1">
            宠物对市场的理解和仓位策略快照
          </p>
        </div>
        {state?.updated_at && (
          <span className="text-xs text-slate-400">
            更新: {new Date(state.updated_at).toLocaleString()}
          </span>
        )}
      </div>

      {loading && !state ? (
        <div className="text-sm text-slate-400">加载状态中...</div>
      ) : error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-600">
          {error}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-slate-50 p-3">
              <div className="text-xs text-slate-400">仓位水平</div>
              <div className="mt-1 text-sm font-medium text-slate-900">{renderValue(state?.position_level)}</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <div className="text-xs text-slate-400">来源 Run</div>
              <div className="mt-1 text-sm font-mono text-slate-900">
                {state?.source_run_id || run?.id || "未关联"}
              </div>
            </div>
          </div>

          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-xs text-slate-400 mb-2">市场观点</div>
            {marketViewEntries.length === 0 ? (
              <div className="text-sm text-slate-400">暂无市场观点</div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {marketViewEntries.map(([key, value]) => (
                  <span key={key} className="rounded-lg border border-black/10 bg-white px-2 py-1 text-xs text-slate-500">
                    {key}: <span className="font-medium text-slate-900">{renderValue(value)}</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-slate-50 p-3">
              <div className="text-xs text-slate-400 mb-2">行业偏好</div>
              {sectorPreferences.length === 0 ? (
                <div className="text-sm text-slate-400">暂无行业偏好</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {sectorPreferences.map((item, index) => (
                    <span key={index} className="rounded-lg border border-black/10 bg-white px-2 py-1 text-xs text-slate-600">
                      {renderValue(item)}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-xl bg-slate-50 p-3">
              <div className="text-xs text-slate-400 mb-2">风险提醒</div>
              {riskAlerts.length === 0 ? (
                <div className="text-sm text-slate-400">暂无风险提醒</div>
              ) : (
                <div className="space-y-2">
                  {riskAlerts.map((item, index) => (
                    <div key={index} className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-700">
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
