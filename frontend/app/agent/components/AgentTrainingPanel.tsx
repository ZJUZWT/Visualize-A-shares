import type { AgentVerificationSuiteResult } from "../types";

interface AgentTrainingPanelProps {
  runningMode: "default" | "smoke" | null;
  result: AgentVerificationSuiteResult | null;
  error: string | null;
  onRunDefault: () => void;
  onRunSmoke: () => void;
}

function renderMetric(label: string, value: string) {
  return (
    <div className="rounded-2xl border border-black/10 bg-white/80 p-4">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-2 text-sm font-medium text-slate-900">{value}</div>
    </div>
  );
}

export default function AgentTrainingPanel({
  runningMode,
  result,
  error,
  onRunDefault,
  onRunSmoke,
}: AgentTrainingPanelProps) {
  const summary = (result?.backtest?.summary ?? {}) as Record<string, unknown>;
  const verification = (result?.demo_verification ?? {}) as Record<string, unknown>;

  return (
    <section className="rounded-[28px] border border-black/10 bg-[linear-gradient(180deg,#fff7e6_0%,#fffdf7_100%)] p-5 shadow-[0_24px_72px_rgba(15,23,42,0.12)]">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.25em] text-slate-500">Training Console</div>
          <h2 className="mt-2 text-2xl font-semibold text-slate-900">训练与闭环验收</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            跑完整 suite 或稳定 smoke，检查它有没有学到东西、有没有真的跑通。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onRunDefault}
            disabled={runningMode !== null}
            className="rounded-2xl bg-[#1d4ed8] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#1e40af] disabled:cursor-wait disabled:opacity-60"
          >
            {runningMode === "default" ? "训练中..." : "Run Training Suite"}
          </button>
          <button
            type="button"
            onClick={onRunSmoke}
            disabled={runningMode !== null}
            className="rounded-2xl border border-black/10 bg-white px-4 py-2.5 text-sm font-medium text-slate-900 transition hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
          >
            {runningMode === "smoke" ? "Smoke 中..." : "Run Smoke"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!result ? (
        <div className="mt-4 rounded-2xl border border-dashed border-black/10 bg-white/50 p-5 text-sm text-slate-500">
          还没有训练结果。先跑一次 suite 或 smoke，再观察 review、memory 和回测表现。
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {renderMetric("模式", result.mode === "smoke" ? "Smoke" : "Training")}
            {renderMetric("总状态", String(result.overall_status).toUpperCase())}
            {renderMetric("Verification", String(verification.verification_status ?? "--"))}
            {renderMetric("交易数", String(summary.trade_count ?? "--"))}
            {renderMetric("复盘数", String(summary.review_count ?? "--"))}
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
            <div className="rounded-2xl border border-black/10 bg-white/80 p-4">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">训练摘要</div>
              <div className="mt-3 text-sm leading-6 text-slate-700">
                verification run:
                <span className="ml-2 font-mono text-slate-950">
                  {String(result.evidence?.verification_run_id ?? "--")}
                </span>
              </div>
              <div className="mt-2 text-sm leading-6 text-slate-700">
                backtest run:
                <span className="ml-2 font-mono text-slate-950">
                  {String(result.evidence?.backtest_run_id ?? "--")}
                </span>
              </div>
              <div className="mt-2 text-sm leading-6 text-slate-700">
                next actions:
                <span className="ml-2 text-slate-950">
                  {result.next_actions.length > 0 ? result.next_actions.join(" / ") : "none"}
                </span>
              </div>
            </div>

            <div className="rounded-2xl border border-black/10 bg-[#1f2937] p-4 text-white">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Memory Delta</div>
              <div className="mt-3 grid gap-2 text-sm text-slate-100">
                <div>added: {String(summary.memory_added ?? "--")}</div>
                <div>updated: {String(summary.memory_updated ?? "--")}</div>
                <div>retired: {String(summary.memory_retired ?? "--")}</div>
                <div>backtest: {String(result.backtest?.status ?? "--")}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
