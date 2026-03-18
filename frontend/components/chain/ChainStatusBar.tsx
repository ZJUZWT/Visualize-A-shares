"use client";

import { useChainStore } from "@/stores/useChainStore";
import { Loader2 } from "lucide-react";

const PHASE_LABELS: Record<string, string> = {
  thinking: "🧠 AI 正在推演",
  parsing: "📋 解析结果",
  propagating: "⚡ 冲击传播中",
};

export default function ChainStatusBar() {
  const { status, nodes, links, subject, error, shocks, simulateProgress, expandingNodes } =
    useChainStore();

  if (status === "idle") return null;

  const renderSimulateStatus = () => {
    if (status !== "simulating") return null;

    const { phase, tokens, progress, nodesApplied, linksApplied } = simulateProgress;
    const phaseLabel = PHASE_LABELS[phase] || "⚡ 正在推演";
    const pct = Math.round(progress * 100);

    if (phase === "thinking") {
      return (
        <>
          <span>{phaseLabel} · {tokens} tokens · {pct}%</span>
          <div className="w-24 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-500 transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
        </>
      );
    }

    if (phase === "parsing") {
      return <span>{phaseLabel}...</span>;
    }

    if (phase === "propagating") {
      return (
        <span>
          {phaseLabel} · 已更新 {nodesApplied} 个节点 / {linksApplied} 条边
        </span>
      );
    }

    return <span>⚡ 正在推演 {shocks.size} 个冲击的传播...</span>;
  };

  return (
    <div
      className="flex items-center gap-3 px-5 py-2 text-xs border-t border-[var(--border)]"
      style={{ background: "var(--bg-secondary)" }}
    >
      {(status === "building" || status === "simulating" || status === "adding") && (
        <Loader2 size={12} className="animate-spin text-[var(--accent)]" />
      )}

      <span className="text-[var(--text-secondary)] flex items-center gap-2">
        {status === "building"
          ? expandingNodes.length > 0
            ? `🌐 正在全局扩展 ${expandingNodes.length} 个节点...（已发现 ${nodes.length} 节点 / ${links.length} 边）`
            : `🔨 正在构建「${subject}」产业链... ${nodes.length > 0 ? `（已发现 ${nodes.length} 节点 / ${links.length} 边）` : ""}`
          : status === "adding"
            ? `➕ 正在添加节点...（${nodes.length} 节点 / ${links.length} 边）`
            : status === "simulating"
              ? renderSimulateStatus()
              : status === "ready"
                ? `✅ 网络就绪 — 点击节点设置涨跌冲击（冲击会即时传播）`
                : status === "error"
                  ? `❌ 出错`
                  : ""}
      </span>

      <span className="text-[var(--text-secondary)]">
        {nodes.length} 个节点 · {links.length} 条传导边
        {shocks.size > 0 && ` · ${shocks.size} 个冲击源`}
      </span>

      {error && (
        <span className="text-red-400 ml-auto">{error}</span>
      )}
    </div>
  );
}
