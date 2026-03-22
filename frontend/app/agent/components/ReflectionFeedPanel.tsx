import { ReflectionFeedItem } from "../types";

interface ReflectionFeedPanelProps {
  loading: boolean;
  error: string | null;
  items: ReflectionFeedItem[];
}

function isPercentMetric(key: string) {
  return key.includes("rate") || key.endsWith("_pct");
}

function renderMetricValue(key: string, value: number | string | null) {
  if (value === null || value === "") {
    return "--";
  }
  if (typeof value === "number") {
    if (isPercentMetric(key)) {
      const normalized = Math.abs(value) <= 1 ? value * 100 : value;
      return `${normalized.toFixed(2)}%`;
    }
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return value;
}

export default function ReflectionFeedPanel({
  loading,
  error,
  items,
}: ReflectionFeedPanelProps) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-medium text-gray-200">反思记录</h2>
        <p className="mt-1 text-xs text-gray-500">
          来自 `/api/v1/agent/reflections` 的反思 feed，按时间倒序展示。
        </p>
      </div>

      {loading ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          加载反思记录中...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          暂无反思记录
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <article key={item.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm text-white">{item.summary || "未提供摘要"}</div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                    <span className="rounded border border-white/10 px-2 py-0.5">
                      {item.kind || "unknown"}
                    </span>
                    <span>{item.date || "--"}</span>
                  </div>
                </div>
              </div>

              {Object.keys(item.metrics).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(item.metrics).map(([key, value]) => (
                    <span key={key} className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                      {key}: <span className="text-white">{renderMetricValue(key, value)}</span>
                    </span>
                  ))}
                </div>
              )}

              {item.details && Object.keys(item.details).length > 0 && (
                <details className="mt-3 group">
                  <summary className="cursor-pointer text-xs text-gray-400 hover:text-white">
                    详细字段 ▸
                  </summary>
                  <pre className="mt-2 rounded bg-white/5 p-3 text-xs text-gray-300 whitespace-pre-wrap overflow-hidden">
                    {JSON.stringify(item.details, null, 2)}
                  </pre>
                </details>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
