"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import { FEEDBACK_ISSUE_LABELS } from "@/lib/expertFeedback";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useExpertStore } from "@/stores/useExpertStore";
import type { ExpertFeedbackDetail, ExpertFeedbackSummary } from "@/types/expert";

export default function AdminFeedbackPage() {
  const userId = useConnectionStore((state) => state.userId);
  const {
    listAdminFeedbackReports,
    getAdminFeedbackReport,
    resolveAdminFeedbackReport,
  } = useExpertStore();
  const [reports, setReports] = useState<ExpertFeedbackSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ExpertFeedbackDetail | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [unresolvedOnly, setUnresolvedOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolveBusy, setResolveBusy] = useState(false);

  const loadReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAdminFeedbackReports(unresolvedOnly, 100);
      setReports(data);
      if (data.length === 0) {
        setSelectedId(null);
        setDetail(null);
        setResolutionNote("");
        return;
      }
      const nextSelectedId = selectedId && data.some((item) => item.id === selectedId)
        ? selectedId
        : data[0].id;
      setSelectedId(nextSelectedId);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "反馈列表加载失败");
      setReports([]);
      setSelectedId(null);
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [listAdminFeedbackReports, selectedId, unresolvedOnly]);

  const loadDetail = useCallback(async (feedbackId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const nextDetail = await getAdminFeedbackReport(feedbackId);
      setDetail(nextDetail);
      setResolutionNote(nextDetail?.resolution_note ?? "");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "反馈详情加载失败");
      setDetail(null);
      setResolutionNote("");
    } finally {
      setDetailLoading(false);
    }
  }, [getAdminFeedbackReport]);

  useEffect(() => {
    if (userId === "Admin") {
      loadReports();
    } else {
      setLoading(false);
    }
  }, [loadReports, userId]);

  useEffect(() => {
    if (selectedId && userId === "Admin") {
      loadDetail(selectedId);
    }
  }, [loadDetail, selectedId, userId]);

  const selectedSummary = useMemo(
    () => reports.find((item) => item.id === selectedId) ?? null,
    [reports, selectedId],
  );

  const handleResolve = useCallback(async () => {
    if (!detail) return;
    setResolveBusy(true);
    setError(null);
    try {
      await resolveAdminFeedbackReport(detail.id, resolutionNote);
      await loadReports();
      await loadDetail(detail.id);
    } catch (resolveError) {
      setError(resolveError instanceof Error ? resolveError.message : "反馈处理失败");
    } finally {
      setResolveBusy(false);
    }
  }, [detail, loadDetail, loadReports, resolutionNote, resolveAdminFeedbackReport]);

  if (userId !== "Admin") {
    return (
      <main
        className="debate-dark relative h-screen flex flex-col"
        style={{
          marginLeft: 48,
          width: "calc(100vw - 48px)",
          background: "var(--bg-primary)",
        }}
      >
        <NavSidebar />
        <div className="flex flex-1 items-center justify-center px-6">
          <div className="max-w-md rounded-[28px] border border-red-500/20 bg-red-500/5 p-8 text-center">
            <div className="text-sm font-semibold text-red-500">仅 Admin 可访问反馈后台</div>
            <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
              请先使用管理员账号登录，再查看反馈列表和上下文详情。
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main
      className="debate-dark relative h-screen flex flex-col overflow-hidden"
      style={{
        marginLeft: 48,
        width: "calc(100vw - 48px)",
        background: "var(--bg-primary)",
      }}
    >
      <NavSidebar />

      <div className="flex h-full flex-col">
        <div className="border-b border-[var(--border)] px-5 py-4">
          <div className="text-[11px] uppercase tracking-[0.28em] text-[var(--text-tertiary)]">
            Admin Console
          </div>
          <div className="mt-2 flex items-center gap-3">
            <div>
              <h1 className="text-2xl font-semibold text-[var(--text-primary)]">
                Expert 反馈后台
              </h1>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                查看回复截断、澄清交互和续写误判问题的完整上下文。
              </p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={() => setUnresolvedOnly(true)}
                className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
                  unresolvedOnly
                    ? "bg-[var(--text-primary)] text-[var(--bg-primary)]"
                    : "border border-[var(--border)] text-[var(--text-secondary)]"
                }`}
              >
                未处理
              </button>
              <button
                type="button"
                onClick={() => setUnresolvedOnly(false)}
                className={`rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
                  !unresolvedOnly
                    ? "bg-[var(--text-primary)] text-[var(--bg-primary)]"
                    : "border border-[var(--border)] text-[var(--text-secondary)]"
                }`}
              >
                全部
              </button>
            </div>
          </div>
          {error && (
            <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-500">
              {error}
            </div>
          )}
        </div>

        <div className="grid flex-1 grid-cols-[360px_minmax(0,1fr)] overflow-hidden">
          <aside className="border-r border-[var(--border)] overflow-y-auto p-4">
            {loading ? (
              <div className="py-12 text-center text-sm text-[var(--text-tertiary)]">加载中...</div>
            ) : reports.length === 0 ? (
              <div className="py-12 text-center text-sm text-[var(--text-tertiary)]">暂无反馈</div>
            ) : (
              <div className="space-y-2">
                {reports.map((report) => (
                  <button
                    key={report.id}
                    type="button"
                    onClick={() => setSelectedId(report.id)}
                    className={`w-full rounded-2xl border px-4 py-3 text-left transition-colors ${
                      report.id === selectedId
                        ? "border-red-500/30 bg-red-500/8"
                        : "border-[var(--border)] bg-[var(--bg-secondary)] hover:border-[var(--border-hover)]"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold text-[var(--text-primary)]">
                          {FEEDBACK_ISSUE_LABELS[report.issue_type]}
                        </div>
                        <div className="mt-1 text-xs text-[var(--text-secondary)]">
                          {report.expert_type} · {report.report_source} · {report.message_status}
                        </div>
                      </div>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                          report.resolved_at
                            ? "bg-emerald-500/12 text-emerald-500"
                            : "bg-red-500/12 text-red-500"
                        }`}
                      >
                        {report.resolved_at ? "已处理" : "待处理"}
                      </span>
                    </div>
                    {report.user_note && (
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                        {report.user_note}
                      </p>
                    )}
                    <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">
                      {report.created_at}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </aside>

          <section className="overflow-y-auto p-5">
            {!selectedSummary ? (
              <div className="flex h-full items-center justify-center text-sm text-[var(--text-tertiary)]">
                选择一条反馈查看详情
              </div>
            ) : detailLoading || !detail ? (
              <div className="py-12 text-center text-sm text-[var(--text-tertiary)]">详情加载中...</div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-secondary)] p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-red-500/12 px-2.5 py-1 text-xs font-medium text-red-500">
                      {FEEDBACK_ISSUE_LABELS[detail.issue_type]}
                    </span>
                    <span className="rounded-full bg-[var(--bg-primary)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
                      {detail.expert_type}
                    </span>
                    <span className="rounded-full bg-[var(--bg-primary)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
                      {detail.report_source}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-3 text-sm text-[var(--text-secondary)]">
                    <div>反馈用户：{detail.user_id}</div>
                    <div>会话 ID：{detail.session_id}</div>
                    <div>消息 ID：{detail.message_id}</div>
                    <div>创建时间：{detail.created_at}</div>
                    <div>处理状态：{detail.resolved_at ? `已处理 · ${detail.resolved_at}` : "未处理"}</div>
                  </div>
                  {detail.user_note && (
                    <div className="mt-4 rounded-2xl bg-[var(--bg-primary)] p-4">
                      <div className="text-xs font-semibold text-[var(--text-secondary)]">用户备注</div>
                      <div className="mt-2 text-sm leading-6 text-[var(--text-primary)]">{detail.user_note}</div>
                    </div>
                  )}
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <article className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-secondary)] p-5">
                    <div className="text-xs font-semibold text-[var(--text-secondary)]">对应用户问题</div>
                    <div className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--text-primary)]">
                      {detail.user_message || "（空）"}
                    </div>
                  </article>

                  <article className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-secondary)] p-5">
                    <div className="text-xs font-semibold text-[var(--text-secondary)]">Assistant 原始输出</div>
                    <div className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--text-primary)]">
                      {detail.assistant_content || "（空）"}
                    </div>
                  </article>
                </div>

                <article className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-secondary)] p-5">
                  <div className="text-xs font-semibold text-[var(--text-secondary)]">thinking_json</div>
                  <pre className="mt-3 overflow-x-auto rounded-2xl bg-[var(--bg-primary)] p-4 text-xs leading-6 text-[var(--text-primary)]">
                    {JSON.stringify(detail.thinking_json, null, 2)}
                  </pre>
                </article>

                <article className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-secondary)] p-5">
                  <div className="text-xs font-semibold text-[var(--text-secondary)]">context_json</div>
                  <pre className="mt-3 overflow-x-auto rounded-2xl bg-[var(--bg-primary)] p-4 text-xs leading-6 text-[var(--text-primary)]">
                    {JSON.stringify(detail.context_json, null, 2)}
                  </pre>
                </article>

                <article className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-secondary)] p-5">
                  <div className="text-xs font-semibold text-[var(--text-secondary)]">处理记录</div>
                  <textarea
                    value={resolutionNote}
                    onChange={(event) => setResolutionNote(event.target.value)}
                    rows={4}
                    placeholder="记录定位结果、复现原因或修复版本"
                    className="mt-3 w-full resize-none rounded-2xl border border-[var(--border)] bg-[var(--bg-primary)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none"
                  />
                  <div className="mt-3 flex items-center gap-3">
                    <button
                      type="button"
                      disabled={resolveBusy}
                      onClick={handleResolve}
                      className="rounded-xl bg-[var(--text-primary)] px-4 py-2 text-sm font-medium text-[var(--bg-primary)] transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      标记已处理
                    </button>
                    {detail.resolver && (
                      <span className="text-xs text-[var(--text-secondary)]">
                        处理人：{detail.resolver}
                      </span>
                    )}
                  </div>
                </article>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
