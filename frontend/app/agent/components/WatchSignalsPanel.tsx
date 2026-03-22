import type {
  WakeSummary,
  WatchSignal,
  WatchSignalFormState,
} from "../types";

interface WatchSignalsPanelProps {
  loading: boolean;
  error: string | null;
  mutationError: string | null;
  signals: WatchSignal[];
  summary: WakeSummary;
  form: WatchSignalFormState;
  submitting: boolean;
  updatingSignalId: string | null;
  onFormChange: (field: keyof WatchSignalFormState, value: string) => void;
  onSubmit: () => void;
  onStatusChange: (signalId: string, status: "triggered" | "cancelled") => void;
}

const SUMMARY_CARDS: Array<{ key: keyof WakeSummary; label: string }> = [
  { key: "total", label: "总信号" },
  { key: "watching", label: "观察中" },
  { key: "triggered", label: "已触发" },
  { key: "inactive", label: "非活跃" },
];

function renderEvidenceSummary(signal: WatchSignal) {
  if (signal.trigger_evidence.length === 0) {
    return "暂无触发证据";
  }
  return signal.trigger_evidence
    .map((item) => item.summary || item.title || item.type || "--")
    .join("；");
}

export default function WatchSignalsPanel({
  loading,
  error,
  mutationError,
  signals,
  summary,
  form,
  submitting,
  updatingSignalId,
  onFormChange,
  onSubmit,
  onStatusChange,
}: WatchSignalsPanelProps) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-medium text-gray-200">Wake Signals</h2>
        <p className="mt-1 text-xs text-gray-500">
          展示 Agent 正在等待的观察条件，并允许最小人工维护。
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {SUMMARY_CARDS.map((card) => (
          <div key={card.key} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-xs text-gray-500">{card.label}</div>
            <div className="mt-1 text-sm text-white">{summary[card.key]}</div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <div className="mb-3 text-sm font-medium text-gray-200">新增观察信号</div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs text-gray-400">
            <span>股票代码</span>
            <input
              value={form.stock_code}
              onChange={(event) => onFormChange("stock_code", event.target.value)}
              placeholder="600519"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-white/30"
            />
          </label>
          <label className="space-y-1 text-xs text-gray-400">
            <span>行业</span>
            <input
              value={form.sector}
              onChange={(event) => onFormChange("sector", event.target.value)}
              placeholder="白酒"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-white/30"
            />
          </label>
          <label className="space-y-1 text-xs text-gray-400 sm:col-span-2">
            <span>信号描述</span>
            <input
              value={form.signal_description}
              onChange={(event) => onFormChange("signal_description", event.target.value)}
              placeholder="渠道价企稳"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-white/30"
            />
          </label>
          <label className="space-y-1 text-xs text-gray-400 sm:col-span-2">
            <span>关键词（逗号分隔）</span>
            <input
              value={form.keywords}
              onChange={(event) => onFormChange("keywords", event.target.value)}
              placeholder="渠道, 价格, 库存"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-white/30"
            />
          </label>
          <label className="space-y-1 text-xs text-gray-400 sm:col-span-2">
            <span>触发后动作</span>
            <textarea
              value={form.if_triggered}
              onChange={(event) => onFormChange("if_triggered", event.target.value)}
              rows={3}
              placeholder="重新评估仓位并复核盈利预测"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-white/30"
            />
          </label>
          <label className="space-y-1 text-xs text-gray-400 sm:col-span-2">
            <span>周期背景</span>
            <textarea
              value={form.cycle_context}
              onChange={(event) => onFormChange("cycle_context", event.target.value)}
              rows={3}
              placeholder="去库存尾声，等待价格信号确认"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition focus:border-white/30"
            />
          </label>
        </div>

        {mutationError && (
          <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
            {mutationError}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              submitting
                ? "cursor-wait bg-blue-500/20 text-blue-400"
                : "bg-white/10 text-white hover:bg-white/20"
            }`}
          >
            {submitting ? "提交中..." : "新增信号"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          加载观察信号中...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : signals.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          暂无观察信号
        </div>
      ) : (
        <div className="space-y-3">
          {signals.map((signal) => (
            <article key={signal.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm text-white">
                    <span className="font-mono">{signal.stock_code || "--"}</span>
                    {signal.sector && <span className="ml-2 text-gray-400">{signal.sector}</span>}
                  </div>
                  <div className="mt-1 text-sm text-gray-200">{signal.signal_description}</div>
                </div>
                <span className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300">
                  {signal.status || "unknown"}
                </span>
              </div>

              {signal.keywords.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {signal.keywords.map((keyword) => (
                    <span
                      key={`${signal.id}-${keyword}`}
                      className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-3 grid gap-2 text-xs text-gray-400 sm:grid-cols-2">
                <div>检查引擎: <span className="text-white">{signal.check_engine || "--"}</span></div>
                <div>来源 run: <span className="font-mono text-white">{signal.source_run_id || "--"}</span></div>
                <div>创建时间: <span className="text-white">{signal.created_at || "--"}</span></div>
                <div>触发时间: <span className="text-white">{signal.triggered_at || "--"}</span></div>
              </div>

              {signal.if_triggered && (
                <div className="mt-3 rounded-lg bg-white/5 p-3 text-xs text-gray-300 whitespace-pre-wrap">
                  <div className="mb-1 text-gray-500">触发后动作</div>
                  {signal.if_triggered}
                </div>
              )}

              {signal.cycle_context && (
                <div className="mt-3 rounded-lg bg-white/5 p-3 text-xs text-gray-300 whitespace-pre-wrap">
                  <div className="mb-1 text-gray-500">周期背景</div>
                  {signal.cycle_context}
                </div>
              )}

              <div className="mt-3 rounded-lg bg-white/5 p-3 text-xs text-gray-300">
                <div className="mb-1 text-gray-500">触发证据</div>
                {renderEvidenceSummary(signal)}
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={updatingSignalId === signal.id || signal.status === "triggered"}
                  onClick={() => onStatusChange(signal.id, "triggered")}
                  className="rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-1.5 text-xs text-green-200 transition hover:bg-green-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {updatingSignalId === signal.id ? "更新中..." : "标记已触发"}
                </button>
                <button
                  type="button"
                  disabled={updatingSignalId === signal.id || signal.status === "cancelled"}
                  onClick={() => onStatusChange(signal.id, "cancelled")}
                  className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-gray-300 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  取消信号
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
