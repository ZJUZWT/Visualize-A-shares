"use client";

/**
 * Sidebar v2.0 — 左侧控制面板
 *
 * v2.0 更新：
 * - 清爽简约浅色主题
 * - 零延迟指标切换（本地 swap 网格）
 * - 影响半径 / 高度缩放 滑块
 */

import { useTerrainStore } from "@/stores/useTerrainStore";
import { Z_METRIC_LABELS, Z_METRIC_ICONS, CLUSTER_COLORS, NOISE_COLOR } from "@/types/terrain";
import type { ZMetric } from "@/types/terrain";

export default function Sidebar() {
  const {
    terrainData,
    isLoading,
    error,
    lastUpdateTime,
    zMetric,
    showLabels,
    showGrid,
    showContours,
    radiusScale,
    heightScale,
    weightEmbedding,
    weightIndustry,
    weightNumeric,
    pcaTargetDim,
    embeddingPcaDim,
    setRadiusScale,
    setHeightScale,
    setWeightEmbedding,
    setWeightIndustry,
    setWeightNumeric,
    setPcaTargetDim,
    setEmbeddingPcaDim,
    toggleLabels,
    toggleGrid,
    toggleContours,
    fetchTerrain,
    refreshTerrain,
    switchMetricLocal,
  } = useTerrainStore();

  return (
    <div className="overlay fixed top-4 left-4 bottom-4 w-[280px] flex flex-col gap-3">
      {/* ─── Logo & 状态 ─────────────────── */}
      <div className="glass-panel px-5 py-4">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE] flex items-center justify-center text-white text-sm font-bold shadow-sm">
            T
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
              StockTerrain
            </h1>
            <p className="text-[10px] text-[var(--text-tertiary)]">
              A股多维聚类 3D 地形可视化
            </p>
          </div>
          <span className="text-[10px] text-[var(--text-tertiary)] font-mono ml-auto bg-[var(--accent-light)] px-2 py-0.5 rounded-full">
            v2.0
          </span>
        </div>
      </div>

      {/* ─── 操作按钮 ─────────────────────── */}
      <div className="glass-panel px-5 py-4">
        <button
          onClick={fetchTerrain}
          disabled={isLoading}
          className="btn-primary w-full"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              计算中...
            </span>
          ) : terrainData ? (
            "🔄 重新计算地形"
          ) : (
            "🏔️ 生成 3D 地形"
          )}
        </button>

        {terrainData && (
          <button
            onClick={refreshTerrain}
            className="btn-secondary w-full mt-2"
          >
            ⚡ 快速刷新行情
          </button>
        )}

        {error && (
          <div className="mt-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-100">
            ❌ {error}
          </div>
        )}
      </div>

      {/* ─── 数据概览 ─────────────────────── */}
      {terrainData && (
        <div className="glass-panel px-5 py-4">
          <SectionTitle>数据概览</SectionTitle>
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
          {lastUpdateTime && (
            <div className="text-[10px] text-[var(--text-tertiary)] mt-2 font-mono">
              更新于 {lastUpdateTime.toLocaleTimeString("zh-CN")}
            </div>
          )}
        </div>
      )}

      {/* ─── Z 轴指标（零延迟切换）──────────── */}
      <div className="glass-panel px-5 py-4">
        <SectionTitle>Z 轴指标</SectionTitle>
        <div className="flex flex-col gap-1">
          {(Object.entries(Z_METRIC_LABELS) as [ZMetric, string][]).map(
            ([key, label]) => (
              <button
                key={key}
                onClick={() => switchMetricLocal(key)}
                className={`text-left px-3 py-2 rounded-lg text-xs transition-smooth flex items-center gap-2 ${
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
      </div>

      {/* ─── 地形控制 ─────────────────────── */}
      <div className="glass-panel px-5 py-4">
        <SectionTitle>地形控制</SectionTitle>
        
        <SliderControl
          label="高度缩放"
          value={heightScale}
          min={1}
          max={15}
          step={0.5}
          onChange={setHeightScale}
          displayValue={`×${heightScale.toFixed(1)}`}
        />
        
        <div className="mt-3">
          <SliderControl
            label="地形连续度"
            value={radiusScale}
            min={0.5}
            max={6}
            step={0.25}
            onChange={setRadiusScale}
            displayValue={radiusScale.toFixed(1)}
            hint="控制股票影响半径"
          />
        </div>
      </div>

      {/* ─── 聚类权重 ─────────────────────── */}
      <div className="glass-panel px-5 py-4">
        <SectionTitle>聚类权重</SectionTitle>
        
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

        <div className="mt-3">
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

        <div className="mt-3">
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

        <div className="mt-3">
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

        <div className="mt-3">
          <SliderControl
            label="嵌入 PCA 维度"
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
          className="btn-primary w-full mt-4 text-xs"
        >
          {isLoading ? "计算中..." : "🏔️ 重新计算地形"}
        </button>
      </div>

      {/* ─── 显示选项 ─────────────────────── */}
      <div className="glass-panel px-5 py-4">
        <SectionTitle>显示选项</SectionTitle>
        <div className="flex flex-col gap-1.5">
          <ToggleItem label="股票标签" checked={showLabels} onChange={toggleLabels} />
          <ToggleItem label="底部网格" checked={showGrid} onChange={toggleGrid} />
          <ToggleItem label="等高线" checked={showContours} onChange={toggleContours} />
        </div>
      </div>

      {/* ─── 聚类图例 ─────────────────────── */}
      {terrainData && terrainData.clusters.length > 0 && (
        <div className="glass-panel px-5 py-4 flex-1 overflow-y-auto min-h-0">
          <SectionTitle>聚类图例</SectionTitle>
          <div className="flex flex-col gap-1">
            {terrainData.clusters
              .filter((c) => !c.is_noise)
              .slice(0, 15)
              .map((cluster, i) => (
                <div
                  key={cluster.cluster_id}
                  className="flex items-center gap-2 text-xs py-1.5 px-2 rounded-lg hover:bg-gray-50 transition-smooth"
                >
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor:
                        CLUSTER_COLORS[i % CLUSTER_COLORS.length],
                    }}
                  />
                  <span className="text-[var(--text-secondary)]">
                    簇 #{cluster.cluster_id}
                  </span>
                  <span className="font-mono text-[var(--text-primary)] ml-auto font-medium">
                    {cluster.size}
                  </span>
                </div>
              ))}
            {terrainData.clusters.find((c) => c.is_noise) && (
              <div className="flex items-center gap-2 text-xs py-1.5 px-2 opacity-60">
                <div
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: NOISE_COLOR }}
                />
                <span>离群</span>
                <span className="font-mono ml-auto">
                  {terrainData.clusters.find((c) => c.is_noise)?.size}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 小组件 ──────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[11px] font-semibold text-[var(--text-tertiary)] mb-2.5 uppercase tracking-wider">
      {children}
    </h3>
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
