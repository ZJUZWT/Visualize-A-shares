"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { JudgeVerdict, DebateSignal } from "@/types/debate";

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

const QUALITY_LABEL: Record<string, string> = {
  consensus: "共识",
  strong_disagreement: "强烈分歧",
  one_sided: "一边倒",
};

interface JudgeVerdictOverlayProps {
  verdict: JudgeVerdict;
  isReplay: boolean;
  onClose: () => void;
}

export default function JudgeVerdictOverlay({ verdict, isReplay, onClose }: JudgeVerdictOverlayProps) {
  const finalColor = verdict.signal ? SIGNAL_COLOR[verdict.signal] : "#9CA3AF";
  const finalLabel = verdict.signal ? SIGNAL_LABEL[verdict.signal] : "中性";

  // 回放模式：静态卡片
  if (isReplay) {
    return <StaticVerdictCard verdict={verdict} finalColor={finalColor} finalLabel={finalLabel} />;
  }

  return <AnimatedVerdictOverlay verdict={verdict} finalColor={finalColor} finalLabel={finalLabel} onClose={onClose} />;
}

function AnimatedVerdictOverlay({
  verdict, finalColor, finalLabel, onClose,
}: { verdict: JudgeVerdict; finalColor: string; finalLabel: string; onClose: () => void }) {
  const SPIN_COLORS = ["#EF4444", "#10B981", "#9CA3AF"];
  const [spinIdx, setSpinIdx] = useState(0);
  const [spinning, setSpinning] = useState(true);
  const [showContent, setShowContent] = useState(false);

  useEffect(() => {
    if (!spinning) return;
    let count = 0;
    const maxCount = 12;
    const run = () => {
      count++;
      const delay = 80 + count * 30;
      setSpinIdx(i => (i + 1) % 3);
      if (count < maxCount) {
        setTimeout(run, delay);
      } else {
        setSpinning(false);
        setTimeout(() => setShowContent(true), 200);
      }
    };
    const t = setTimeout(run, 80);
    return () => clearTimeout(t);
  }, [spinning]);

  const headerColor = spinning ? SPIN_COLORS[spinIdx] : finalColor;

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center"
      initial={{ backgroundColor: "rgba(0,0,0,0)" }}
      animate={{ backgroundColor: "rgba(0,0,0,0.7)" }}
      transition={{ duration: 0.3 }}
      onClick={spinning ? () => { setSpinning(false); setShowContent(true); } : undefined}
    >
      <motion.div
        className="relative bg-[var(--bg-secondary)] rounded-2xl border border-[var(--border)]
                   w-full max-w-lg max-h-[80vh] overflow-y-auto"
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        onClick={e => e.stopPropagation()}
      >
        {/* 顶部色块 */}
        <div className="h-2 rounded-t-2xl transition-colors duration-150" style={{ backgroundColor: headerColor }} />

        <button onClick={onClose} className="absolute top-4 right-4 text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
          <X size={16} />
        </button>

        <div className="px-6 py-5">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-2xl font-bold" style={{ color: finalColor }}>{finalLabel}</span>
            {verdict.score !== null && (
              <span className="text-sm text-[var(--text-tertiary)]">评分 {verdict.score}</span>
            )}
            <span className="text-xs text-[var(--text-tertiary)] ml-auto">
              {QUALITY_LABEL[verdict.debate_quality] ?? verdict.debate_quality}
            </span>
          </div>

          <AnimatePresence>
            {showContent && <VerdictContent verdict={verdict} />}
          </AnimatePresence>
        </div>
      </motion.div>
    </motion.div>
  );
}

function VerdictContent({ verdict }: { verdict: JudgeVerdict }) {
  const items = [
    { label: "多头核心论点", content: verdict.bull_core_thesis, side: "bull" },
    { label: "空头核心论点", content: verdict.bear_core_thesis, side: "bear" },
  ];

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
      {/* 多空对比 */}
      <div className="grid grid-cols-2 gap-3">
        {items.map(({ label, content, side }) => (
          <div key={side} className={`p-3 rounded-lg text-xs ${side === "bull" ? "bg-red-500/5 border-l-2 border-red-500" : "bg-emerald-500/5 border-l-2 border-emerald-500"}`}>
            <div className="font-medium text-[var(--text-secondary)] mb-1">{label}</div>
            <p className="text-[var(--text-primary)] leading-relaxed">{content}</p>
          </div>
        ))}
      </div>

      {/* 观察员注 */}
      {(verdict.retail_sentiment_note || verdict.smart_money_note) && (
        <div className="space-y-2">
          {verdict.retail_sentiment_note && (
            <p className="text-xs text-[var(--text-secondary)]">
              <span className="text-[var(--text-tertiary)]">散户情绪：</span>{verdict.retail_sentiment_note}
            </p>
          )}
          {verdict.smart_money_note && (
            <p className="text-xs text-[var(--text-secondary)]">
              <span className="text-[var(--text-tertiary)]">主力动向：</span>{verdict.smart_money_note}
            </p>
          )}
        </div>
      )}

      {/* 风险警示 */}
      {verdict.risk_warnings.length > 0 && (
        <div>
          <div className="text-xs text-[var(--text-tertiary)] mb-1">风险提示</div>
          <ul className="space-y-1">
            {verdict.risk_warnings.map((w, i) => (
              <li key={i} className="text-xs text-[var(--text-secondary)] flex gap-1">
                <span className="text-yellow-500 shrink-0">⚠</span>{w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 总结 */}
      <p className="text-base font-medium text-[var(--text-primary)] leading-relaxed border-t border-[var(--border)] pt-4">
        {verdict.summary}
      </p>
    </motion.div>
  );
}

function StaticVerdictCard({ verdict, finalColor, finalLabel }: { verdict: JudgeVerdict; finalColor: string; finalLabel: string }) {
  return (
    <div className="mx-4 my-4 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden">
      <div className="h-1.5" style={{ backgroundColor: finalColor }} />
      <div className="px-5 py-4 space-y-4">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold" style={{ color: finalColor }}>{finalLabel}</span>
          {verdict.score !== null && (
            <span className="text-sm text-[var(--text-tertiary)]">评分 {verdict.score}</span>
          )}
          <span className="text-xs text-[var(--text-tertiary)] ml-auto">
            {QUALITY_LABEL[verdict.debate_quality] ?? verdict.debate_quality}
          </span>
        </div>
        <VerdictContent verdict={verdict} />
      </div>
    </div>
  );
}
