import { StrategyHistoryEntry } from "../types";

interface StrategyHistoryPanelProps {
  loading: boolean;
  error: string | null;
  items: StrategyHistoryEntry[];
}

function renderValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "--";
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

export default function StrategyHistoryPanel({
  loading,
  error,
  items,
}: StrategyHistoryPanelProps) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-medium text-gray-200">策略演进</h2>
        <p className="mt-1 text-xs text-gray-500">
          每次决策后的策略状态变化时间线
        </p>
      </div>

      {loading ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          加载策略历史中...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          暂无策略历史
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <article key={item.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-xs text-white">{item.run_id || "run:unknown"}</span>
                <span className="text-xs text-gray-500">{item.occurred_at || "--"}</span>
              </div>

              <div className="mt-3 grid gap-2 text-xs text-gray-400">
                <div>仓位水平: <span className="text-white">{item.position_level || "--"}</span></div>
                {item.market_view && (
                  <div>市场观点: <span className="text-white">{renderValue(item.market_view)}</span></div>
                )}
              </div>

              <div className="mt-3 space-y-2">
                <div>
                  <div className="mb-1 text-xs text-gray-500">行业偏好</div>
                  {item.sector_preferences && item.sector_preferences.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {item.sector_preferences.map((sector, index) => (
                        <span key={index} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                          {renderValue(sector)}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-gray-500">暂无行业偏好</div>
                  )}
                </div>

                <div>
                  <div className="mb-1 text-xs text-gray-500">风险提醒</div>
                  {item.risk_alerts && item.risk_alerts.length > 0 ? (
                    <div className="space-y-1">
                      {item.risk_alerts.map((risk, index) => (
                        <div key={index} className="rounded border border-yellow-500/20 bg-yellow-500/10 px-2 py-1 text-xs text-yellow-100">
                          {renderValue(risk)}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-gray-500">暂无风险提醒</div>
                  )}
                </div>
              </div>

              {Object.keys(item.execution_counters).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(item.execution_counters).map(([key, value]) => (
                    <span key={key} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                      {key}: <span className="text-white">{renderValue(value)}</span>
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
