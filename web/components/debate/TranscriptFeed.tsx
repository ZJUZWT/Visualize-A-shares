"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { TranscriptItem } from "@/stores/useDebateStore";
import type { JudgeVerdict, DebateSignal, RoundEval } from "@/types/debate";
import SpeechBubble from "./SpeechBubble";

interface TranscriptFeedProps {
  transcript: TranscriptItem[];
  verdict: JudgeVerdict | null;
}

const SIGNAL_COLOR: Record<DebateSignal, string> = {
  bullish: "#EF4444",
  bearish: "#10B981",
  neutral: "#9CA3AF",
};
const SIGNAL_LABEL: Record<DebateSignal, string> = {
  bullish: "看多",
  bearish: "看空",
  neutral: "中性",
};

const ROLE_LABEL: Record<string, string> = {
  bull_expert: "多头专家",
  bear_expert: "空头专家",
  retail_investor: "散户",
  smart_money: "主力",
  judge: "裁判",
};

const ROLE_COLOR: Record<string, string> = {
  bull_expert: "#EF4444",
  bear_expert: "#10B981",
  retail_investor: "#F59E0B",
  smart_money: "#8B5CF6",
  judge: "#6B7280",
};

export default function TranscriptFeed({ transcript, verdict }: TranscriptFeedProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript.length, verdict]);

  if (transcript.length === 0 && !verdict) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-[var(--text-tertiary)] h-full">
        <span className="text-4xl">⚖️</span>
        <p className="text-base">输入股票议题，开始辩论</p>
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full px-8 py-6 space-y-5">
      {transcript.map((item) => {
        if (item.type === "blackboard_data") {
          return <BlackboardCard key={item.id} item={item} />;
        }
        if (item.type === "round_divider") {
          return (
            <div key={item.id} className="flex items-center gap-3 py-1">
              <div className="flex-1 h-px bg-[var(--border)]" />
              <span className="text-xs font-medium text-[var(--text-tertiary)] px-3 py-1 rounded-full bg-[var(--bg-primary)]">
                {item.is_final ? "最终轮" : `第 ${item.round} 轮`}
              </span>
              <div className="flex-1 h-px bg-[var(--border)]" />
            </div>
          );
        }
        if (item.type === "system") {
          return (
            <div key={item.id} className="flex justify-center">
              <span className="text-xs text-[var(--text-tertiary)] px-4 py-1.5 rounded-full bg-[var(--bg-primary)] border border-[var(--border)]">
                {item.text}
              </span>
            </div>
          );
        }
        if (item.type === "entry") {
          return <SpeechBubble key={item.id} entry={item.data} />;
        }
        if (item.type === "streaming") {
          return <StreamingBubble key={item.id} item={item} />;
        }
        if (item.type === "data_request") {
          return <DataRequestCard key={item.id} item={item} />;
        }
        if (item.type === "round_eval") {
          return <RoundEvalCard key={item.id} data={item.data} />;
        }
        if (item.type === "industry_cognition") {
          return <IndustryCognitionCard key={item.id} item={item} />;
        }
        return null;
      })}

      {verdict && <VerdictCard verdict={verdict} />}
      <div ref={bottomRef} />
    </div>
  );
}

// ── 黑板初始数据卡片（可折叠）────────────────────────────
function BlackboardCard({ item }: { item: Extract<TranscriptItem, { type: "blackboard_data" }> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[90%] rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] text-xs overflow-hidden">
        <button
          onClick={() => setOpen(v => !v)}
          className="w-full flex items-center gap-2 px-4 py-2 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
        >
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          <span>辩论初始化 · {item.target}</span>
        </button>
        {open && (
          <div className="px-4 pb-3 space-y-1 border-t border-[var(--border)]">
            <p className="text-[var(--text-tertiary)] pt-2">辩论 ID: <span className="text-[var(--text-secondary)]">{item.debateId}</span></p>
            <p className="text-[var(--text-tertiary)]">参与者: <span className="text-[var(--text-secondary)]">{item.participants.join(", ")}</span></p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 行业认知卡片 ────────────────────────────────────
function IndustryCognitionCard({ item }: { item: Extract<TranscriptItem, { type: "industry_cognition" }> }) {
  const [open, setOpen] = useState(false);

  if (item.loading) {
    return (
      <div className="flex justify-center">
        <div className="w-full max-w-[90%] rounded-xl border border-amber-500/20 bg-amber-500/5 text-xs overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 text-[var(--text-tertiary)]">
            <Loader2 size={12} className="animate-spin text-amber-400" />
            <span className="text-amber-400 font-medium">行业认知</span>
            <span>正在分析 {item.industry} 产业链逻辑...</span>
          </div>
        </div>
      </div>
    );
  }

  if (item.error) {
    return (
      <div className="flex justify-center">
        <div className="w-full max-w-[90%] rounded-xl border border-red-500/20 bg-red-500/5 text-xs overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 text-[var(--text-tertiary)]">
            <span className="text-red-400">✗</span>
            <span className="text-red-400 font-medium">行业认知</span>
            <span>{item.summary}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[90%] rounded-xl border border-amber-500/20 bg-amber-500/5 text-xs overflow-hidden">
        <button
          onClick={() => setOpen(v => !v)}
          className="w-full flex items-center gap-2 px-4 py-2.5 text-left text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
        >
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          <span className="text-amber-400 font-medium">行业认知</span>
          <span className="text-[var(--text-secondary)]">{item.industry}</span>
          {item.cached && <span className="text-[var(--text-tertiary)] text-[10px]">(缓存)</span>}
          <span className="ml-auto flex gap-3">
            {item.cycle_position && <span className="text-amber-400">{item.cycle_position}</span>}
            {item.traps_count > 0 && <span className="text-yellow-500">陷阱 {item.traps_count}</span>}
          </span>
        </button>
        {open && (
          <div className="px-4 pb-3 border-t border-amber-500/10 pt-2 space-y-1">
            <p className="text-[var(--text-secondary)] leading-relaxed">{item.summary}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 数据请求卡片（可折叠结果）────────────────────────────
function DataRequestCard({ item }: { item: Extract<TranscriptItem, { type: "data_request" }> }) {
  const [open, setOpen] = useState(false);
  const isPending = item.status === "pending";
  const isFailed = item.status === "failed";
  const borderCls = isPending
    ? "border-[var(--border)] bg-[var(--bg-primary)]"
    : isFailed
    ? "border-red-500/30 bg-[var(--bg-primary)]"
    : "border-emerald-500/30 bg-[var(--bg-primary)]";

  return (
    <div className="flex justify-center">
      <div className={`w-full max-w-[90%] rounded-xl border text-xs overflow-hidden ${borderCls}`}>
        <button
          onClick={() => !isPending && setOpen(v => !v)}
          className="w-full flex items-center gap-2 px-4 py-2 text-left"
          disabled={isPending}
        >
          {isPending
            ? <Loader2 size={11} className="animate-spin text-[var(--text-tertiary)] shrink-0" />
            : <span className={`shrink-0 ${isFailed ? "text-red-400" : "text-emerald-400"}`}>{isFailed ? "✗" : "✓"}</span>
          }
          <span className="text-[var(--text-tertiary)]">{item.requested_by}</span>
          <span className="font-medium text-[var(--text-secondary)]">{item.action}</span>
          {item.duration_ms !== undefined && (
            <span className="text-[var(--text-tertiary)] ml-auto">{item.duration_ms}ms</span>
          )}
          {!isPending && item.result_summary && (
            open ? <ChevronUp size={11} className="ml-1 shrink-0 text-[var(--text-tertiary)]" />
                 : <ChevronDown size={11} className="ml-1 shrink-0 text-[var(--text-tertiary)]" />
          )}
        </button>
        {open && item.result_summary && (
          <p className="px-4 pb-3 text-[var(--text-secondary)] leading-relaxed border-t border-[var(--border)] pt-2">
            {item.result_summary}
          </p>
        )}
      </div>
    </div>
  );
}

// ── 流式气泡（与最终格式一致）────────────────────────────
function StreamingBubble({ item }: { item: Extract<TranscriptItem, { type: "streaming" }> }) {
  const isBull = item.role === "bull_expert";
  const isObserver = item.role === "retail_investor" || item.role === "smart_money";
  const isJudge = item.role === "judge";
  const color = ROLE_COLOR[item.role] ?? "#9CA3AF";
  const label = ROLE_LABEL[item.role] ?? item.role;

  if (isJudge) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] px-5 py-4">
        <span className="text-xs font-semibold mb-2 block" style={{ color }}>裁判</span>
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary)]">
          <Loader2 size={14} className="animate-spin" />
          <span>裁判正在综合各方观点，生成裁决...</span>
        </div>
      </div>
    );
  }

  if (isObserver) {
    return (
      <div className="flex justify-center">
        <div className="max-w-[85%] rounded-2xl border border-[var(--border)] bg-[var(--bg-primary)] px-6 py-4">
          <span className="text-xs font-semibold mb-2 block" style={{ color }}>{label}</span>
          <div className="text-[13px] text-[var(--text-primary)] leading-7">
            <MarkdownContent content={item.tokens} />
            <span className="inline-block w-0.5 h-4 bg-[var(--text-primary)] animate-pulse ml-0.5 align-middle" />
          </div>
        </div>
      </div>
    );
  }

  // debater
  const borderSide = isBull ? "border-l-2" : "border-r-2";
  return (
    <div className={`flex ${isBull ? "justify-start" : "justify-end"}`}>
      <div className={`max-w-[78%] rounded-2xl px-6 py-4 bg-[var(--bg-secondary)] ${borderSide}`} style={{ borderColor: color }}>
        <div className="flex items-center gap-2 mb-3">
          {item.round !== null && <span className="text-xs text-[var(--text-tertiary)]">Round {item.round}</span>}
          <span className="text-[13px] font-semibold" style={{ color }}>{label}</span>
        </div>
        <div className="text-[13px] text-[var(--text-primary)] leading-7">
          <MarkdownContent content={item.tokens} />
          <span className="inline-block w-0.5 h-4 bg-[var(--text-primary)] animate-pulse ml-0.5 align-middle" />
        </div>
      </div>
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1.5">{children}</ol>,
        li: ({ children }) => <li className="leading-7">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children }) => <code className="px-1.5 py-0.5 rounded text-xs bg-[var(--bg-primary)] font-mono">{children}</code>,
        h1: ({ children }) => <h1 className="text-base font-bold mb-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mb-2">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mb-1.5">{children}</h3>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

// ── 评委每轮小评卡片 ──────────────────────────────────
function RoundEvalCard({ data }: { data: RoundEval }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[90%] rounded-xl border border-purple-500/20 bg-purple-500/5 text-xs overflow-hidden">
        <button
          onClick={() => setOpen(v => !v)}
          className="w-full flex items-center gap-2 px-4 py-2 text-left text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
        >
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          <span className="text-purple-400 font-medium">评委小评</span>
          <span>Round {data.round}</span>
          <span className="ml-auto flex gap-3">
            <span className="text-red-400">多 {Math.round(data.bull.judge_confidence * 100)}%</span>
            <span className="text-emerald-400">空 {Math.round(data.bear.judge_confidence * 100)}%</span>
          </span>
        </button>
        {open && (
          <div className="px-4 pb-3 border-t border-purple-500/10 pt-2 space-y-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-red-400 font-medium mb-1">多头</p>
                <TripleBar label="公开" value={data.bull.self_confidence} color="#EF4444" />
                <TripleBar label="内心" value={data.bull.inner_confidence} color="#F59E0B" />
                <TripleBar label="评委" value={data.bull.judge_confidence} color="#8B5CF6" />
                {data.bull_reasoning && <p className="text-[var(--text-secondary)] mt-1 leading-relaxed">{data.bull_reasoning}</p>}
              </div>
              <div>
                <p className="text-emerald-400 font-medium mb-1">空头</p>
                <TripleBar label="公开" value={data.bear.self_confidence} color="#10B981" />
                <TripleBar label="内心" value={data.bear.inner_confidence} color="#F59E0B" />
                <TripleBar label="评委" value={data.bear.judge_confidence} color="#8B5CF6" />
                {data.bear_reasoning && <p className="text-[var(--text-secondary)] mt-1 leading-relaxed">{data.bear_reasoning}</p>}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TripleBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2 mb-1">
      <span className="w-6 text-[var(--text-tertiary)] shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-[var(--bg-primary)]">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${value * 100}%`, backgroundColor: color }} />
      </div>
      <span style={{ color }} className="w-7 text-right shrink-0">{Math.round(value * 100)}%</span>
    </div>
  );
}

function VerdictCard({ verdict }: { verdict: JudgeVerdict }) {
  const color = verdict.signal ? SIGNAL_COLOR[verdict.signal] : "#9CA3AF";
  const label = verdict.signal ? SIGNAL_LABEL[verdict.signal] : "中性";

  const QUALITY_LABEL: Record<string, string> = {
    consensus: "共识", strong_disagreement: "激烈分歧", one_sided: "一边倒",
  };

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden mt-6">
      <div className="h-1.5" style={{ backgroundColor: color }} />
      <div className="px-6 py-5 space-y-5">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold" style={{ color }}>{label}</span>
          {verdict.score !== null && (
            <span className="text-sm text-[var(--text-tertiary)]">评分 {verdict.score}</span>
          )}
          <span className="text-xs text-[var(--text-tertiary)] ml-auto px-2.5 py-1 rounded bg-[var(--bg-primary)]">
            {QUALITY_LABEL[verdict.debate_quality] ?? verdict.debate_quality}
          </span>
        </div>

        <div className="text-[13px] text-[var(--text-primary)] leading-7">
          <MarkdownContent content={verdict.summary} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 rounded-xl text-[13px] bg-[var(--bg-primary)] border-l-2 border-red-500">
            <div className="font-medium text-[var(--text-secondary)] mb-2">多头核心论点</div>
            <div className="text-[var(--text-primary)] leading-7">
              <MarkdownContent content={verdict.bull_core_thesis} />
            </div>
          </div>
          <div className="p-4 rounded-xl text-[13px] bg-[var(--bg-primary)] border-l-2 border-emerald-500">
            <div className="font-medium text-[var(--text-secondary)] mb-2">空头核心论点</div>
            <div className="text-[var(--text-primary)] leading-7">
              <MarkdownContent content={verdict.bear_core_thesis} />
            </div>
          </div>
        </div>

        {verdict.risk_warnings.length > 0 && (
          <ul className="space-y-2">
            {verdict.risk_warnings.map((w, i) => (
              <li key={i} className="text-[13px] text-[var(--text-secondary)] flex gap-2 leading-relaxed">
                <span className="text-yellow-500 shrink-0">⚠</span>{w}
              </li>
            ))}
          </ul>
        )}

        <div className="text-xs text-[var(--text-tertiary)] border-t border-[var(--border)] pt-4 flex gap-6">
          <span>散户情绪：{verdict.retail_sentiment_note}</span>
          <span>主力资金：{verdict.smart_money_note}</span>
        </div>
      </div>
    </div>
  );
}
