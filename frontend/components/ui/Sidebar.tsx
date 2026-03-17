"use client";

/**
 * Sidebar v3.1 — 单左侧栏 + 底部浮动工具栏
 *
 * v3.1 更新：
 * - 单左侧面板（核心操作 + 显示开关 + 聚类图例）
 * - 底部浮动工具栏 + 弹出面板（历史回放 / 高级设置 / 质量）
 * - Lucide 图标 + framer-motion 动画
 */

import { useState } from "react";
import { useTerrainStore } from "@/stores/useTerrainStore";
import { Z_METRIC_LABELS, CLUSTER_COLORS, NOISE_COLOR } from "@/types/terrain";
import type { ZMetric } from "@/types/terrain";
import {
  BarChart3, Mountain, FileText, Settings2, History,
  Activity, Palette, TrendingUp, RefreshCw, DollarSign,
  BookOpen, Scale, Sparkles, Tag, Grid3x3, Waves, Minimize2, GripVertical,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

const METRIC_ICON_COMPONENTS: Record<ZMetric, React.ComponentType<{ className?: string }>> = {
  pct_chg: TrendingUp,
  turnover_rate: RefreshCw,
  volume: BarChart3,
  amount: DollarSign,
  pe_ttm: FileText,
  pb: BookOpen,
  wb_ratio: Scale,
  rise_prob: Sparkles,
};

export default function Sidebar() {
  return (
    <>
      <LeftPanel />
      <BottomToolbar />
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
    xyScale,
    computeProgress,
    setHeightScale,
    setXYScale,
    fetchTerrain,
    refreshTerrain,
    switchMetricLocal,
    showLabels,
    showGrid,
    showContours,
    flattenBalls,
    showDropLines,
    toggleLabels,
    toggleGrid,
    toggleContours,
    toggleFlattenBalls,
    toggleDropLines,
  } = useTerrainStore();

  return (
    <div className="overlay fixed top-4 left-16 bottom-4 w-[260px] flex flex-col gap-2.5 overflow-y-auto scrollbar-thin">
      {/* ─── Logo & 状态 ─────────────────── */}
      <div className="glass-panel px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE] flex items-center justify-center text-white text-sm font-bold shadow-sm flex-shrink-0">
            T
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
              StockScape
            </h1>
            <p className="text-[10px] text-[var(--text-tertiary)] truncate">
              A股 AI 投研平台
            </p>
          </div>
          <span className="text-[10px] text-[var(--text-tertiary)] font-mono ml-auto bg-[var(--accent-light)] px-2 py-0.5 rounded-full flex-shrink-0">
            v3.1
          </span>
        </div>
      </div>

      {/* ─── 操作按钮 ─────────────────────── */}
      <div className="glass-panel px-4 py-3">
        {isStaticMode ? (
          <>
            {terrainData && (
              <div className="text-[11px] text-[var(--text-tertiary)] bg-[var(--accent-light)] rounded-lg px-3 py-2 text-center">
                展示模式 · 数据快照
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
                  {computeProgress
                    ? `${computeProgress.step}/${computeProgress.totalSteps} ${computeProgress.stepName}`
                    : "连接服务器..."}
                </span>
              ) : terrainData ? (
                "刷新地形数据"
              ) : (
                "生成 3D 地形"
              )}
            </button>

            {/* 计算进度展示 */}
            {isLoading && computeProgress && (
              <div className="mt-2 space-y-1.5">
                {/* 步骤进度条 */}
                <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-[var(--accent)] h-full rounded-full transition-all duration-500 ease-out"
                    style={{
                      width: `${Math.min(100, (computeProgress.step / computeProgress.totalSteps) * 100)}%`,
                    }}
                  />
                </div>
                {/* 步骤信息 */}
                <div className="text-[10px] text-[var(--text-tertiary)] text-center">
                  {computeProgress.message}
                </div>
                {/* 步骤编号 & 耗时 */}
                <div className="flex justify-between text-[10px] text-[var(--text-tertiary)] font-mono">
                  <span>步骤 {computeProgress.step}/{computeProgress.totalSteps}</span>
                  <span>{computeProgress.elapsed}s</span>
                </div>
              </div>
            )}

            {terrainData && !isLoading && (
              <div className="text-[10px] text-[var(--text-tertiary)] mt-1.5 text-center">
                布局保持稳定 · 调整权重可重排
              </div>
            )}
          </>
        )}

        {error && (
          <div className="mt-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-100">
            {error}
          </div>
        )}

        {lastUpdateTime && (
          <div className="text-[10px] text-[var(--text-tertiary)] mt-2 font-mono text-center">
            更新于 {lastUpdateTime.toLocaleTimeString("zh-CN")}
          </div>
        )}
      </div>

      {/* ─── Z 轴指标 ──────────────────────── */}
      <CollapsiblePanel title="Z 轴指标" icon={<BarChart3 className="w-3.5 h-3.5" />} defaultOpen>
        <div className="grid grid-cols-2 gap-1">
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
                {(() => {
                  const IconComp = METRIC_ICON_COMPONENTS[key];
                  return <IconComp className="w-3.5 h-3.5" />;
                })()}
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
      <CollapsiblePanel title="地形控制" icon={<Mountain className="w-3.5 h-3.5" />} defaultOpen>
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
      </CollapsiblePanel>

      {/* ─── 数据概览 ─────────────────────── */}
      {terrainData && (
        <CollapsiblePanel title="数据概览" icon={<FileText className="w-3.5 h-3.5" />} defaultOpen={false}>
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

      {/* ─── 显示开关（图标行）──────────────── */}
      {terrainData && (
        <div className="glass-panel px-4 py-3">
          <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">显示</div>
          <div className="flex gap-1.5">
            <button
              onClick={toggleLabels}
              title="股票标签"
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
                showLabels ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
              }`}
            >
              <Tag className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={toggleGrid}
              title="底部网格"
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
                showGrid ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
              }`}
            >
              <Grid3x3 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={toggleContours}
              title="等高线"
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
                showContours ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
              }`}
            >
              <Waves className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={toggleFlattenBalls}
              title="球体拍平"
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
                flattenBalls ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
              }`}
            >
              <Minimize2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={toggleDropLines}
              title="价格垂线"
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
                showDropLines ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
              }`}
            >
              <GripVertical className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* ─── 聚类图例 ─────────────────────── */}
      {terrainData && terrainData.clusters.length > 0 && (
        <CollapsiblePanel title="聚类图例" icon={<Palette className="w-3.5 h-3.5" />} defaultOpen={false}>
          <div className="flex flex-col gap-1">
            {terrainData.clusters
              .filter((c) => !c.is_noise)
              .map((cluster, i) => (
                <ClusterLegendItem
                  key={cluster.cluster_id}
                  cluster={cluster}
                  color={CLUSTER_COLORS[i % CLUSTER_COLORS.length]}
                />
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
 * 底部浮动工具栏 + 弹出面板
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function BottomToolbar() {
  const {
    terrainData,
    isStaticMode,
    isLoading,
    // 历史回放
    playbackFrames, playbackIndex, isPlaying, playbackSpeed, playbackLoading, fetchProgress,
    fetchHistory, setPlaybackIndex, togglePlayback, setPlaybackSpeed, stopPlayback,
    // 聚类权重
    weightEmbedding, weightIndustry, weightNumeric, pcaTargetDim, embeddingPcaDim,
    setWeightEmbedding, setWeightIndustry, setWeightNumeric, setPcaTargetDim, setEmbeddingPcaDim,
    // 高级地形参数
    radiusScale, gridResolution, xScaleRatio, yScaleRatio,
    setRadiusScale, setGridResolution, setXScaleRatio, setYScaleRatio,
    fetchTerrain, computeProgress,
  } = useTerrainStore();

  const [activePopup, setActivePopup] = useState<"playback" | "settings" | "quality" | null>(null);

  if (!terrainData || isStaticMode) return null;

  const togglePopup = (panel: typeof activePopup) => {
    setActivePopup((prev) => (prev === panel ? null : panel));
  };

  return (
    <>
      {/* 弹出面板 */}
      <AnimatePresence>
        {activePopup && (
          <motion.div
            key={activePopup}
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overlay fixed bottom-16 left-[340px] w-[360px] z-30"
          >
            <div className="glass-panel p-4 max-h-[400px] overflow-y-auto scrollbar-thin">
              {activePopup === "playback" && (
                <PlaybackPopup
                  playbackFrames={playbackFrames}
                  playbackIndex={playbackIndex}
                  isPlaying={isPlaying}
                  playbackSpeed={playbackSpeed}
                  playbackLoading={playbackLoading}
                  fetchProgress={fetchProgress}
                  isLoading={isLoading}
                  onFetchHistory={() => fetchHistory(7)}
                  onSetPlaybackIndex={setPlaybackIndex}
                  onTogglePlayback={togglePlayback}
                  onSetPlaybackSpeed={setPlaybackSpeed}
                  onStopPlayback={stopPlayback}
                />
              )}
              {activePopup === "settings" && (
                <SettingsPopup
                  weightEmbedding={weightEmbedding}
                  weightIndustry={weightIndustry}
                  weightNumeric={weightNumeric}
                  pcaTargetDim={pcaTargetDim}
                  embeddingPcaDim={embeddingPcaDim}
                  radiusScale={radiusScale}
                  gridResolution={gridResolution}
                  xScaleRatio={xScaleRatio}
                  yScaleRatio={yScaleRatio}
                  isLoading={isLoading}
                  computeProgress={computeProgress}
                  onSetWeightEmbedding={setWeightEmbedding}
                  onSetWeightIndustry={setWeightIndustry}
                  onSetWeightNumeric={setWeightNumeric}
                  onSetPcaTargetDim={setPcaTargetDim}
                  onSetEmbeddingPcaDim={setEmbeddingPcaDim}
                  onSetRadiusScale={setRadiusScale}
                  onSetGridResolution={(v: number) => setGridResolution(Math.round(v))}
                  onSetXScaleRatio={setXScaleRatio}
                  onSetYScaleRatio={setYScaleRatio}
                  onFetchTerrain={fetchTerrain}
                />
              )}
              {activePopup === "quality" && terrainData.cluster_quality && (
                <ClusterQualityPanel quality={terrainData.cluster_quality} />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 底部工具栏 */}
      <div className="overlay fixed bottom-4 left-[340px] right-4 flex justify-center z-20">
        <div className="glass-panel px-4 py-2 flex items-center gap-1">
          <button
            onClick={() => togglePopup("playback")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-smooth ${
              activePopup === "playback"
                ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-gray-50"
            }`}
          >
            <History className="w-3.5 h-3.5" />
            历史回放
          </button>
          <div className="w-px h-4 bg-[var(--border)]" />
          <button
            onClick={() => togglePopup("settings")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-smooth ${
              activePopup === "settings"
                ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-gray-50"
            }`}
          >
            <Settings2 className="w-3.5 h-3.5" />
            高级设置
          </button>
          <div className="w-px h-4 bg-[var(--border)]" />
          <button
            onClick={() => togglePopup("quality")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-smooth ${
              activePopup === "quality"
                ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-gray-50"
            }`}
            disabled={!terrainData.cluster_quality}
          >
            <Activity className="w-3.5 h-3.5" />
            质量
          </button>
        </div>
      </div>
    </>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 弹出面板：历史回放
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function PlaybackPopup({
  playbackFrames,
  playbackIndex,
  isPlaying,
  playbackSpeed,
  playbackLoading,
  fetchProgress,
  isLoading,
  onFetchHistory,
  onSetPlaybackIndex,
  onTogglePlayback,
  onSetPlaybackSpeed,
  onStopPlayback,
}: {
  playbackFrames: import("@/stores/useTerrainStore").PlaybackFrame[] | null;
  playbackIndex: number;
  isPlaying: boolean;
  playbackSpeed: number;
  playbackLoading: boolean;
  fetchProgress: import("@/stores/useTerrainStore").FetchProgress | null;
  isLoading: boolean;
  onFetchHistory: () => void;
  onSetPlaybackIndex: (i: number) => void;
  onTogglePlayback: () => void;
  onSetPlaybackSpeed: (s: number) => void;
  onStopPlayback: () => void;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-[var(--text-secondary)] flex items-center gap-2 mb-3">
        <History className="w-3.5 h-3.5" /> 历史回放
      </div>

      {!playbackFrames ? (
        <>
          <button
            onClick={onFetchHistory}
            disabled={playbackLoading || isLoading}
            className="btn-secondary w-full"
          >
            {playbackLoading ? (
              <span className="flex items-center justify-center gap-2">
                <Spinner />
                {fetchProgress
                  ? fetchProgress.phase === "fetching"
                    ? `拉取行情 ${fetchProgress.done}/${fetchProgress.total}`
                    : fetchProgress.phase === "computing"
                      ? `计算地形 ${fetchProgress.done}/${fetchProgress.total}`
                      : fetchProgress.message || "检查数据..."
                  : "连接服务器..."}
              </span>
            ) : (
              "加载历史回放"
            )}
          </button>

          {/* 实时进度显示 */}
          {playbackLoading && fetchProgress ? (
            <div className="mt-2 space-y-1.5">
              {/* 进度条 */}
              {fetchProgress.total > 0 && (
                <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-[var(--accent)] h-full rounded-full transition-all duration-300 ease-out"
                    style={{
                      width: `${Math.min(100, (fetchProgress.done / fetchProgress.total) * 100)}%`,
                    }}
                  />
                </div>
              )}
              {/* 进度文字 */}
              <div className="text-[10px] text-[var(--text-tertiary)] text-center">
                {fetchProgress.message}
              </div>
              {/* 详细信息 */}
              {fetchProgress.phase === "fetching" && fetchProgress.total > 0 && (
                <div className="flex justify-between text-[10px] text-[var(--text-tertiary)] font-mono">
                  <span>{fetchProgress.done}/{fetchProgress.total}</span>
                  <span>
                    {fetchProgress.elapsed ? `${fetchProgress.elapsed}s` : ""}
                    {fetchProgress.done > 0 && fetchProgress.elapsed
                      ? ` · 预计${Math.round(
                          ((fetchProgress.total - fetchProgress.done) / fetchProgress.done) *
                            fetchProgress.elapsed
                        )}s`
                      : ""}
                  </span>
                </div>
              )}
            </div>
          ) : !playbackLoading ? (
            <div className="text-[10px] text-[var(--text-tertiary)] mt-1.5 text-center">
              首次加载需拉取全市场数据
            </div>
          ) : null}
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
            onChange={(e) => onSetPlaybackIndex(parseInt(e.target.value))}
            className="w-full"
          />

          {/* 播放控制按钮 */}
          <div className="flex items-center gap-1.5 mt-2">
            <button
              onClick={() => onSetPlaybackIndex(Math.max(0, playbackIndex - 1))}
              className="btn-secondary flex-1 text-xs py-1.5"
              disabled={playbackIndex === 0}
            >
              ⏮
            </button>
            <button
              onClick={onTogglePlayback}
              className="btn-primary flex-1 text-xs py-1.5"
            >
              {isPlaying ? "⏸" : "▶"}
            </button>
            <button
              onClick={() => onSetPlaybackIndex(Math.min(playbackFrames.length - 1, playbackIndex + 1))}
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
              onChange={onSetPlaybackSpeed}
              displayValue={`${playbackSpeed.toFixed(1)}s`}
            />
          </div>

          {/* 退出回放 */}
          <button
            onClick={onStopPlayback}
            className="btn-secondary w-full mt-2 text-xs"
          >
            退出回放
          </button>
        </>
      )}
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 弹出面板：高级设置
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function SettingsPopup({
  weightEmbedding,
  weightIndustry,
  weightNumeric,
  pcaTargetDim,
  embeddingPcaDim,
  radiusScale,
  gridResolution,
  xScaleRatio,
  yScaleRatio,
  isLoading,
  computeProgress,
  onSetWeightEmbedding,
  onSetWeightIndustry,
  onSetWeightNumeric,
  onSetPcaTargetDim,
  onSetEmbeddingPcaDim,
  onSetRadiusScale,
  onSetGridResolution,
  onSetXScaleRatio,
  onSetYScaleRatio,
  onFetchTerrain,
}: {
  weightEmbedding: number;
  weightIndustry: number;
  weightNumeric: number;
  pcaTargetDim: number;
  embeddingPcaDim: number;
  radiusScale: number;
  gridResolution: number;
  xScaleRatio: number;
  yScaleRatio: number;
  isLoading: boolean;
  computeProgress: import("@/stores/useTerrainStore").ComputeProgress | null;
  onSetWeightEmbedding: (v: number) => void;
  onSetWeightIndustry: (v: number) => void;
  onSetWeightNumeric: (v: number) => void;
  onSetPcaTargetDim: (v: number) => void;
  onSetEmbeddingPcaDim: (v: number) => void;
  onSetRadiusScale: (v: number) => void;
  onSetGridResolution: (v: number) => void;
  onSetXScaleRatio: (v: number) => void;
  onSetYScaleRatio: (v: number) => void;
  onFetchTerrain: () => void;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-[var(--text-secondary)] flex items-center gap-2 mb-3">
        <Settings2 className="w-3.5 h-3.5" /> 高级设置
      </div>

      {/* ─── 地形参数 ──────────────────────── */}
      <div className="text-[10px] text-[var(--text-tertiary)] mb-2 font-medium">地形参数</div>
      <SliderControl
        label="核平滑半径"
        value={radiusScale}
        min={0.1}
        max={6.0}
        step={0.1}
        onChange={onSetRadiusScale}
        displayValue={`×${radiusScale.toFixed(1)}`}
        hint="越小越尖锐(单点)·越大越平滑"
      />
      <div className="mt-2.5">
        <SliderControl
          label="网格分辨率"
          value={gridResolution}
          min={64}
          max={1024}
          step={64}
          onChange={onSetGridResolution}
          displayValue={`${gridResolution}×${gridResolution}`}
          hint="越高越精细·计算越慢"
        />
      </div>
      <div className="mt-2.5">
        <SliderControl
          label="X 轴比例"
          value={xScaleRatio}
          min={0.3}
          max={3.0}
          step={0.05}
          onChange={onSetXScaleRatio}
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
          onChange={onSetYScaleRatio}
          displayValue={`×${yScaleRatio.toFixed(2)}`}
        />
      </div>

      {/* ─── 聚类权重 ──────────────────────── */}
      <div className="text-[10px] text-[var(--text-tertiary)] mb-2 mt-4 font-medium">聚类权重</div>
      <SliderControl
        label="嵌入权重"
        value={weightEmbedding}
        min={0}
        max={3}
        step={0.1}
        onChange={onSetWeightEmbedding}
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
          onChange={onSetWeightIndustry}
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
          onChange={onSetWeightNumeric}
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
          onChange={onSetPcaTargetDim}
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
          onChange={onSetEmbeddingPcaDim}
          displayValue={embeddingPcaDim.toString()}
          hint="嵌入预降维维度"
        />
      </div>

      {/* ─── 应用按钮 ──────────────────────── */}
      <button
        onClick={onFetchTerrain}
        disabled={isLoading}
        className="btn-primary w-full mt-3 text-xs"
      >
        {isLoading ? (
          <span className="flex items-center justify-center gap-1.5">
            <Spinner />
            {computeProgress
              ? `${computeProgress.step}/${computeProgress.totalSteps} ${computeProgress.stepName}`
              : "连接服务器..."}
          </span>
        ) : "应用并重算"}
      </button>
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
  icon?: React.ReactNode;
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
        {icon && <span className="text-[var(--text-tertiary)]">{icon}</span>}
        <span className="text-xs font-medium text-[var(--text-secondary)]">
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

/** v4.0: 聚类质量评分面板 */
function ClusterQualityPanel({ quality }: { quality: import("@/types/terrain").ClusterQuality }) {
  const silhouette = quality.silhouette_score ?? 0;
  const ch = quality.calinski_harabasz ?? 0;
  const noiseRatio = quality.noise_ratio ?? 0;
  const nClusters = quality.n_clusters ?? 0;
  const avgSize = quality.avg_cluster_size ?? 0;

  // Silhouette 评级
  const silRating = silhouette > 0.5 ? "优秀" : silhouette > 0.25 ? "良好" : silhouette > 0 ? "一般" : "较差";
  const silColor = silhouette > 0.5 ? "text-green-600" : silhouette > 0.25 ? "text-blue-600" : silhouette > 0 ? "text-yellow-600" : "text-red-600";

  return (
    <div className="space-y-2">
      {/* Silhouette 分数 — 带评级标签 */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-secondary)]">轮廓系数</span>
        <div className="flex items-center gap-1.5">
          <span className={`text-xs font-mono font-semibold ${silColor}`}>
            {silhouette.toFixed(4)}
          </span>
          <span className={`text-[10px] ${silColor} bg-opacity-10 px-1.5 py-0.5 rounded-full`}
            style={{ backgroundColor: `${silhouette > 0.25 ? '#dcfce7' : '#fef3c7'}` }}>
            {silRating}
          </span>
        </div>
      </div>

      {/* Silhouette 进度条 */}
      <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            silhouette > 0.5 ? "bg-green-500" : silhouette > 0.25 ? "bg-blue-500" : silhouette > 0 ? "bg-yellow-500" : "bg-red-500"
          }`}
          style={{ width: `${Math.max(0, Math.min(100, (silhouette + 1) * 50))}%` }}
        />
      </div>

      {/* CH 指数 */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-secondary)]">CH 指数</span>
        <span className="text-xs font-mono font-medium text-[var(--text-primary)]">
          {ch > 1000 ? `${(ch / 1000).toFixed(1)}k` : ch.toFixed(1)}
        </span>
      </div>

      {/* 摘要统计 */}
      <div className="grid grid-cols-3 gap-1.5 pt-1 border-t border-gray-100">
        <div className="text-center">
          <div className="text-[10px] text-[var(--text-tertiary)]">簇数</div>
          <div className="text-xs font-mono font-medium">{nClusters}</div>
        </div>
        <div className="text-center">
          <div className="text-[10px] text-[var(--text-tertiary)]">平均大小</div>
          <div className="text-xs font-mono font-medium">{avgSize.toFixed(0)}</div>
        </div>
        <div className="text-center">
          <div className="text-[10px] text-[var(--text-tertiary)]">噪声率</div>
          <div className="text-xs font-mono font-medium">{(noiseRatio * 100).toFixed(1)}%</div>
        </div>
      </div>
    </div>
  );
}

/** v4.0: 聚类图例项 — 含语义标签和可展开的特征画像 */
function ClusterLegendItem({ cluster, color }: { cluster: import("@/types/terrain").ClusterInfo; color: string }) {
  const [expanded, setExpanded] = useState(false);
  const clusterLabel = cluster.label || `板块 ${cluster.cluster_id}`;
  const profile = cluster.feature_profile;
  const topIndustries = cluster.top_industries;

  // 特征中文名映射
  const FEATURE_LABELS: Record<string, string> = {
    avg_pe_ttm: "PE(TTM)", avg_pb: "PB", avg_total_mv: "总市值(对数)", avg_circ_mv: "流通市值(对数)",
    avg_turnover_rate: "换手率%", avg_pct_chg: "涨跌幅%",
    avg_volatility_20d: "20日波动率", avg_volatility_60d: "60日波动率",
    avg_momentum_20d: "20日动量%", avg_rsi_14: "RSI(14)",
    avg_ma_deviation_20: "20均线偏离%", avg_ma_deviation_60: "60均线偏离%",
  };

  return (
    <div className="rounded-lg hover:bg-gray-50 transition-smooth">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs py-1.5 px-2 w-full"
      >
        <div
          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: color }}
        />
        <span className="text-[var(--text-secondary)] truncate flex-1 text-left" title={clusterLabel}>
          {clusterLabel}
        </span>
        <span className="font-mono text-[var(--text-primary)] font-medium text-[11px] flex-shrink-0">
          {cluster.size}
        </span>
        <svg
          className={`w-2.5 h-2.5 text-[var(--text-tertiary)] transition-transform duration-150 flex-shrink-0 ${expanded ? "rotate-0" : "-rotate-90"}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="px-2 pb-2 space-y-1.5">
          {/* 行业分布 */}
          {topIndustries && topIndustries.length > 0 && (
            <div>
              <div className="text-[10px] text-[var(--text-tertiary)] mb-0.5">行业分布</div>
              <div className="flex flex-wrap gap-1">
                {topIndustries.map((ind) => (
                  <span key={ind.name} className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded-full text-[var(--text-secondary)]">
                    {ind.name} {ind.count}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 特征画像 */}
          {profile && Object.keys(profile).filter(k => k.startsWith("avg_")).length > 0 && (
            <div>
              <div className="text-[10px] text-[var(--text-tertiary)] mb-0.5">特征均值</div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                {Object.entries(profile)
                  .filter(([k]) => k.startsWith("avg_"))
                  .map(([key, val]) => (
                    <div key={key} className="flex justify-between text-[10px]">
                      <span className="text-[var(--text-tertiary)] truncate">
                        {FEATURE_LABELS[key] || key.replace("avg_", "")}
                      </span>
                      <span className="font-mono text-[var(--text-primary)] ml-1">
                        {Math.abs(val) >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(2)}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* 代表股票 */}
          {cluster.top_stocks?.length > 0 && (
            <div className="text-[10px] text-[var(--text-tertiary)]">
              代表: {cluster.top_stocks.slice(0, 3).join("、")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
