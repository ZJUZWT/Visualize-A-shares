"use client";

import { useState, useRef, useCallback } from "react";
import type { ThinkingItem } from "@/types/expert";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createPortal } from "react-dom";
import {
  ChevronRight,
  ChevronDown,
  Network,
  Wrench,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Users,
  Loader2,
  TrendingUp,
  RefreshCw,
} from "lucide-react";
import { KLinePreview } from "./KLinePreview";

interface ThinkingPanelProps {
  thinking: ThinkingItem[];
  color?: string;
  /** 是否默认展开（流式消息 true，历史消息 false） */
  defaultOpen?: boolean;
}

/** 精简版 Markdown 渲染（用于专家回复详情） */
function MiniMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
        ul: ({ children }) => (
          <ul className="list-disc pl-4 mb-1.5 space-y-0.5">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal pl-4 mb-1.5 space-y-0.5">{children}</ol>
        ),
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => (
          <strong className="font-semibold text-[var(--text-primary)]">
            {children}
          </strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children }) => (
          <code className="px-1 py-0.5 rounded text-[10px] bg-[var(--bg-primary)] font-mono">
            {children}
          </code>
        ),
        h1: ({ children }) => (
          <h1 className="text-xs font-bold mb-1.5 text-[var(--text-primary)]">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-xs font-bold mb-1 text-[var(--text-primary)]">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-[11px] font-semibold mb-1 text-[var(--text-primary)]">{children}</h3>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-1.5">
            <table className="text-[10px] border-collapse w-full">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="border-b border-[var(--border)]">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-1.5 py-0.5 text-left text-[var(--text-secondary)] font-medium">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-1.5 py-0.5 text-[var(--text-primary)]">{children}</td>
        ),
        tr: ({ children }) => (
          <tr className="border-b border-[var(--border)] last:border-b-0">{children}</tr>
        ),
        hr: () => <hr className="my-1.5 border-[var(--border)]" />,
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-[var(--accent)] pl-2 my-1 text-[var(--text-tertiary)] italic">
            {children}
          </blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

/** 可折叠的专家回复详情 — 默认折叠 */
function ExpertReplyDetail({
  content,
  label,
  hasError,
  defaultOpen = false,
}: {
  content: string;
  label: string;
  hasError?: boolean;
  defaultOpen?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultOpen);
  if (!content) return null;

  // 去掉开头的 [xxx专家工具链] 调用摘要行，只保留实质回复
  const cleanContent = content.replace(/^\[.*?专家工具链\].*?\n/, "");

  return (
    <div className="mt-1.5">
      <button
        onClick={(e) => {
          e.stopPropagation();
          setExpanded((v) => !v);
        }}
        className="flex items-center gap-1 text-[10px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
      >
        {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        <span>
          {expanded ? "收起" : "展开"}
          {label}回复
        </span>
      </button>
      {expanded && (
        <div
          className={`mt-1 p-2.5 rounded-lg text-[11px] leading-relaxed max-h-[400px] overflow-y-auto
                      border text-[var(--text-primary)]
                      ${
                        hasError
                          ? "bg-red-500/5 border-red-500/20"
                          : "bg-[var(--bg-secondary)] border-[var(--border)]"
                      }`}
        >
          <MiniMarkdown content={cleanContent} />
        </div>
      )}
    </div>
  );
}

/** 悬浮 K 线预览图标 — 鼠标悬停 300ms 后在光标旁弹出浮窗 */
function HoverKLineIcon({
  chartData,
}: {
  chartData: { code: string; records: Array<Record<string, unknown>> };
}) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const iconRef = useRef<HTMLSpanElement>(null);

  const handleEnter = useCallback((e: React.MouseEvent) => {
    timerRef.current = setTimeout(() => {
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      // 浮窗出现在图标右侧偏下，避免遮挡
      const x = rect.right + 8;
      const y = rect.top - 20;
      // 边界修正：防止超出视口
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      setPos({
        x: x + 420 > vw ? rect.left - 420 : x,
        y: y + 280 > vh ? vh - 290 : y < 0 ? 10 : y,
      });
      setShow(true);
    }, 300);
  }, []);

  const handleLeave = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setShow(false);
  }, []);

  if (!chartData.records || chartData.records.length === 0) return null;

  return (
    <>
      <span
        ref={iconRef}
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        className="inline-flex items-center cursor-default ml-1 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
        title="悬停查看 K 线"
      >
        <TrendingUp size={11} />
      </span>
      {show &&
        createPortal(
          <div
            style={{
              position: "fixed",
              left: pos.x,
              top: pos.y,
              zIndex: 9999,
              pointerEvents: "none",
            }}
          >
            <KLinePreview
              code={chartData.code}
              records={chartData.records as any}
              width={400}
              height={250}
            />
          </div>,
          document.body
        )}
    </>
  );
}

export function ThinkingPanel({
  thinking,
  color = "var(--accent)",
  defaultOpen = true,
}: ThinkingPanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  if (thinking.length === 0) return null;

  // 计算错误数
  const errorCount = thinking.filter(
    (item) =>
      (item.type === "tool_result" && item.data.hasError) ||
      (item.type === "tool_call" && item.status === "error")
  ).length;

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)]
                   hover:text-[var(--text-secondary)] transition-colors mb-1"
      >
        <ChevronRight
          size={12}
          className={`transition-transform duration-150 ${open ? "rotate-90" : ""}`}
        />
        <span>思考过程</span>
        <span className="px-1.5 py-0.5 rounded-full bg-[var(--bg-primary)] text-[10px]">
          {thinking.length}
        </span>
        {errorCount > 0 && (
          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-500 text-[10px]">
            <AlertTriangle size={9} />
            {errorCount} 项失败
          </span>
        )}
      </button>

      {open && (
        <div
          className="mb-3 rounded-xl border border-[var(--border)] bg-[var(--bg-primary)]
                      divide-y divide-[var(--border)] overflow-hidden text-xs"
        >
          {thinking.map((item, i) => {
            if (item.type === "graph_recall")
              return (
                <div key={i} className="px-3 py-2 flex gap-2">
                  <Network
                    size={13}
                    className="shrink-0 mt-0.5"
                    style={{ color }}
                  />
                  <div>
                    <span className="font-medium text-[var(--text-secondary)]">
                      图谱召回
                    </span>
                    {!item.nodes || item.nodes.length === 0 ? (
                      <span className="text-[var(--text-tertiary)] ml-1">
                        无相关节点
                      </span>
                    ) : (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {item.nodes.map((n) => (
                          <span
                            key={n.id}
                            className="px-1.5 py-0.5 rounded-md text-[10px]"
                            style={{
                              backgroundColor: color + "15",
                              color,
                            }}
                          >
                            {n.label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );

            if (item.type === "thinking_round")
              return (
                <div key={i} className="px-3 py-1.5 flex items-center gap-2 bg-[var(--bg-secondary)]">
                  <RefreshCw
                    size={11}
                    className="shrink-0 animate-spin"
                    style={{ color }}
                  />
                  <span className="text-[10px] font-medium" style={{ color }}>
                    第 {item.round} 轮补充查询
                  </span>
                  <span className="text-[10px] text-[var(--text-tertiary)]">
                    （最多 {item.maxRounds} 轮）
                  </span>
                  <div className="flex-1 h-px bg-[var(--border)]" />
                </div>
              );

            if (item.type === "tool_call") {
              const isExpert = item.data.engine === "expert";
              const status = item.status ?? "pending";
              const hasResult = !!item.result;

              const StatusIcon = status === "pending" ? (
                <Loader2 size={13} className="animate-spin shrink-0 mt-0.5" style={{ color }} />
              ) : status === "error" ? (
                <AlertTriangle size={13} className="text-red-500 shrink-0 mt-0.5" />
              ) : (
                <CheckCircle2 size={13} className={isExpert ? "text-pink-500 shrink-0 mt-0.5" : "text-emerald-500 shrink-0 mt-0.5"} />
              );

              return (
                <div key={i} className="px-3 py-2">
                  <div className="flex gap-2">
                    {StatusIcon}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-[var(--text-secondary)]">
                          {item.data.label || `${item.data.engine}.${item.data.action}`}
                        </span>
                        {status === "error" && (
                          <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/10 text-red-500">
                            调用失败
                          </span>
                        )}
                        {status === "done" && hasResult && item.result!.chartData && (
                          <HoverKLineIcon chartData={item.result!.chartData} />
                        )}
                      </div>
                      {isExpert && !!item.data.params?.question && (
                        <p className="mt-0.5 text-[var(--text-tertiary)] text-[10px] line-clamp-1">
                          &ldquo;{String(item.data.params.question)}&rdquo;
                        </p>
                      )}
                      {hasResult && item.result!.content && isExpert && (
                        <ExpertReplyDetail
                          content={item.result!.content}
                          label={item.result!.label || item.data.label || "专家"}
                          hasError={item.result!.hasError}
                          defaultOpen={false}
                        />
                      )}
                      {hasResult && !isExpert && (
                        <p className={`mt-0.5 leading-relaxed line-clamp-2 ${
                          item.result!.hasError ? "text-red-400 text-[10px]" : "text-[var(--text-tertiary)]"
                        }`}>
                          {item.result!.summary}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            }

            if (item.type === "tool_result") {
              // fallback: 仅当 tool_result 未被合并到 tool_call 时才渲染（历史数据兼容）
              const isExpert = item.data.engine === "expert";
              const hasError = item.data.hasError;
              return (
                <div key={i} className="px-3 py-2">
                  <div className="flex gap-2">
                    {hasError ? (
                      <AlertTriangle
                        size={13}
                        className="text-red-500 shrink-0 mt-0.5"
                      />
                    ) : (
                      <CheckCircle2
                        size={13}
                        className={
                          isExpert
                            ? "text-pink-500 shrink-0 mt-0.5"
                            : "text-emerald-500 shrink-0 mt-0.5"
                        }
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`font-medium ${
                            hasError
                              ? "text-red-500"
                              : "text-[var(--text-secondary)]"
                          }`}
                        >
                          {isExpert
                            ? item.data.label || "专家已回复"
                            : "返回结果"}
                        </span>
                        {hasError && (
                          <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/10 text-red-500">
                            调用失败
                          </span>
                        )}
                        {item.data.chartData && (
                          <HoverKLineIcon chartData={item.data.chartData} />
                        )}
                      </div>
                      {/* 非专家的摘要（或专家错误时的摘要） */}
                      {(!isExpert || hasError) && (
                        <p
                          className={`mt-0.5 leading-relaxed line-clamp-2 ${
                            hasError
                              ? "text-red-400 text-[10px]"
                              : "text-[var(--text-tertiary)]"
                          }`}
                        >
                          {item.data.summary}
                        </p>
                      )}
                      {/* 专家完整回复（直接展示，支持 Markdown） */}
                      {isExpert && item.data.content && (
                        <ExpertReplyDetail
                          content={item.data.content}
                          label={item.data.label || "专家"}
                          hasError={hasError}
                          defaultOpen={!hasError}
                        />
                      )}
                    </div>
                  </div>
                </div>
              );
            }

            if (item.type === "belief_updated")
              return (
                <div key={i} className="px-3 py-2 flex gap-2">
                  <Sparkles
                    size={13}
                    className="text-purple-500 shrink-0 mt-0.5"
                  />
                  <div>
                    <span className="font-medium text-[var(--text-secondary)]">
                      信念更新
                    </span>
                    <p className="mt-0.5 text-[var(--text-tertiary)] line-clamp-2">
                      {item.data.new.content}
                    </p>
                  </div>
                </div>
              );

            return null;
          })}
        </div>
      )}
    </div>
  );
}
