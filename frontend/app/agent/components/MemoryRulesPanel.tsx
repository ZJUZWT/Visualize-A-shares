import { MemoryRule } from "../types";

interface MemoryRulesPanelProps {
  loading: boolean;
  error: string | null;
  rules: MemoryRule[];
  statusFilter: "all" | "active" | "retired";
  onStatusFilterChange: (value: "all" | "active" | "retired") => void;
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return `${(value * 100).toFixed(0)}%`;
}

export default function MemoryRulesPanel({
  loading,
  error,
  rules,
  statusFilter,
  onStatusFilterChange,
}: MemoryRulesPanelProps) {
  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-gray-200">经验规则</h2>
          <p className="mt-1 text-xs text-gray-500">
            只读展示 memory rules 的状态、置信度和验证情况。
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-white/10 bg-white/5 p-1 text-xs">
          {(["all", "active", "retired"] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onStatusFilterChange(value)}
              className={`rounded-md px-3 py-1 transition-colors ${
                statusFilter === value
                  ? "bg-white/15 text-white"
                  : "text-gray-400 hover:bg-white/10 hover:text-white"
              }`}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          加载经验规则中...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : rules.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          暂无经验规则
        </div>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {rules.map((rule) => (
            <div key={rule.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="text-sm text-white whitespace-pre-wrap">{rule.rule_text}</div>
                <span className={`rounded px-2 py-0.5 text-xs ${
                  rule.status === "active"
                    ? "bg-green-500/15 text-green-300"
                    : "bg-red-500/15 text-red-300"
                }`}>
                  {rule.status || "unknown"}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-400">
                <span className="rounded border border-white/10 px-2 py-1">{rule.category || "uncategorized"}</span>
                {rule.source_run_id && (
                  <span className="rounded border border-white/10 px-2 py-1 font-mono">
                    {rule.source_run_id}
                  </span>
                )}
              </div>
              <div className="mt-4">
                <div className="mb-1 flex items-center justify-between text-xs text-gray-400">
                  <span>置信度</span>
                  <span className="text-white">{formatPercent(rule.confidence)}</span>
                </div>
                <div className="h-2 rounded-full bg-white/10">
                  <div
                    className="h-2 rounded-full bg-green-400"
                    style={{ width: `${Math.max(0, Math.min(100, (rule.confidence ?? 0) * 100))}%` }}
                  />
                </div>
              </div>
              <div className="mt-3 grid gap-2 text-xs text-gray-400 sm:grid-cols-2">
                <div>验证次数: <span className="text-white">{rule.verify_count ?? 0}</span></div>
                <div>验证胜场: <span className="text-white">{rule.verify_win ?? 0}</span></div>
                <div>创建时间: <span className="text-white">{rule.created_at || "--"}</span></div>
                <div>退役时间: <span className="text-white">{rule.retired_at || "--"}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
