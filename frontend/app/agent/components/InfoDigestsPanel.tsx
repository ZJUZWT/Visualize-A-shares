import type { InfoDigest, WakeDigestMode } from "../types";

interface InfoDigestsPanelProps {
  loading: boolean;
  error: string | null;
  items: InfoDigest[];
  mode: WakeDigestMode;
  selectedRunId: string | null;
  onModeChange: (value: WakeDigestMode) => void;
}

export default function InfoDigestsPanel({
  loading,
  error,
  items,
  mode,
  selectedRunId,
  onModeChange,
}: InfoDigestsPanelProps) {
  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-gray-200">Info Digests</h2>
          <p className="mt-1 text-xs text-gray-500">
            展示 data-hunger 对消息面的结构化消化结果，默认优先绑定当前选中 run。
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-white/10 bg-white/5 p-1 text-xs">
          {([
            { value: "selected_run", label: "当前 run" },
            { value: "recent", label: "最近摘要" },
          ] as const).map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onModeChange(option.value)}
              className={`rounded-md px-3 py-1 transition-colors ${
                mode === option.value
                  ? "bg-white/15 text-white"
                  : "text-gray-400 hover:bg-white/10 hover:text-white"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-gray-400">
        当前上下文:
        <span className="ml-2 font-mono text-white">{selectedRunId || "未选择 run"}</span>
        <span className="ml-3 text-gray-500">
          {mode === "selected_run" ? "优先展示该 run 关联摘要，不存在时回退到最近摘要。" : "直接展示最近摘要。"}
        </span>
      </div>

      {loading ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          加载信息摘要中...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-gray-500">
          暂无信息摘要
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((digest) => (
            <article key={digest.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm text-white">
                    <span className="font-mono">{digest.stock_code || "--"}</span>
                    <span className="ml-2 text-gray-400">{digest.digest_type || "digest"}</span>
                  </div>
                  <div className="mt-1 text-sm text-gray-200">{digest.summary || "未提供摘要"}</div>
                </div>
                <div className="text-right text-xs text-gray-500">
                  <div>{digest.impact_assessment || "--"}</div>
                  <div className="mt-1 font-mono">{digest.run_id || "run:unknown"}</div>
                </div>
              </div>

              <div className="mt-3 grid gap-2 text-xs text-gray-400 sm:grid-cols-2">
                <div>策略相关性: <span className="text-white">{digest.strategy_relevance || "--"}</span></div>
                <div>创建时间: <span className="text-white">{digest.created_at || "--"}</span></div>
              </div>

              {digest.key_evidence.length > 0 && (
                <div className="mt-3">
                  <div className="mb-2 text-xs text-gray-500">关键信号</div>
                  <div className="flex flex-wrap gap-2">
                    {digest.key_evidence.map((item) => (
                      <span
                        key={`${digest.id}-evidence-${item}`}
                        className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(digest.risk_flags.length > 0 || digest.missing_sources.length > 0) && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg bg-white/5 p-3">
                    <div className="mb-2 text-xs text-gray-500">风险提示</div>
                    {digest.risk_flags.length === 0 ? (
                      <div className="text-xs text-gray-400">暂无风险提示</div>
                    ) : (
                      <div className="space-y-1">
                        {digest.risk_flags.map((item) => (
                          <div key={`${digest.id}-risk-${item}`} className="text-xs text-yellow-100">
                            {item}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-lg bg-white/5 p-3">
                    <div className="mb-2 text-xs text-gray-500">缺失来源</div>
                    {digest.missing_sources.length === 0 ? (
                      <div className="text-xs text-gray-400">无</div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {digest.missing_sources.map((item) => (
                          <span
                            key={`${digest.id}-missing-${item}`}
                            className="rounded border border-white/10 px-2 py-1 text-xs text-gray-300"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
