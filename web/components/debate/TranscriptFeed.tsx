"use client";

import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import type { TranscriptItem } from "@/stores/useDebateStore";
import type { JudgeVerdict, DebateSignal, ObserverState } from "@/types/debate";
import SpeechBubble from "./SpeechBubble";

interface TranscriptFeedProps {
  transcript: TranscriptItem[];
  verdict: JudgeVerdict | null;
  observerState: Record<string, ObserverState>;
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

export default function TranscriptFeed({ transcript, verdict, observerState }: TranscriptFeedProps) {
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
    <div className="overflow-y-auto h-full px-6 py-5 space-y-4">
      {transcript.map((item, idx) => {
        if (item.type === "round_divider") {
          return (
            <div key={idx} className="flex items-center gap-3 py-1">
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
            <div key={idx} className="flex justify-center">
              <span className="text-xs text-[var(--text-tertiary)] px-4 py-1.5 rounded-full bg-[var(--bg-primary)] border border-[var(--border)]">
                {item.text}
              </span>
            </div>
          );
        }
        if (item.type === "loading") {
          return (
            <div key={idx} className="flex justify-center">
              <span className="flex items-center gap-2 text-xs text-[var(--text-tertiary)] px-4 py-1.5 rounded-full bg-[var(--bg-primary)] border border-[var(--border)]">
                <Loader2 size={12} className="animate-spin" />
                正在获取补充数据...
              </span>
            </div>
          );
        }
        // 每条发言后插入 observer 条
        if (item.type === "speech") {
          const retail = observerState["retail_investor"];
          const smart = observerState["smart_money"];
          return (
            <div key={idx} className="space-y-3">
              <SpeechBubble entry={item.data} />
              <ObserverBar retail={retail} smart={smart} />
            </div>
          );
        }
        return <SpeechBubble key={idx} entry={item.data} />;
      })}

      {verdict && <VerdictCard verdict={verdict} />}
      <div ref={bottomRef} />
    </div>
  );
}

function ObserverBar({ retail, smart }: { retail: ObserverState | undefined; smart: ObserverState | undefined }) {
  const retailScore = retail?.retail_sentiment_score ?? 0;
  const retailSignal: DebateSignal = retailScore > 0.1 ? "bullish" : retailScore < -0.1 ? "bearish" : "neutral";
  const retailColor = SIGNAL_COLOR[retailSignal];
  const retailLabel = retail?.speak ? SIGNAL_LABEL[retailSignal] : null;

  const smartLabel = smart?.speak ? smart.argument?.slice(0, 20) : null;

  const retailBg = retailSignal === "bullish" ? "bg-red-500/8" : retailSignal === "bearish" ? "bg-emerald-500/8" : "bg-[var(--bg-primary)]";
  const smartBg = "bg-[var(--bg-primary)]";

  return (
    <div className="flex gap-2 justify-center">
      {/* 散户情绪 */}
      <div className={`flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] text-xs ${retailBg}`}>
        <span className="text-[var(--text-tertiary)]">散户</span>
        {retailLabel
          ? <span className="font-medium" style={{ color: retailColor }}>{retailLabel}</span>
          : <span className="text-[var(--text-tertiary)]">暂无意见</span>
        }
      </div>
      {/* 主力动向 */}
      <div className={`flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] text-xs ${smartBg}`}>
        <span className="text-[var(--text-tertiary)]">主力</span>
        {smartLabel
          ? <span className="text-[var(--text-secondary)]">{smartLabel}...</span>
          : <span className="text-[var(--text-tertiary)]">暂无意见</span>
        }
      </div>
    </div>
  );
}

function VerdictCard({ verdict }: { verdict: JudgeVerdict }) {
  const color = verdict.signal ? SIGNAL_COLOR[verdict.signal] : "#9CA3AF";
  const label = verdict.signal ? SIGNAL_LABEL[verdict.signal] : "中性";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden mt-4">
      <div className="h-1.5" style={{ backgroundColor: color }} />
      <div className="px-5 py-4 space-y-4">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold" style={{ color }}>{label}</span>
          {verdict.score !== null && (
            <span className="text-sm text-[var(--text-tertiary)]">评分 {verdict.score}</span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg text-sm bg-red-500/5 border-l-2 border-red-500">
            <div className="font-medium text-[var(--text-secondary)] mb-1.5">多头核心论点</div>
            <p className="text-[var(--text-primary)] leading-relaxed">{verdict.bull_core_thesis}</p>
          </div>
          <div className="p-3 rounded-lg text-sm bg-emerald-500/5 border-l-2 border-emerald-500">
            <div className="font-medium text-[var(--text-secondary)] mb-1.5">空头核心论点</div>
            <p className="text-[var(--text-primary)] leading-relaxed">{verdict.bear_core_thesis}</p>
          </div>
        </div>
        {verdict.risk_warnings.length > 0 && (
          <ul className="space-y-1.5">
            {verdict.risk_warnings.map((w, i) => (
              <li key={i} className="text-sm text-[var(--text-secondary)] flex gap-2">
                <span className="text-yellow-500 shrink-0">⚠</span>{w}
              </li>
            ))}
          </ul>
        )}
        <p className="text-base text-[var(--text-primary)] leading-relaxed border-t border-[var(--border)] pt-4">
          {verdict.summary}
        </p>
      </div>
    </div>
  );
}
