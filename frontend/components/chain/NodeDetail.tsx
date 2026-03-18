"use client";

import { useState, useCallback } from "react";
import {
  X, ArrowUpRight, ArrowDownRight, Truck, Factory, Clock, Package, Globe,
  TrendingUp, TrendingDown, Minus, Expand,
} from "lucide-react";
import { useChainStore } from "@/stores/useChainStore";
import { IMPACT_COLORS, NODE_TYPE_ICONS } from "@/types/chain";

export default function NodeDetail() {
  const { selectedNode, selectNode, links, shocks, setShock, clearShock, expandNode, status } =
    useChainStore();

  if (!selectedNode) return null;

  const constraint = selectedNode.constraint;
  const relatedLinks = links.filter(
    (l) => l.source === selectedNode.name || l.target === selectedNode.name,
  );
  const currentShock = shocks.get(selectedNode.name);
  const isSource = selectedNode.impact === "source" && currentShock;

  return (
    <div
      className="absolute right-0 top-0 h-full w-[380px] border-l border-[var(--border)]
                 overflow-y-auto z-10"
      style={{ background: "var(--bg-secondary)" }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <span className="text-lg">
            {NODE_TYPE_ICONS[selectedNode.node_type] || "📍"}
          </span>
          <span className="text-base font-semibold text-[var(--text-primary)]">
            {selectedNode.name}
          </span>
          <PriceChangeBadge priceChange={selectedNode.price_change ?? 0} />
          <ImpactBadge impact={selectedNode.impact} score={selectedNode.impact_score} />
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => expandNode(selectedNode.name)}
            disabled={status === "building" || status === "simulating"}
            className="p-1 rounded hover:bg-[var(--bg-primary)] text-[var(--accent)]
                       disabled:opacity-40 transition-colors"
            title="展开此节点的上下游"
          >
            <Expand size={16} />
          </button>
          <button
            onClick={() => selectNode(null)}
            className="p-1 rounded hover:bg-[var(--bg-primary)] text-[var(--text-secondary)]"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* 🎛 冲击滑块 — 核心交互 */}
      <ShockSlider
        nodeName={selectedNode.name}
        currentShock={currentShock?.shock ?? 0}
        hasShock={!!currentShock}
        isSimulating={status === "simulating"}
        onSetShock={setShock}
        onClearShock={clearShock}
      />

      {/* 摘要 + 冲击影响详情 */}
      {(selectedNode.summary || selectedNode.impact !== "neutral") && (
        <div className="px-4 py-3 border-b border-[var(--border)] space-y-2">
          {/* 冲击后：显示价格+利好利空两个维度 */}
          {selectedNode.impact !== "neutral" && selectedNode.impact !== "source" && (
            <div className="flex flex-col gap-1.5">
              {/* 商品节点显示价格变动（A股：红涨绿跌）*/}
              {selectedNode.node_type !== "company" && Math.abs(selectedNode.price_change ?? 0) > 0.01 && (
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-[var(--text-secondary)]">📊 价格传导：</span>
                  <span
                    className="font-semibold"
                    style={{ color: (selectedNode.price_change ?? 0) > 0 ? IMPACT_COLORS.benefit : IMPACT_COLORS.hurt }}
                  >
                    {(selectedNode.price_change ?? 0) > 0 ? "↑ 涨" : "↓ 跌"}
                    {Math.round(Math.abs(selectedNode.price_change ?? 0) * 100)}%
                  </span>
                </div>
              )}
              {/* 企业节点显示利好利空（A股：红=利好，绿=利空）*/}
              {selectedNode.node_type === "company" && (
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-[var(--text-secondary)]">💼 综合影响：</span>
                  <span
                    className="font-semibold"
                    style={{ color: IMPACT_COLORS[selectedNode.impact] || IMPACT_COLORS.neutral }}
                  >
                    {selectedNode.impact === "benefit" ? "利好" : "利空"}
                    {" "}{Math.round(Math.abs(selectedNode.impact_score) * 100)}%
                  </span>
                </div>
              )}
            </div>
          )}
          {selectedNode.summary && (
            <p className="text-sm text-[var(--text-primary)] leading-relaxed">
              {selectedNode.summary}
            </p>
          )}
        </div>
      )}

      {/* 代表性股票 */}
      {selectedNode.representative_stocks.length > 0 && (
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <h4 className="text-xs font-semibold text-[var(--text-secondary)] mb-2">
            📈 代表性A股
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {selectedNode.representative_stocks.map((code) => (
              <span
                key={code}
                className="px-2 py-0.5 rounded bg-[var(--bg-primary)] text-xs text-[var(--accent)] font-mono"
              >
                {code}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 物理约束 */}
      {constraint && (
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <h4 className="text-xs font-semibold text-[var(--text-secondary)] mb-3">
            🔬 物理约束
          </h4>
          <div className="space-y-2.5">
            <ConstraintItem icon={<Clock size={13} />} label="停产恢复" value={constraint.shutdown_recovery_time} />
            <ConstraintItem icon={<Factory size={13} />} label="产能天花板" value={constraint.capacity_ceiling} />
            <ConstraintItem icon={<Factory size={13} />} label="扩产周期" value={constraint.expansion_lead_time} />
            <ConstraintItem icon={<Truck size={13} />} label="运输方式" value={constraint.logistics_mode} />
            <ConstraintItem icon={<Truck size={13} />} label="物流瓶颈" value={constraint.logistics_bottleneck} />
            <ConstraintItem icon={<Package size={13} />} label="库存缓冲" value={constraint.inventory_buffer_days} />
            <ConstraintItem icon={<Globe size={13} />} label="进口依存度" value={constraint.import_dependency} />
            <ConstraintItem icon={<Globe size={13} />} label="关键贸易路线" value={constraint.key_trade_routes} />
            <ConstraintItem icon={<ArrowUpRight size={13} />} label="替代路径" value={constraint.substitution_path} />
            <ConstraintItem icon={<ArrowDownRight size={13} />} label="切换成本" value={constraint.switching_cost} />
          </div>
        </div>
      )}

      {/* 传导关系 */}
      {relatedLinks.length > 0 && (
        <div className="px-4 py-3">
          <h4 className="text-xs font-semibold text-[var(--text-secondary)] mb-3">
            🔗 传导关系
          </h4>
          <div className="space-y-2">
            {relatedLinks.map((link, i) => (
              <div key={i} className="p-2.5 rounded-lg bg-[var(--bg-primary)] text-xs">
                <div className="flex items-center gap-1 mb-1">
                  <span className="text-[var(--text-primary)] font-medium">{link.source}</span>
                  <span className="text-[var(--text-secondary)]">→</span>
                  <span className="text-[var(--text-primary)] font-medium">{link.target}</span>
                  <span
                    className="ml-auto px-1.5 py-0.5 rounded text-[10px]"
                    style={{
                      background:
                        link.impact === "positive" ? "rgba(239,68,68,0.15)"
                        : link.impact === "negative" ? "rgba(34,197,94,0.15)"
                        : "rgba(148,163,184,0.15)",
                      color:
                        link.impact === "positive" ? "#ef4444"
                        : link.impact === "negative" ? "#22c55e"
                        : "#94a3b8",
                    }}
                  >
                    {link.transmission_strength || link.relation}
                  </span>
                </div>
                <p className="text-[var(--text-secondary)] leading-relaxed">
                  {link.impact_reason}
                </p>
                {link.transmission_speed && (
                  <div className="mt-1.5 flex gap-2 text-[10px] text-[var(--text-secondary)]">
                    <span>⏱ {link.transmission_speed}</span>
                    <span>📡 {link.transmission_mechanism}</span>
                  </div>
                )}
                {(link.dampening_factors.length > 0 || link.amplifying_factors.length > 0) && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {link.dampening_factors.map((f, j) => (
                      <span key={`d${j}`} className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[10px]">
                        🛡 {f}
                      </span>
                    ))}
                    {link.amplifying_factors.map((f, j) => (
                      <span key={`a${j}`} className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 text-[10px]">
                        🔥 {f}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ── 冲击滑块组件 ──

function ShockSlider({
  nodeName,
  currentShock,
  hasShock,
  isSimulating,
  onSetShock,
  onClearShock,
}: {
  nodeName: string;
  currentShock: number;
  hasShock: boolean;
  isSimulating: boolean;
  onSetShock: (name: string, shock: number, label?: string) => void;
  onClearShock: (name: string) => void;
}) {
  const [localValue, setLocalValue] = useState(currentShock);

  const handleSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = parseFloat(e.target.value);
      setLocalValue(v);
    },
    [],
  );

  const handleSliderRelease = useCallback(() => {
    if (localValue === 0) {
      onClearShock(nodeName);
    } else {
      const label = `${localValue > 0 ? "涨" : "跌"}${Math.abs(Math.round(localValue * 100))}%`;
      onSetShock(nodeName, localValue, label);
    }
  }, [localValue, nodeName, onSetShock, onClearShock]);

  // A股风格：红涨绿跌
  const presets = [
    { label: "暴跌", value: -1.0, color: "#22c55e" },
    { label: "下跌", value: -0.5, color: "#4ade80" },
    { label: "不变", value: 0, color: "#64748b" },
    { label: "上涨", value: 0.5, color: "#f87171" },
    { label: "暴涨", value: 1.0, color: "#ef4444" },
  ];

  const sliderColor =
    localValue > 0 ? `rgba(239,68,68,${0.3 + Math.abs(localValue) * 0.7})`    // 涨=红
    : localValue < 0 ? `rgba(34,197,94,${0.3 + Math.abs(localValue) * 0.7})`  // 跌=绿
    : "rgba(100,116,139,0.5)";

  return (
    <div className="px-4 py-3 border-b border-[var(--border)]">
      <h4 className="text-xs font-semibold text-[var(--text-secondary)] mb-2.5 flex items-center gap-1.5">
        🎛 设置冲击
        {hasShock && (
          <span className="text-[10px] text-amber-400 font-normal">
            （已设为冲击源）
          </span>
        )}
      </h4>

      {/* 滑块 */}
      <div className="relative mb-2">
        <input
          type="range"
          min={-1}
          max={1}
          step={0.05}
          value={localValue}
          onChange={handleSliderChange}
          onMouseUp={handleSliderRelease}
          onTouchEnd={handleSliderRelease}
          disabled={isSimulating}
          className="w-full h-2 rounded-full appearance-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, #22c55e 0%, #64748b 50%, #ef4444 100%)`,
            accentColor: sliderColor,
          }}
        />
        <div className="flex justify-between text-[10px] text-[var(--text-secondary)] mt-1">
          <span>暴跌 -100%</span>
          <span
            className="text-sm font-bold"
            style={{
              color: localValue > 0 ? "#ef4444" : localValue < 0 ? "#22c55e" : "#64748b",
            }}
          >
            {localValue > 0 ? "+" : ""}{Math.round(localValue * 100)}%
          </span>
          <span>暴涨 +100%</span>
        </div>
      </div>

      {/* 快捷预设 */}
      <div className="flex gap-1.5">
        {presets.map(({ label, value, color }) => (
          <button
            key={label}
            onClick={() => {
              setLocalValue(value);
              if (value === 0) {
                onClearShock(nodeName);
              } else {
                onSetShock(nodeName, value, label);
              }
            }}
            disabled={isSimulating}
            className="flex-1 px-1 py-1.5 rounded text-[10px] font-medium transition-all
                       hover:scale-105 disabled:opacity-40"
            style={{
              background: `${color}15`,
              color,
              border: Math.abs(localValue - value) < 0.01 ? `1px solid ${color}` : "1px solid transparent",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 清除按钮 */}
      {hasShock && (
        <button
          onClick={() => {
            setLocalValue(0);
            onClearShock(nodeName);
          }}
          disabled={isSimulating}
          className="mt-2 w-full text-center text-[10px] text-[var(--text-secondary)]
                     hover:text-red-400 transition-colors"
        >
          清除此节点冲击
        </button>
      )}
    </div>
  );
}


// ── 影响标签 ──

function ImpactBadge({ impact, score }: { impact: string; score: number }) {
  const label =
    impact === "source" ? (score > 0 ? `冲击源 ↑` : score < 0 ? `冲击源 ↓` : "中心")
    : impact === "benefit" ? "利好"
    : impact === "hurt" ? "利空"
    : "中性";

  return (
    <span
      className="px-2 py-0.5 rounded-full text-xs font-medium"
      style={{
        background: `${IMPACT_COLORS[impact] || IMPACT_COLORS.neutral}20`,
        color: IMPACT_COLORS[impact] || IMPACT_COLORS.neutral,
      }}
    >
      {label}
      {score !== 0 && impact !== "source" && (
        <span className="ml-1 font-mono text-[10px]">
          {score > 0 ? "+" : ""}{Math.round(score * 100)}%
        </span>
      )}
    </span>
  );
}


// ── 价格变动标签 ──

function PriceChangeBadge({ priceChange }: { priceChange: number }) {
  if (Math.abs(priceChange) < 0.01) return null;

  const isUp = priceChange > 0;
  const pct = Math.round(Math.abs(priceChange) * 100);
  const color = isUp ? IMPACT_COLORS.benefit : IMPACT_COLORS.hurt; // A股：红涨绿跌

  return (
    <span
      className="px-2 py-0.5 rounded-full text-xs font-medium"
      style={{
        background: `${color}20`,
        color,
      }}
    >
      价格{isUp ? "↑" : "↓"}
      <span className="ml-1 font-mono text-[10px]">
        {pct}%
      </span>
    </span>
  );
}


// ── 约束条目 ──

function ConstraintItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 text-[var(--text-secondary)]">{icon}</span>
      <div>
        <span className="text-[10px] text-[var(--text-secondary)]">{label}</span>
        <p className="text-xs text-[var(--text-primary)] leading-relaxed">{value}</p>
      </div>
    </div>
  );
}
