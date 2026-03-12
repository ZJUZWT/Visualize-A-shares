"use client";

/**
 * Sidebar v3.0 — 双侧面板布局
 *
 * v3.0 更新：
 * - 拆分为左侧面板（核心操作）+ 右侧面板（辅助信息/设置）
 * - 所有面板可折叠
 * - 两侧均可独立滚动
 */

import { useState } from "react";
import { useTerrainStore } from "@/stores/useTerrainStore";
import { Z_METRIC_LABELS, Z_METRIC_ICONS, CLUSTER_COLORS, NOISE_COLOR } from "@/types/terrain";
import type { ZMetric } from "@/types/terrain";

export default function Sidebar() {
  return (
    <>
      <LeftPanel />
      <RightPanel />
    </>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 左侧面板 — 核心操作
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function LeftPanel() {
  const {
    terrainData,
    isLoading,
    error,
    lastUpdateTime,
    isStaticMode,
    zMetric,
    heightScale,
    radiusScale,
    xyScale,
    xScaleRatio,
    yScaleRatio,
    gridResolution,
    setHeightScale,
    setRadiusScale,
    setXYScale,
    setXScaleRatio,
    setYScaleRatio,
    setGridResolution,
    fetchTerrain,
    refreshTerrain,
    switchMetricLocal,
  } = useTerrainStore();

  return (
    <div className="overlay fixed top-4 left-4 bottom-4 w-[260px] flex flex-col gap-2.5 overflow-y-auto scrollbar-thin">
      {/* ─── Logo & 状态 ─────────────────── */}
      <div className="glass-panel px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE] flex items-center justify-center text-white text-sm font-bold shadow-sm flex-shrink-0">
            T
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
              StockTerrain
            </h1>
            <p className="text-[10px] text-[var(--text-tertiary)] truncate">
              A股多维聚类 3D 地形可视化
            </p>
          </div>
          <span className="text-[10px] text-[var(--text-tertiary)] font-mono ml-auto bg-[var(--accent-light)] px-2 py-0.5 rounded-full flex-shrink-0">
            v3.0
          </span>
        </div>
      </div>

      {/* ─── 操作按钮 ─────────────────────── */}
      <div className="glass-panel px-4 py-3">
        {isStaticMode ? (
          <>
            {terrainData && (
              <div className="text-[11px] text-[var(--text-tertiary)] bg-[var(--accent-light)] rounded-lg px-3 py-2 text-center">
                📸 展示模式 · 数据快照
              </div>
            )}
            {isLoading && (
              <div className="flex items-center justify-center gap-2 text-sm text-[var(--text-secondary)]">
                <Spinner />
                加载数据中...
              </div>
            )}
          </>
        ) : (
          <>
            <button
              onClick={fetchTerrain}
              disabled={isLoading}
              className="btn-primary w-full"
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <Spinner />
                  计算中...
                </span>
              ) : terrainData ? (
                "🔄 刷新地形数据"
              ) : (
                "🏔️ 生成 3D 地形"
              )}
            </button>

            {terrainData && (
              <div className="text-[10px] text-[var(--text-tertiary)] mt-1.5 text-center">
                布局保持稳定 · 调整权重可重排
              </div>
            )}
          </>
        )}

        {error && (
          <div className="mt-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-100">
            ❌ {error}
          </div>
        )}

        {lastUpdateTime && (
          <div className="text-[10px] text-[var(--text-tertiary)] mt-2 font-mono text-center">
            更新于 {lastUpdateTime.toLocaleTimeString("zh-CN")}
          </div>
        )}
      </div>

      {/* ─── Z 轴指标 ──────────────────────── */}
      <CollapsiblePanel title="Z 轴指标" icon="📊" defaultOpen>
        <div className="flex flex-col gap-1">
          {(Object.entries(Z_METRIC_LABELS) as [ZMetric, string][]).map(
            ([key, label]) => (
              <button
                key={key}
                onClick={() => switchMetricLocal(key)}
                className={`text-left px-3 py-1.5 rounded-lg text-xs transition-smooth flex items-center gap-2 ${
                  zMetric === key
                    ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium border border-[var(--accent)]/20"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-gray-50"
                }`}
              >
                <span>{Z_METRIC_ICONS[key]}</span>
                <span>{label}</span>
                {zMetric === key && (
                  <span className="ml-auto text-[10px] text-[var(--accent)]">●</span>
                )}
              </button>
            )
          )}
        </div>
      </CollapsiblePanel>

      {/* ─── 地形控制 ─────────────────────── */}
      <CollapsiblePanel title="地形控制" icon="🏔️" defaultOpen>
        <SliderControl
          label="高度缩放"
          value={heightScale}
          min={1}
          max={15}
          step={0.5}
          onChange={setHeightScale}
          displayValue={`×${heightScale.toFixed(1)}`}
        />

        <div className="mt-2.5">
          <SliderControl
            label="核平滑半径"
            value={radiusScale}
            min={0.1}
            max={6.0}
            step={0.1}
            onChange={setRadiusScale}
            displayValue={`×${radiusScale.toFixed(1)}`}
            hint="越小越尖锐(单点)·越大越平滑"
          />
        </div>

        <div className="mt-2.5">
          <SliderControl
            label="网格分辨率"
            value={gridResolution}
            min={64}
            max={1024}
            step={64}
            onChange={(v) => setGridResolution(Math.round(v))}
            displayValue={`${gridResolution}×${gridResolution}`}
            hint="越高越精细·计算越慢"
          />
        </div>

        {!isStaticMode && (radiusScale !== 2.0 || gridResolution !== 512) && (
          <button
            onClick={fetchTerrain}
            disabled={isLoading}
            className="btn-secondary w-full mt-2 text-xs"
          >
            {isLoading ? "计算中..." : "🔄 应用核半径/分辨率"}
          </button>
        )}

        <div className="mt-2.5">
          <SliderControl
            label="XY 整体缩放"
            value={xyScale}
            min={0.5}
            max={5.0}
            step={0.1}
            onChange={setXYScale}
            displayValue={`×${xyScale.toFixed(1)}`}
            hint="整体放大/缩小地形平面"
          />
        </div>

        <div className="mt-2.5">
          <SliderControl
            label="X 轴比例"
            value={xScaleRatio}
            min={0.3}
            max={3.0}
            step={0.05}
            onChange={setXScaleRatio}
            displayValue={`×${xScaleRatio.toFixed(2)}`}
          />
        </div>

        <div className="mt-2.5">
          <SliderControl
            label="Y 轴比例"
            value={yScaleRatio}
            min={0.3}
            max={3.0}
            step={0.05}
            onChange={setYScaleRatio}
            displayValue={`×${yScaleRatio.toFixed(2)}`}
          />
        </div>
      </CollapsiblePanel>

      {/* ─── 数据概览 ─────────────────────── */}
      {terrainData && (
        <CollapsiblePanel title="数据概览" icon="📋" defaultOpen={false}>
          <div className="grid grid-cols-2 gap-2">
            <StatItem label="股票数" value={terrainData.stock_count.toLocaleString()} />
            <StatItem label="聚类数" value={terrainData.cluster_count.toString()} />
            <StatItem
              label="网格"
              value={`${terrainData.terrain_resolution}²`}
            />
            <StatItem
              label="耗时"
              value={`${(terrainData.computation_time_ms / 1000).toFixed(1)}s`}
            />
          </div>
        </CollapsiblePanel>
      )}
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 右侧面板 — 辅助设置 & 信息
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function RightPanel() {
  const {
    terrainData,
    isLoading,
    isStaticMode,
    showLabels,
    showGrid,
    showContours,
    showDropLines,
    flattenBalls,
    weightEmbedding,
    weightIndustry,
    weightNumeric,
    pcaTargetDim,
    embeddingPcaDim,
    playbackFrames,
    playbackIndex,
    isPlaying,
    playbackSpeed,
    playbackLoading,
    setWeightEmbedding,
    setWeightIndustry,
    setWeightNumeric,
    setPcaTargetDim,
    setEmbeddingPcaDim,
    toggleLabels,
    toggleGrid,
    toggleContours,
    toggleFlattenBalls,
    toggleDropLines,
    fetchTerrain,
    fetchHistory,
    setPlaybackIndex,
    togglePlayback,
    setPlaybackSpeed,
    stopPlayback,
  } = useTerrainStore();

  // 没有数据时不显示右侧面板（除了显示选项）
  const hasAnyContent = terrainData || !isStaticMode;
  if (!hasAnyContent) return null;

  return (
    <div className="overlay fixed top-14 right-4 bottom-14 w-[240px] flex flex-col gap-2.5 overflow-y-auto scrollbar-thin">
      {/* ─── 显示选项 ─────────────────────── */}
      <CollapsiblePanel title="显示选项" icon="👁️" defaultOpen>
        <div className="flex flex-col gap-1">
          <ToggleItem label="股票标签" checked={showLabels} onChange={toggleLabels} />
          <ToggleItem label="底部网格" checked={showGrid} onChange={toggleGrid} />
          <ToggleItem label="等高线" checked={showContours} onChange={toggleContours} />
          <ToggleItem label="球体拍平" checked={flattenBalls} onChange={toggleFlattenBalls} />
          <ToggleItem label="价格垂线" checked={showDropLines} onChange={toggleDropLines} />
        </div>
      </CollapsiblePanel>

      {/* ─── 聚类权重（仅动态模式）─────────── */}
      {!isStaticMode && (
        <CollapsiblePanel title="聚类权重" icon="⚙️" defaultOpen={false}>
          <SliderControl
            label="嵌入权重"
            value={weightEmbedding}
            min={0}
            max={3}
            step={0.1}
            onChange={setWeightEmbedding}
            displayValue={weightEmbedding.toFixed(1)}
            hint="BGE 语义嵌入层权重"
          />

          <div className="mt-2.5">
            <SliderControl
              label="行业权重"
              value={weightIndustry}
              min={0}
              max={2}
              step={0.1}
              onChange={setWeightIndustry}
              displayValue={weightIndustry.toFixed(1)}
              hint="行业 one-hot 层权重"
            />
          </div>

          <div className="mt-2.5">
            <SliderControl
              label="数值权重"
              value={weightNumeric}
              min={0}
              max={3}
              step={0.1}
              onChange={setWeightNumeric}
              displayValue={weightNumeric.toFixed(1)}
              hint="财务/交易特征层权重"
            />
          </div>

          <div className="mt-2.5">
            <SliderControl
              label="PCA 维度"
              value={pcaTargetDim}
              min={10}
              max={100}
              step={5}
              onChange={setPcaTargetDim}
              displayValue={pcaTargetDim.toString()}
              hint="最终降维目标维度"
            />
          </div>

          <div className="mt-2.5">
            <SliderControl
              label="嵌入 PCA"
              value={embeddingPcaDim}
              min={8}
              max={64}
              step={4}
              onChange={setEmbeddingPcaDim}
              displayValue={embeddingPcaDim.toString()}
              hint="嵌入预降维维度"
            />
          </div>

          <button
            onClick={fetchTerrain}
            disabled={isLoading}
            className="btn-primary w-full mt-3 text-xs"
          >
            {isLoading ? "计算中..." : "🏔️ 应用并重算"}
          </button>
        </CollapsiblePanel>
      )}

      {/* ─── 历史回放 ─────────────────────── */}
      {terrainData && !isStaticMode && (
        <CollapsiblePanel title="历史回放" icon="📅" defaultOpen={false}>
          {!playbackFrames ? (
            <>
              <button
                onClick={() => fetchHistory(7)}
                disabled={playbackLoading || isLoading}
                className="btn-secondary w-full"
              >
                {playbackLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Spinner />
                    加载历史数据...
                  </span>
                ) : (
                  "📅 加载历史回放"
                )}
              </button>
              <div className="text-[10px] text-[var(--text-tertiary)] mt-1.5 text-center">
                每次生成地形会自动积累快照
              </div>
            </>
          ) : (
            <>
              {/* 日期显示 */}
              <div className="text-center mb-2">
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                  {playbackFrames[playbackIndex]?.date ?? ""}
                </span>
                <span className="text-[10px] text-[var(--text-tertiary)] ml-2">
                  {playbackIndex + 1}/{playbackFrames.length}
                </span>
              </div>

              {/* 时间轴滑块 */}
              <input
                type="range"
                min={0}
                max={playbackFrames.length - 1}
                step={1}
                value={playbackIndex}
                onChange={(e) => setPlaybackIndex(parseInt(e.target.value))}
                className="w-full"
              />

              {/* 播放控制按钮 */}
              <div className="flex items-center gap-1.5 mt-2">
                <button
                  onClick={() => setPlaybackIndex(Math.max(0, playbackIndex - 1))}
                  className="btn-secondary flex-1 text-xs py-1.5"
                  disabled={playbackIndex === 0}
                >
                  ⏮
                </button>
                <button
                  onClick={togglePlayback}
                  className="btn-primary flex-1 text-xs py-1.5"
                >
                  {isPlaying ? "⏸" : "▶"}
                </button>
                <button
                  onClick={() => setPlaybackIndex(Math.min(playbackFrames.length - 1, playbackIndex + 1))}
                  className="btn-secondary flex-1 text-xs py-1.5"
                  disabled={playbackIndex === playbackFrames.length - 1}
                >
                  ⏭
                </button>
              </div>

              {/* 速度控制 */}
              <div className="mt-2">
                <SliderControl
                  label="速度"
                  value={playbackSpeed}
                  min={0.5}
                  max={5}
                  step={0.5}
                  onChange={setPlaybackSpeed}
                  displayValue={`${playbackSpeed.toFixed(1)}s`}
                />
              </div>

              {/* 退出回放 */}
              <button
                onClick={stopPlayback}
                className="btn-secondary w-full mt-2 text-xs"
              >
                ✕ 退出回放
              </button>
            </>
          )}
        </CollapsiblePanel>
      )}

      {/* ─── 聚类图例 ─────────────────────── */}
      {terrainData && terrainData.clusters.length > 0 && (
        <CollapsiblePanel title="聚类图例" icon="🎨" defaultOpen={false}>
          <div className="flex flex-col gap-0.5">
            {terrainData.clusters
              .filter((c) => !c.is_noise)
              .slice(0, 15)
              .map((cluster, i) => (
                <div
                  key={cluster.cluster_id}
                  className="flex items-center gap-2 text-xs py-1 px-2 rounded-lg hover:bg-gray-50 transition-smooth"
                >
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor:
                        CLUSTER_COLORS[i % CLUSTER_COLORS.length],
                    }}
                  />
                  <span className="text-[var(--text-secondary)]">
                    #{cluster.cluster_id}
                  </span>
                  <span className="font-mono text-[var(--text-primary)] ml-auto font-medium text-[11px]">
                    {cluster.size}
                  </span>
                </div>
              ))}
            {terrainData.clusters.find((c) => c.is_noise) && (
              <div className="flex items-center gap-2 text-xs py-1 px-2 opacity-60">
                <div
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: NOISE_COLOR }}
                />
                <span>离群</span>
                <span className="font-mono ml-auto text-[11px]">
                  {terrainData.clusters.find((c) => c.is_noise)?.size}
                </span>
              </div>
            )}
          </div>
        </CollapsiblePanel>
      )}
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 通用组件
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

/** 可折叠面板 */
function CollapsiblePanel({
  title,
  icon,
  defaultOpen = true,
  children,
}: {
  title: string;
  icon?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="glass-panel">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-2.5 flex items-center gap-2 hover:bg-gray-50/50 transition-smooth rounded-[var(--radius)]"
      >
        {icon && <span className="text-xs">{icon}</span>}
        <span className="text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
          {title}
        </span>
        <svg
          className={`w-3 h-3 ml-auto text-[var(--text-tertiary)] transition-transform duration-200 ${
            isOpen ? "rotate-0" : "-rotate-90"
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div
        className={`overflow-hidden transition-all duration-200 ease-in-out ${
          isOpen ? "max-h-[600px] opacity-100" : "max-h-0 opacity-0"
        }`}
      >
        <div className="px-4 pb-3">
          {children}
        </div>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"/>
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
    </svg>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50/80 rounded-lg px-3 py-2">
      <div className="text-[10px] text-[var(--text-tertiary)]">{label}</div>
      <div className="font-mono text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </div>
    </div>
  );
}

function ToggleItem({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <button
      onClick={onChange}
      className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-gray-50 transition-smooth"
    >
      <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      <div
        className={`w-8 h-[18px] rounded-full transition-colors relative ${
          checked ? "bg-[var(--accent)]" : "bg-gray-200"
        }`}
      >
        <div
          className={`w-3.5 h-3.5 rounded-full bg-white absolute top-[2px] transition-transform shadow-sm ${
            checked ? "translate-x-[14px]" : "translate-x-[2px]"
          }`}
        />
      </div>
    </button>
  );
}

function SliderControl({
  label,
  value,
  min,
  max,
  step,
  onChange,
  displayValue,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  displayValue: string;
  hint?: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-[var(--text-secondary)]">{label}</span>
        <span className="text-xs font-mono text-[var(--accent)] font-medium bg-[var(--accent-light)] px-2 py-0.5 rounded-full">
          {displayValue}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
      {hint && (
        <div className="text-[10px] text-[var(--text-tertiary)] mt-1">{hint}</div>
      )}
    </div>
  );
}
