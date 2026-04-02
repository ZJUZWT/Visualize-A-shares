"use client";

import { useState, useEffect, useCallback } from "react";
import type { ExpertMessage, ThinkingItem, ClarificationSelection, ClarificationOption, ExpertFeedbackIssueType } from "@/types/expert";
import { useExpertStore } from "@/stores/useExpertStore";
import { ThinkingPanel } from "./ThinkingPanel";
import { AlertCircle, RotateCw, CheckCircle2, ChevronDown, ChevronRight, Check, PlayCircle, AlertTriangle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  buildClarificationSelections,
  toggleClarificationOption,
  toggleClarificationSubChoice,
} from "@/lib/clarificationSelection";
import { buildExpertTradePlanPayload } from "@/lib/expertTradePlan";
import { splitByTradePlan, hasTradePlan } from "@/lib/parseTradePlan";
import {
  FEEDBACK_ISSUE_LABELS,
  defaultFeedbackIssueTypeForMessage,
  shouldOfferResumeCheck,
} from "@/lib/expertFeedback";
import { normalizePlanReview, normalizeSavedTradePlanCard } from "@/lib/planReview";
import TradePlanCard from "@/components/plans/TradePlanCard";
import { getApiBase, apiFetch } from "@/lib/api-base";

interface MessageBubbleProps {
  message: ExpertMessage;
  expertColor: string;
  expertIcon: string;
  expertName: string;
}

const FEEDBACK_ISSUE_OPTIONS: ExpertFeedbackIssueType[] = [
  "load_failed",
  "llm_truncated",
  "resume_misjudged_complete",
  "clarify_missing_options",
  "clarify_auto_advance",
  "clarify_subchoice_stuck",
  "other",
];

/** 单轮澄清卡片 — 支持单选 / 多选 / 子选项 */
function ClarificationCard({
  item,
  expertColor,
  isLastPending,
}: {
  item: Extract<ThinkingItem, { type: "clarification_request" }>;
  expertColor: string;
  /** 是否是最后一个 pending 的轮次（只有它可交互） */
  isLastPending: boolean;
}) {
  const { submitClarifications, pendingClarifications, activeExpert } = useExpertStore();
  const isPending = item.status === "pending";
  const canSubmit = isPending && isLastPending && !!pendingClarifications[activeExpert];
  const isResolved = item.status === "selected" || item.status === "skipped";
  const [expanded, setExpanded] = useState(!isResolved);
  const multiSelect = item.data.multi_select ?? false;

  // 多选模式本地状态：{ optionId: ClarificationSelection }
  const [selectedMap, setSelectedMap] = useState<Map<string, ClarificationSelection>>(new Map());
  // 子选项展开状态：哪个 option 的子选项正在展开
  const [expandedSubId, setExpandedSubId] = useState<string | null>(null);

  // 当选项被选中后自动折叠
  useEffect(() => {
    if (isResolved) {
      setExpanded(false);
    }
  }, [isResolved]);

  const roundLabel = item.round ?? item.data.round;

  const toggleOption = useCallback((option: ClarificationOption) => {
    if (!canSubmit) return;
    if (option.sub_choices && option.sub_choices.length > 0) {
      setExpandedSubId(prev => prev === option.id ? null : option.id);
      return;
    }
    setSelectedMap((prev) => toggleClarificationOption(prev, option, multiSelect));
  }, [canSubmit, multiSelect]);

  const selectSubChoice = useCallback((option: ClarificationOption, subId: string, subText: string) => {
    if (!canSubmit) return;
    setSelectedMap((prev) =>
      toggleClarificationSubChoice(prev, option, subId, subText, multiSelect),
    );
  }, [canSubmit, multiSelect]);

  const handleConfirmSelection = useCallback(() => {
    if (!canSubmit || selectedMap.size === 0) return;
    submitClarifications(buildClarificationSelections(selectedMap));
  }, [canSubmit, selectedMap, submitClarifications]);

  // 构建已选摘要文本
  const buildSelectedSummary = (): string => {
    if (item.status === "skipped") return "跳过，直接分析";
    // 多选模式
    if (item.selectedOptions && item.selectedOptions.length > 0) {
      return item.selectedOptions.map(s => {
        let text = `${s.label}`;
        if (s.sub_choice_text) text += `(${s.sub_choice_text})`;
        return text;
      }).join(" + ");
    }
    // 单选模式
    if (item.selectedOption) {
      let text = `${item.selectedOption.label}. ${item.selectedOption.title}`;
      if (item.selectedOption.sub_choice_text) {
        text += `（${item.selectedOption.sub_choice_text}）`;
      }
      return text;
    }
    return "";
  };

  // 选中后的摘要显示（折叠态）
  if (isResolved && !expanded) {
    const selectedLabel = buildSelectedSummary();
    return (
      <button
        onClick={() => setExpanded(true)}
        className="mb-2 flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-left transition-colors hover:border-[var(--accent)]/30 w-full"
      >
        <div
          className="h-5 w-5 shrink-0 rounded-md flex items-center justify-center text-[10px] text-white"
          style={{ backgroundColor: expertColor }}
        >
          ✓
        </div>
        <span className="text-xs text-[var(--text-secondary)] truncate">
          {roundLabel ? `第${roundLabel}轮 · ` : ""}分析方向：<span className="text-[var(--text-primary)] font-medium">{selectedLabel}</span>
        </span>
        <ChevronRight size={12} className="ml-auto shrink-0 text-[var(--text-tertiary)]" />
      </button>
    );
  }

  return (
    <div className="mb-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
      <div className="flex items-start gap-2">
        <div
          className="mt-0.5 h-6 w-6 shrink-0 rounded-lg flex items-center justify-center text-[11px] text-white"
          style={{ backgroundColor: expertColor }}
        >
          ?
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-semibold text-[var(--text-primary)]">
              {roundLabel ? `第${roundLabel}轮 · ` : ""}先确认分析方向{multiSelect ? "（可多选）" : ""}
            </p>
            {isResolved && (
              <button onClick={() => setExpanded(false)} className="text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]">
                <ChevronDown size={14} />
              </button>
            )}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-[var(--text-primary)]">
            {item.data.question_summary}
          </p>
          <div className="mt-3 grid gap-2">
            {item.data.options.map((option) => {
              const isSelectedSingle = item.selectedOption?.option_id === option.id;
              const isSelectedMulti = selectedMap.has(option.id);
              const isSelected = isResolved ? isSelectedSingle || (item.selectedOptions ?? []).some(s => s.option_id === option.id) : isSelectedMulti;
              const hasSubChoices = (option.sub_choices ?? []).length > 0;
              const isSubExpanded = expandedSubId === option.id;
              const currentSubChoiceId = selectedMap.get(option.id)?.sub_choice_id;

              return (
                <div key={option.id}>
                  <button
                    onClick={() => toggleOption(option)}
                    disabled={!canSubmit}
                    className={`w-full rounded-xl border px-3 py-2.5 text-left transition-all duration-150 ${
                      isSelected
                        ? "border-transparent text-white"
                        : "border-[var(--border)] bg-[var(--bg-primary)]/50 hover:border-[var(--border-hover)]"
                    } ${!canSubmit ? "opacity-70 cursor-default" : ""}`}
                    style={isSelected ? { backgroundColor: expertColor } : undefined}
                  >
                    <div className="flex items-center gap-2">
                      {multiSelect && canSubmit && (
                        <span className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[9px] ${
                          isSelected ? "border-white/40 bg-white/20 text-white" : "border-[var(--text-tertiary)]"
                        }`}>
                          {isSelected && <Check size={10} />}
                        </span>
                      )}
                      <span
                        className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                          isSelected ? "bg-white/20 text-white" : ""
                        }`}
                        style={isSelected ? undefined : { backgroundColor: expertColor + "20", color: expertColor }}
                      >
                        {option.label}
                      </span>
                      <span className={`text-sm font-medium ${isSelected ? "text-white" : "text-[var(--text-primary)]"}`}>{option.title}</span>
                      {hasSubChoices && (
                        <span className={`text-[10px] ml-1 ${isSelected ? "text-white/60" : "text-[var(--text-secondary)]"}`}>
                          {isSubExpanded ? "▾" : "▸"} 展开选项
                        </span>
                      )}
                      {isSelected && !hasSubChoices && <CheckCircle2 size={14} className="ml-auto text-white" />}
                      {isSelected && currentSubChoiceId && (
                        <span className="ml-auto text-xs text-white/80">
                          {selectedMap.get(option.id)?.sub_choice_text}
                        </span>
                      )}
                    </div>
                    <p className={`mt-1 text-xs leading-relaxed ${isSelected ? "text-white/80" : "text-[var(--text-secondary)]"}`}>
                      {option.description}
                    </p>
                  </button>

                  {/* 子选项展开区 */}
                  {hasSubChoices && isSubExpanded && canSubmit && (
                    <div className="ml-8 mt-1.5 mb-1 flex flex-wrap gap-1.5">
                      {(option.sub_choices ?? []).map((sc) => {
                        const isSubSelected = currentSubChoiceId === sc.id;
                        return (
                          <button
                            key={sc.id}
                            onClick={() => selectSubChoice(option, sc.id, sc.text)}
                            className={`rounded-full border px-3 py-1 text-xs font-medium transition-all ${
                              isSubSelected
                                ? "border-transparent text-white"
                                : "border-[var(--border)] hover:border-[var(--border-hover)] text-[var(--text-primary)]"
                            }`}
                            style={isSubSelected ? { backgroundColor: expertColor } : undefined}
                          >
                            {sc.label} {sc.text}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {canSubmit && (
            <button
              onClick={handleConfirmSelection}
              disabled={selectedMap.size === 0}
              className={`mt-3 rounded-xl border px-4 py-2 text-sm font-medium transition-all ${
                selectedMap.size > 0
                  ? "text-white border-transparent shadow-sm"
                  : "border-[var(--border)] text-[var(--text-secondary)] cursor-not-allowed opacity-50"
              }`}
              style={selectedMap.size > 0 ? { backgroundColor: expertColor } : undefined}
            >
              确认选择{selectedMap.size > 0 ? `（${selectedMap.size}项）` : ""}
            </button>
          )}

          <button
            onClick={() =>
              canSubmit &&
              submitClarifications([{
                option_id: item.data.skip_option.id,
                label: item.data.skip_option.label,
                title: item.data.skip_option.title,
                focus: item.data.skip_option.focus,
                skip: true,
              }])
            }
            disabled={!canSubmit}
            className={`mt-3 inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              !canSubmit ? "opacity-50 cursor-default" : "hover:border-[var(--border-hover)]"
            } ${item.status === "skipped" ? "" : "text-[var(--text-secondary)] border-[var(--border)]"}`}
            style={{
              borderColor: item.status === "skipped" ? expertColor : undefined,
              color: item.status === "skipped" ? expertColor : undefined,
            }}
          >
            {item.status === "skipped" ? "已选择：跳过，直接分析" : item.data.skip_option.title}
          </button>
        </div>
      </div>
    </div>
  );
}

/** 多轮澄清卡片组：遍历所有 clarification_request ThinkingItem */
function ClarificationCards({
  message,
  expertColor,
}: {
  message: ExpertMessage;
  expertColor: string;
}) {
  const clarificationItems = message.thinking.filter(
    (t): t is Extract<ThinkingItem, { type: "clarification_request" }> =>
      t.type === "clarification_request"
  );
  if (clarificationItems.length === 0) return null;

  // 找到最后一个 pending 的索引
  const lastPendingIdx = clarificationItems.findLastIndex((t) => t.status === "pending");

  return (
    <>
      {clarificationItems.map((item, idx) => (
        <ClarificationCard
          key={`clarify-${idx}`}
          item={item}
          expertColor={expertColor}
          isLastPending={idx === lastPendingIdx}
        />
      ))}
    </>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => (
          <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => (
          <strong className="font-semibold text-[var(--text-primary)]">
            {children}
          </strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children }) => (
          <code className="px-1.5 py-0.5 rounded text-xs bg-[var(--bg-primary)] font-mono">
            {children}
          </code>
        ),
        h1: ({ children }) => (
          <h1 className="text-base font-bold mb-2">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-sm font-bold mb-1.5">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-semibold mb-1">{children}</h3>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="text-xs border-collapse w-full">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="border-b border-[var(--border)]">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1 text-left text-[var(--text-secondary)] font-medium">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-2 py-1 text-[var(--text-primary)]">{children}</td>
        ),
        tr: ({ children }) => (
          <tr className="border-b border-[var(--border)] last:border-b-0">{children}</tr>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

/** partial 消息提示条 + 续写按钮 */
function PartialBanner({
  message,
  expertColor,
}: {
  message: ExpertMessage;
  expertColor: string;
}) {
  const { resumeReply, status } = useExpertStore();
  const isResuming = status === "thinking";
  const label = message.interruptionReason === "user_cancelled"
    ? "已停止生成"
    : message.interruptionReason === "provider_error" || message.interruptionReason === "server_error"
      ? "生成中断，可继续补全"
      : "回复未完成";

  return (
    <div className="mt-2 flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2">
      <AlertTriangle size={14} className="shrink-0 text-amber-500" />
      <span className="text-xs text-amber-600 dark:text-amber-400">{label}</span>
      <button
        onClick={() => !isResuming && resumeReply(message.dbMessageId || message.id)}
        disabled={isResuming}
        className="ml-auto flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all
                   border-[var(--border)] hover:border-[var(--border-hover)] disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ color: expertColor }}
      >
        <PlayCircle size={12} />
        继续生成
      </button>
    </div>
  );
}

function ExpertFeedbackPanel({
  message,
  expertColor,
}: {
  message: ExpertMessage;
  expertColor: string;
}) {
  const { submitFeedback } = useExpertStore();
  const [open, setOpen] = useState(false);
  const [issueType, setIssueType] = useState<ExpertFeedbackIssueType>(
    defaultFeedbackIssueTypeForMessage(message),
  );
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [submittedLabel, setSubmittedLabel] = useState<string | null>(null);

  const canResumeCheck = shouldOfferResumeCheck(issueType, message);

  const handleSubmit = useCallback(async (checkResumeAfterSubmit: boolean) => {
    const targetId = message.dbMessageId || message.id;
    if (!targetId) return;
    setSubmitting(true);
    setFeedbackError(null);
    setSubmittedLabel(null);
    try {
      await submitFeedback(targetId, {
        issueType,
        userNote: note,
        checkResumeAfterSubmit,
      });
      setSubmittedLabel(checkResumeAfterSubmit ? "已反馈，并发起完整性检查" : "已提交反馈");
      setOpen(false);
      setNote("");
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : "反馈提交失败");
    } finally {
      setSubmitting(false);
    }
  }, [issueType, message.dbMessageId, message.id, note, submitFeedback]);

  return (
    <div className="mt-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-red-500 transition-colors hover:text-red-400"
        >
          <AlertTriangle size={13} />
          反馈问题
        </button>
        {submittedLabel && (
          <span className="text-xs text-emerald-500">{submittedLabel}</span>
        )}
        {feedbackError && (
          <span className="text-xs text-red-500">{feedbackError}</span>
        )}
      </div>

      {open && (
        <div className="mt-2 rounded-2xl border border-red-500/20 bg-red-500/5 p-3">
          <div className="grid gap-3">
            <label className="grid gap-1">
              <span className="text-[11px] font-semibold text-[var(--text-secondary)]">
                问题类型
              </span>
              <select
                value={issueType}
                onChange={(event) => setIssueType(event.target.value as ExpertFeedbackIssueType)}
                className="rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
              >
                {FEEDBACK_ISSUE_OPTIONS.map((item) => (
                  <option key={item} value={item}>
                    {FEEDBACK_ISSUE_LABELS[item]}
                  </option>
                ))}
              </select>
            </label>

            <label className="grid gap-1">
              <span className="text-[11px] font-semibold text-[var(--text-secondary)]">
                备注
              </span>
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
                placeholder="可选：补充你看到的现象、重现步骤或报错文案"
                className="resize-none rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none"
              />
            </label>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={submitting}
                onClick={() => handleSubmit(false)}
                className="rounded-xl border border-[var(--border)] px-3 py-2 text-xs font-medium text-[var(--text-primary)] transition-colors hover:border-[var(--border-hover)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                提交反馈
              </button>
              {canResumeCheck && (
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => handleSubmit(true)}
                  className="rounded-xl px-3 py-2 text-xs font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
                  style={{ backgroundColor: expertColor }}
                >
                  提交并检查续写
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function MessageBubble({
  message,
  expertColor,
  expertIcon,
  expertName,
}: MessageBubbleProps) {
  const { activeExpert, activeSessions } = useExpertStore();
  const isUser = message.role === "user";
  const thinkingItems = message.thinking.filter((item) => item.type !== "clarification_request");
  const sourceConversationId = activeSessions[activeExpert];

  if (isUser) {
    const isFailed = message.sendStatus === "failed";
    const isPending = message.sendStatus === "pending";
    return (
      <div className="flex justify-end items-end gap-2">
        {/* 发送失败：红色感叹号 + 点击重试 */}
        {isFailed && (
          <button
            onClick={() => useExpertStore.getState().retryMessage(message.id)}
            className="shrink-0 flex items-center gap-1 text-red-500 hover:text-red-400 transition-colors mb-1"
            title="发送失败，点击重试"
          >
            <AlertCircle size={16} />
            <RotateCw size={12} />
          </button>
        )}
        {isPending && (
          <span className="shrink-0 mb-1">
            <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white/80 rounded-full animate-spin" />
          </span>
        )}
        <div
          className={`max-w-[72%] px-4 py-2.5 rounded-2xl rounded-br-sm
                      text-white text-sm leading-relaxed ${isFailed ? "opacity-60" : ""}`}
          style={{ backgroundColor: expertColor }}
        >
          {/* 用户发送的图片缩略图 */}
          {message.images && message.images.length > 0 && (
            <div className="mb-2 flex gap-1.5 flex-wrap">
              {message.images.map((img, i) => (
                <img
                  key={i}
                  src={img}
                  alt={`图片 ${i + 1}`}
                  className="h-20 w-20 rounded-lg object-cover border border-white/20 cursor-pointer hover:opacity-80 transition-opacity"
                  onClick={() => window.open(img, "_blank")}
                />
              ))}
            </div>
          )}
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-3">
      {/* 头像 */}
      <div
        className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5 text-xs"
        style={{ backgroundColor: expertColor + "20" }}
      >
        {expertIcon}
      </div>

      <div className="flex-1 min-w-0 max-w-[80%]">
        {/* 多轮澄清卡片 */}
        <ClarificationCards message={message} expertColor={expertColor} />

        {thinkingItems.length > 0 && (
          <ThinkingPanel thinking={thinkingItems} color={expertColor} defaultOpen />
        )}

        {/* 正文 */}
        <div className="text-sm text-[var(--text-primary)] leading-relaxed">
          {message.content ? (
            hasTradePlan(message.content) ? (
              splitByTradePlan(message.content).map((segment, i) =>
                segment.type === "text" ? (
                  <MarkdownContent key={i} content={segment.content} />
                ) : segment.plan ? (
                  <div key={i} className="my-3">
                    <TradePlanCard
                      plan={segment.plan}
                      variant="dark"
                      onSave={async (plan) => {
                        const resp = await apiFetch(`${getApiBase()}/api/v1/agent/plans`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify(
                            buildExpertTradePlanPayload(
                              plan,
                              sourceConversationId,
                              message.dbMessageId || message.id,
                            ),
                          ),
                        });
                        if (!resp.ok) {
                          throw new Error(`收藏失败 (${resp.status})`);
                        }
                        return normalizeSavedTradePlanCard(await resp.json()) ?? undefined;
                      }}
                      onReview={async (planId) => {
                        const resp = await apiFetch(`${getApiBase()}/api/v1/agent/plans/${planId}/review`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({}),
                        });
                        if (!resp.ok) {
                          throw new Error(`策略卡复盘失败 (${resp.status})`);
                        }
                        return normalizePlanReview(await resp.json());
                      }}
                    />
                  </div>
                ) : (
                  <MarkdownContent key={i} content={segment.content} />
                )
              )
            ) : (
              <MarkdownContent content={message.content} />
            )
          ) : message.isStreaming ? (
            <span className="inline-flex items-center gap-1.5 text-[var(--text-tertiary)] text-xs">
              <span className="inline-flex gap-[3px]" style={{ color: expertColor }}>
                <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
              </span>
              正在思考
            </span>
          ) : null}
          {message.isStreaming && message.content && (
            <span
              className="inline-block w-0.5 h-3.5 ml-0.5 align-middle animate-pulse"
              style={{ backgroundColor: expertColor }}
            />
          )}
        </div>

        {/* partial 消息提示条 + 续写按钮 */}
        {message.status === "partial" && !message.isStreaming && (
          <PartialBanner
            message={message}
            expertColor={expertColor}
          />
        )}

        <ExpertFeedbackPanel message={message} expertColor={expertColor} />
      </div>
    </div>
  );
}
