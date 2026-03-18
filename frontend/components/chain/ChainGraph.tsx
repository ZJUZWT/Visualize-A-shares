"use client";

import { useCallback, useEffect, useRef, useMemo, useState } from "react";
import { useChainStore } from "@/stores/useChainStore";
import { IMPACT_COLORS, NODE_TYPE_ICONS, NODE_TYPE_BASE_COLORS } from "@/types/chain";
import type { ChainNode, ChainLink } from "@/types/chain";
import { Settings2, Layers, ChevronDown, ChevronUp } from "lucide-react";
import dynamic from "next/dynamic";

// react-force-graph-2d 依赖 window，需要动态导入
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
      加载图谱引擎...
    </div>
  ),
});

/** 将 store 数据转为 react-force-graph 格式
 *
 * 关键：保留已有节点的物理位置 (x/y/fx/fy/vx/vy)，
 * 这样 simulate 更新 impact 时不会让图重新布局飞走。
 */
function buildGraphData(
  nodes: ChainNode[],
  links: ChainLink[],
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  prevNodesById: Map<string, any>,
) {
  const nodeMap = new Map(nodes.map((n) => [n.name, n]));

  const graphLinks = links
    .filter((l) => nodeMap.has(l.source) && nodeMap.has(l.target))
    .map((l) => ({
      source: `n_${l.source}`,
      target: `n_${l.target}`,
      relation: l.relation,
      impact: l.impact,
      impact_reason: l.impact_reason,
      confidence: l.confidence,
      transmission_speed: l.transmission_speed,
      transmission_strength: l.transmission_strength,
      transmission_mechanism: l.transmission_mechanism,
      dampening_factors: l.dampening_factors,
      amplifying_factors: l.amplifying_factors,
      constraint: l.constraint,
    }));

  const graphNodes = nodes.map((n) => {
    const id = `n_${n.name}`;
    const prev = prevNodesById.get(id);
    // 保留已有节点的物理位置
    return {
      ...n,
      id,
      // 如果之前有位置，继承过来
      ...(prev ? { x: prev.x, y: prev.y, vx: prev.vx, vy: prev.vy, fx: prev.fx, fy: prev.fy } : {}),
    };
  });

  return { nodes: graphNodes, links: graphLinks };
}

/** 左下角悬浮设置面板：展开深度 + 布局参数 */
function GraphSettingsPanel() {
  const { expandDepth, setExpandDepth, graphSettings, setGraphSettings } = useChainStore();
  const [open, setOpen] = useState(false);

  return (
    <div
      className="absolute bottom-10 left-4 z-20 select-none"
      style={{ pointerEvents: "auto" }}
    >
      {/* 折叠/展开按钮 */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                   border border-[var(--border)] backdrop-blur-md transition-all
                   hover:border-[var(--accent)]/50"
        style={{ background: "rgba(15, 23, 42, 0.85)" }}
      >
        <Settings2 size={13} className="text-[var(--text-secondary)]" />
        <span className="text-[var(--text-secondary)]">图谱设置</span>
        {open ? <ChevronDown size={12} className="text-[var(--text-secondary)]" /> : <ChevronUp size={12} className="text-[var(--text-secondary)]" />}
      </button>

      {/* 展开内容 */}
      {open && (
        <div
          className="mt-1.5 p-3 rounded-xl border border-[var(--border)] backdrop-blur-md space-y-3"
          style={{ background: "rgba(15, 23, 42, 0.92)", width: 240 }}
        >
          {/* 双击展开深度 */}
          <div>
            <div className="flex items-center gap-1.5 mb-1.5">
              <Layers size={12} className="text-[var(--text-secondary)]" />
              <span className="text-[10px] text-[var(--text-secondary)]">双击展开深度</span>
            </div>
            <div className="flex gap-1">
              {[1, 2, 3].map((d) => (
                <button
                  key={d}
                  onClick={() => setExpandDepth(d)}
                  className="flex-1 py-1 rounded text-xs font-medium transition-all"
                  style={{
                    background: expandDepth === d ? "var(--accent)" : "rgba(100,116,139,0.15)",
                    color: expandDepth === d ? "#fff" : "var(--text-secondary)",
                  }}
                  title={`双击节点展开 ${d} 层`}
                >
                  {d}层
                </button>
              ))}
            </div>
          </div>

          {/* 分割线 */}
          <div className="border-t border-[var(--border)]" />

          {/* 边长度 */}
          <div>
            <div className="flex justify-between text-[10px] text-[var(--text-secondary)] mb-1">
              <span>边长度</span>
              <span className="tabular-nums">{graphSettings.linkDistance}</span>
            </div>
            <input
              type="range"
              min={50}
              max={400}
              step={10}
              value={graphSettings.linkDistance}
              onChange={(e) => setGraphSettings({ linkDistance: parseInt(e.target.value) })}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-blue-500"
              style={{ background: "var(--border)" }}
            />
          </div>

          {/* 节点大小 */}
          <div>
            <div className="flex justify-between text-[10px] text-[var(--text-secondary)] mb-1">
              <span>节点大小</span>
              <span className="tabular-nums">{graphSettings.nodeSize.toFixed(1)}x</span>
            </div>
            <input
              type="range"
              min={0.5}
              max={2.5}
              step={0.1}
              value={graphSettings.nodeSize}
              onChange={(e) => setGraphSettings({ nodeSize: parseFloat(e.target.value) })}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-blue-500"
              style={{ background: "var(--border)" }}
            />
          </div>

          {/* 节点间距（斥力）*/}
          <div>
            <div className="flex justify-between text-[10px] text-[var(--text-secondary)] mb-1">
              <span>节点间距</span>
              <span className="tabular-nums">{Math.abs(graphSettings.chargeStrength)}</span>
            </div>
            <input
              type="range"
              min={50}
              max={1000}
              step={50}
              value={Math.abs(graphSettings.chargeStrength)}
              onChange={(e) => setGraphSettings({ chargeStrength: -parseInt(e.target.value) })}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-blue-500"
              style={{ background: "var(--border)" }}
            />
          </div>

          {/* 恢复默认 */}
          <button
            onClick={() => setGraphSettings({ linkDistance: 120, nodeSize: 1.0, chargeStrength: -300 })}
            className="w-full py-1 text-center text-[10px] text-[var(--text-secondary)]
                       hover:text-[var(--accent)] rounded transition-colors
                       border border-[var(--border)] hover:border-[var(--accent)]/30"
          >
            恢复默认
          </button>
        </div>
      )}
    </div>
  );
}

export default function ChainGraph() {
  const { nodes, links, status, selectedNode, selectNode, expandNode, shocks, simulateSummary, expandingNodes, graphSettings } =
    useChainStore();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  // 保存上一次渲染的节点位置，用于 simulate 时保持稳定
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const prevNodesRef = useRef<Map<string, any>>(new Map());

  // 确保容器已挂载且尺寸就绪后再渲染 ForceGraph2D，避免 getBoundingClientRect 空引用
  const [mounted, setMounted] = useState(false);

  const graphData = useMemo(() => {
    // 先从当前 force-graph 实例中提取最新的节点位置
    const fg = graphRef.current;
    if (fg) {
      const gd = fg.graphData?.();
      if (gd && gd.nodes) {
        const map = new Map();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        for (const n of gd.nodes as any[]) {
          if (n.id) map.set(n.id, n);
        }
        prevNodesRef.current = map;
      }
    }
    return buildGraphData(nodes, links, prevNodesRef.current);
  }, [nodes, links]);

  // 自适应画布大小
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        setDimensions({ width, height });
        // 首次拿到有效尺寸后标记为已挂载
        if (!mounted) setMounted(true);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 新节点加入时 zoom to fit (仅在节点数量变化时)
  const prevNodeCountRef = useRef(0);
  useEffect(() => {
    if (graphRef.current && nodes.length > 0 && nodes.length !== prevNodeCountRef.current) {
      prevNodeCountRef.current = nodes.length;
      setTimeout(() => graphRef.current?.zoomToFit(400, 60), 300);
    }
  }, [nodes.length]);

  // graphSettings 变化时更新力引擎参数
  useEffect(() => {
    const fg = graphRef.current;
    if (!fg) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const fgAny = fg as any;
      const charge = fgAny.d3Force?.("charge");
      if (charge) charge.strength(graphSettings.chargeStrength);
      const link = fgAny.d3Force?.("link");
      if (link) link.distance(graphSettings.linkDistance);
      fgAny.d3ReheatSimulation?.();
    } catch {
      // ignore
    }
  }, [graphSettings.chargeStrength, graphSettings.linkDistance]);

  // 初始化力参数（图首次渲染后）
  useEffect(() => {
    if (nodes.length === 0) return;
    const timer = setTimeout(() => {
      const fg = graphRef.current;
      if (!fg) return;
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const fgAny = fg as any;
        const charge = fgAny.d3Force?.("charge");
        if (charge) charge.strength(graphSettings.chargeStrength);
        const link = fgAny.d3Force?.("link");
        if (link) link.distance(graphSettings.linkDistance);
      } catch {
        // ignore
      }
    }, 100);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length > 0]);

  // ── 节点绘制 ──
  const paintNode = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.name || "";
      const impact = node.impact || "neutral";
      const nodeType = node.node_type || "industry";
      const isSelected = selectedNode?.name === node.name;
      const hasShock = shocks.has(node.name);
      const isExpanding = expandingNodes.includes(node.name);
      const score = Math.abs(node.impact_score || 0);

      // 节点大小：冲击源更大，受影响的按 score 缩放；乘以用户设置的大小系数
      const sizeScale = graphSettings.nodeSize;
      const baseSize = (hasShock ? 10 : isSelected ? 8 : 5 + score * 4) * sizeScale;

      // 正在展开的节点 — 环形进度条
      if (isExpanding) {
        const pulse = (Date.now() % 1500) / 1500;
        const startAngle = -Math.PI / 2;
        const endAngle = startAngle + pulse * 2 * Math.PI;

        // 背景轨道
        ctx.beginPath();
        ctx.arc(node.x, node.y, baseSize + 3, 0, 2 * Math.PI);
        ctx.strokeStyle = "rgba(59, 130, 246, 0.15)";
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // 进度弧
        ctx.beginPath();
        ctx.arc(node.x, node.y, baseSize + 3, startAngle, endAngle);
        ctx.strokeStyle = "#3b82f6";
        ctx.lineWidth = 2.5;
        ctx.lineCap = "round";
        ctx.stroke();
      }

      // 冲击源脉冲动画
      if (hasShock) {
        const pulse = (Date.now() % 2000) / 2000;
        const pulseRadius = baseSize + pulse * 12;
        ctx.beginPath();
        ctx.arc(node.x, node.y, pulseRadius, 0, 2 * Math.PI);
        ctx.fillStyle = `rgba(251, 191, 36, ${0.15 * (1 - pulse)})`;
        ctx.fill();
      }

      // 节点圆 — neutral 时用类型底色区分
      ctx.beginPath();
      ctx.arc(node.x, node.y, baseSize, 0, 2 * Math.PI);
      const fillColor = impact === "neutral"
        ? (NODE_TYPE_BASE_COLORS[nodeType] || IMPACT_COLORS.neutral)
        : (IMPACT_COLORS[impact] || IMPACT_COLORS.neutral);
      ctx.fillStyle = fillColor;
      ctx.fill();

      // 选中高亮环
      if (isSelected) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // 冲击源标记环
      if (hasShock) {
        ctx.strokeStyle = "#fbbf24";
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }

      // 标签
      if (globalScale > 0.5) {
        const icon = NODE_TYPE_ICONS[nodeType] || "";
        const fontSize = Math.max(12 / globalScale, 3);
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "rgba(226, 232, 240, 0.9)";
        ctx.fillText(`${icon} ${label}`, node.x, node.y + baseSize + 2);

        // 显示 impact 信息（冲击后）
        if (score > 0 && !hasShock) {
          const isCompany = nodeType === "company";
          const priceChange = node.price_change || 0;

          if (isCompany) {
            // 企业节点：显示利好/利空（A股：红=利好，绿=利空）
            const impactLabel = impact === "benefit" ? "利好" : "利空";
            const impactPct = `${Math.round(Math.abs(node.impact_score) * 100)}%`;
            ctx.fillStyle = IMPACT_COLORS[impact] || "#94a3b8";
            ctx.font = `bold ${Math.max(10 / globalScale, 2.5)}px Inter, sans-serif`;
            ctx.fillText(`${impactLabel} ${impactPct}`, node.x, node.y + baseSize + fontSize + 4);
          } else if (Math.abs(priceChange) > 0.01) {
            // 商品/材料节点：显示价格涨跌（A股：红=涨，绿=跌）
            const priceText = `${priceChange > 0 ? "↑" : "↓"}${Math.round(Math.abs(priceChange) * 100)}%`;
            ctx.fillStyle = priceChange > 0 ? IMPACT_COLORS.benefit : IMPACT_COLORS.hurt;
            ctx.font = `bold ${Math.max(10 / globalScale, 2.5)}px Inter, sans-serif`;
            ctx.fillText(priceText, node.x, node.y + baseSize + fontSize + 4);
          } else {
            // 其他受影响节点
            const scoreText = `${node.impact_score > 0 ? "+" : ""}${Math.round(node.impact_score * 100)}%`;
            ctx.fillStyle = IMPACT_COLORS[impact] || "#94a3b8";
            ctx.font = `bold ${Math.max(10 / globalScale, 2.5)}px Inter, sans-serif`;
            ctx.fillText(scoreText, node.x, node.y + baseSize + fontSize + 4);
          }
        }
      }
    },
    [selectedNode, shocks, expandingNodes, graphSettings],
  );

  // ── 边绘制 ──
  const paintLink = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const impact = link.impact || "neutral";
      const strength = link.transmission_strength || "";

      // 颜色 — A股风格：positive=红（利好/涨），negative=绿（利空/跌）
      const color =
        impact === "positive"
          ? "rgba(239, 68, 68, 0.5)"   // 红 = 利好方向
          : impact === "negative"
            ? "rgba(34, 197, 94, 0.5)"  // 绿 = 利空方向
            : "rgba(100, 116, 139, 0.15)";

      // 线宽
      const width = strength.includes("强") ? 2.5 : strength.includes("弱") ? 0.8 : 1.5;

      const source = link.source;
      const target = link.target;
      if (!source.x || !target.x) return;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.strokeStyle = color;
      ctx.lineWidth = width / globalScale;

      if (link.relation === "substitute" || link.relation === "competes") {
        ctx.setLineDash([4 / globalScale, 4 / globalScale]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // 箭头
      const angle = Math.atan2(target.y - source.y, target.x - source.x);
      const arrowLen = 6 / globalScale;
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2;
      ctx.beginPath();
      ctx.moveTo(midX, midY);
      ctx.lineTo(
        midX - arrowLen * Math.cos(angle - Math.PI / 6),
        midY - arrowLen * Math.sin(angle - Math.PI / 6),
      );
      ctx.moveTo(midX, midY);
      ctx.lineTo(
        midX - arrowLen * Math.cos(angle + Math.PI / 6),
        midY - arrowLen * Math.sin(angle + Math.PI / 6),
      );
      ctx.strokeStyle = color;
      ctx.stroke();
    },
    [],
  );

  // ── 事件处理（单击/双击）──
  const lastClickRef = useRef<{ name: string; time: number }>({ name: "", time: 0 });

  const handleNodeClick = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (node: any) => {
      const now = Date.now();
      const last = lastClickRef.current;

      if (last.name === node.name && now - last.time < 400) {
        expandNode(node.name);
        lastClickRef.current = { name: "", time: 0 };
      } else {
        const chainNode = nodes.find((n) => n.name === node.name);
        selectNode(chainNode || null);
        lastClickRef.current = { name: node.name, time: now };
      }
    },
    [nodes, selectNode, expandNode],
  );

  // 定时触发重绘（冲击源脉冲动画）
  // 注意：不能用 d3ReheatSimulation，那会让整个力模拟重新加热、节点全部飞走
  // 改用 tickFrame / refresh 仅重绘 canvas 而不改变力学状态
  useEffect(() => {
    if (shocks.size === 0 && expandingNodes.length === 0) return;
    const interval = setInterval(() => {
      const fg = graphRef.current;
      if (fg) {
        try {
          const renderer = fg;
          if (typeof renderer.refresh === "function") {
            renderer.refresh();
          } else if (typeof renderer.pauseAnimation === "function" && typeof renderer.resumeAnimation === "function") {
            renderer.resumeAnimation();
          }
        } catch {
          // ignore
        }
      }
    }, 50);
    return () => clearInterval(interval);
  }, [shocks.size, expandingNodes.length]);

  const hasNodes = graphData.nodes.length > 0;

  return (
    <div ref={containerRef} className="relative w-full h-full">
      {/* ForceGraph2D 始终渲染，避免条件切换导致 getBoundingClientRect 空引用 */}
      {mounted && (
        <div
          style={{
            opacity: hasNodes ? 1 : 0,
            pointerEvents: hasNodes ? "auto" : "none",
            position: "absolute",
            inset: 0,
          }}
        >
          <ForceGraph2D
            ref={graphRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={graphData}
            nodeCanvasObject={paintNode}
            linkCanvasObject={paintLink}
            onNodeClick={handleNodeClick}
            onNodeDragEnd={(node: Record<string, unknown>) => {
              node.fx = node.x;
              node.fy = node.y;
            }}
            onNodeRightClick={(node: Record<string, unknown>) => {
              node.fx = undefined;
              node.fy = undefined;
            }}
            cooldownTicks={100}
            cooldownTime={5000}
            d3AlphaDecay={0.05}
            d3VelocityDecay={0.3}
            enableZoomInteraction={true}
            enablePanInteraction={true}
            backgroundColor="transparent"
          />
        </div>
      )}

      {/* 空态占位 / 加载状态 */}
      {!hasNodes && (
        <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
          {status === "idle" ? (
            <div className="text-center space-y-3">
              <div className="text-4xl">🔗</div>
              <div className="text-base">输入任意主体，构建产业链沙盘</div>
              <div className="text-xs opacity-60">
                公司：中泰化学、宁德时代 · 原材料：石油、锂电池 ·
                宏观：美联储加息 · 自由组合：黄金与石油的关系
              </div>
            </div>
          ) : status === "building" || status === "adding" ? (
            <div className="text-center space-y-4">
              {/* 旋转圆环 */}
              <div className="relative mx-auto w-16 h-16">
                <div
                  className="absolute inset-0 rounded-full border-4 border-[var(--border)]"
                />
                <div
                  className="absolute inset-0 rounded-full border-4 border-transparent border-t-[var(--accent)] animate-spin"
                />
                <div className="absolute inset-0 flex items-center justify-center text-xl">
                  🔗
                </div>
              </div>
              <div className="text-sm">
                正在添加节点到产业链...
              </div>
              <div className="text-xs opacity-60">
                AI 正在分析产业链关系，请稍候
              </div>
            </div>
          ) : (
            "暂无数据"
          )}
        </div>
      )}

      {/* 模拟结果摘要 */}
      {simulateSummary && (
        <div
          className="absolute top-4 right-4 max-w-[300px] p-3 rounded-xl border border-amber-500/30
                     backdrop-blur-md text-xs z-10"
          style={{ background: "rgba(15, 23, 42, 0.9)" }}
        >
          <div className="text-[10px] font-semibold text-amber-400 mb-1">⚡ 冲击传播总结</div>
          <p className="text-[var(--text-primary)] leading-relaxed">{simulateSummary}</p>
        </div>
      )}

      {/* 构建/添加/展开 时的悬浮加载指示（图谱有内容时） */}
      {hasNodes && (status === "building" || status === "adding" || expandingNodes.length > 0) && (
        <div
          className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2.5 px-4 py-2 rounded-xl
                     border border-[var(--accent)]/30 backdrop-blur-md z-10 shadow-lg"
          style={{ background: "rgba(15, 23, 42, 0.9)" }}
        >
          <div className="relative w-5 h-5 shrink-0">
            <div className="absolute inset-0 rounded-full border-2 border-[var(--border)]" />
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-[var(--accent)] animate-spin" />
          </div>
          <span className="text-xs text-[var(--text-primary)]">
            {expandingNodes.length > 0
              ? `展开「${expandingNodes[0]}」中...`
              : `添加节点中... (${nodes.length} 节点)`}
          </span>
        </div>
      )}

      {/* 底部提示 */}
      {nodes.length > 0 && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-xs text-[var(--text-secondary)] opacity-60">
          💡 单击 → 设置涨跌冲击 · 双击 → 展开子网络 · 右键 → 取消固定 · 搜索框追加 → 增量添加
        </div>
      )}

      {/* 左下角悬浮设置面板 */}
      {nodes.length > 0 && <GraphSettingsPanel />}
    </div>
  );
}
