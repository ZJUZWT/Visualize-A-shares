/**
 * 地形状态管理 v2.0 (Zustand)
 *
 * v2.0 新增：
 * - 多指标网格缓存（切换指标零延迟）
 * - 影响半径滑块控制
 * - 浅色主题状态
 */

import { create } from "zustand";
import type { TerrainData, StockPoint, ZMetric } from "@/types/terrain";

interface TerrainState {
  // ─── 数据 ────────────────────────────
  terrainData: TerrainData | null;
  isLoading: boolean;
  error: string | null;
  lastUpdateTime: Date | null;

  // ─── 交互状态 ────────────────────────
  selectedStock: StockPoint | null;
  hoveredStock: StockPoint | null;
  zMetric: ZMetric;
  showLabels: boolean;
  showGrid: boolean;
  showContours: boolean;
  
  // v2.0: 影响半径控制
  radiusScale: number;
  heightScale: number;

  // v3.0: 聚类权重
  weightEmbedding: number;
  weightIndustry: number;
  weightNumeric: number;
  pcaTargetDim: number;
  embeddingPcaDim: number;

  // ─── Actions ─────────────────────────
  setTerrainData: (data: TerrainData) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedStock: (stock: StockPoint | null) => void;
  setHoveredStock: (stock: StockPoint | null) => void;
  setZMetric: (metric: ZMetric) => void;
  setRadiusScale: (scale: number) => void;
  setHeightScale: (scale: number) => void;
  setWeightEmbedding: (v: number) => void;
  setWeightIndustry: (v: number) => void;
  setWeightNumeric: (v: number) => void;
  setPcaTargetDim: (v: number) => void;
  setEmbeddingPcaDim: (v: number) => void;
  toggleLabels: () => void;
  toggleGrid: () => void;
  toggleContours: () => void;
  fetchTerrain: () => Promise<void>;
  refreshTerrain: () => Promise<void>;
  
  // v2.0: 本地切换指标（零延迟）
  switchMetricLocal: (metric: ZMetric) => void;
}

export const useTerrainStore = create<TerrainState>((set, get) => ({
  // ─── 初始状态 ────────────────────────
  terrainData: null,
  isLoading: false,
  error: null,
  lastUpdateTime: null,

  selectedStock: null,
  hoveredStock: null,
  zMetric: "pct_chg",
  showLabels: true,
  showGrid: true,
  showContours: true,
  radiusScale: 2.0,
  heightScale: 8.0,

  // v3.0: 聚类权重默认值
  weightEmbedding: 1.5,
  weightIndustry: 0.8,
  weightNumeric: 1.0,
  pcaTargetDim: 50,
  embeddingPcaDim: 32,

  // ─── Actions ─────────────────────────
  setTerrainData: (data) =>
    set({ terrainData: data, lastUpdateTime: new Date(), error: null }),

  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error, isLoading: false }),

  setSelectedStock: (stock) => set({ selectedStock: stock }),
  setHoveredStock: (stock) => set({ hoveredStock: stock }),
  setZMetric: (metric) => set({ zMetric: metric }),
  setRadiusScale: (scale) => set({ radiusScale: scale }),
  setHeightScale: (scale) => set({ heightScale: scale }),
  setWeightEmbedding: (v) => set({ weightEmbedding: v }),
  setWeightIndustry: (v) => set({ weightIndustry: v }),
  setWeightNumeric: (v) => set({ weightNumeric: v }),
  setPcaTargetDim: (v) => set({ pcaTargetDim: v }),
  setEmbeddingPcaDim: (v) => set({ embeddingPcaDim: v }),

  toggleLabels: () => set((s) => ({ showLabels: !s.showLabels })),
  toggleGrid: () => set((s) => ({ showGrid: !s.showGrid })),
  toggleContours: () => set((s) => ({ showContours: !s.showContours })),

  // v2.0: 本地切换指标（从缓存的 grids 中切换，零延迟）
  switchMetricLocal: (metric: ZMetric) => {
    const { terrainData } = get();
    if (!terrainData || !terrainData.grids || !terrainData.grids[metric]) {
      // 无缓存，回退到网络请求
      set({ zMetric: metric });
      return;
    }

    const newGrid = terrainData.grids[metric];
    const metricBounds = terrainData.bounds_per_metric?.[metric] || { zmin: 0, zmax: 1 };
    
    // 更新股票点的 z 值
    const zKey = `z_${metric}` as keyof StockPoint;
    const updatedStocks = terrainData.stocks.map((s) => ({
      ...s,
      z: (s[zKey] as number) ?? s.z,
    }));

    set({
      zMetric: metric,
      terrainData: {
        ...terrainData,
        terrain_grid: newGrid,
        stocks: updatedStocks,
        bounds: {
          ...terrainData.bounds,
          zmin: metricBounds.zmin,
          zmax: metricBounds.zmax,
        },
        active_metric: metric,
      },
    });
  },

  // 全量计算
  fetchTerrain: async () => {
    set({ isLoading: true, error: null });
    try {
      const {
        zMetric, radiusScale,
        weightEmbedding, weightIndustry, weightNumeric,
        pcaTargetDim, embeddingPcaDim,
      } = get();
      const res = await fetch("/api/v1/terrain/compute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          z_metric: zMetric,
          resolution: 128,
          radius_scale: radiusScale,
          weight_embedding: weightEmbedding,
          weight_industry: weightIndustry,
          weight_numeric: weightNumeric,
          pca_target_dim: pcaTargetDim,
          embedding_pca_dim: embeddingPcaDim,
        }),
      });

      if (!res.ok) {
        const errBody = await res.text();
        throw new Error(`HTTP ${res.status}: ${errBody}`);
      }
      const data: TerrainData = await res.json();

      set({
        terrainData: data,
        isLoading: false,
        lastUpdateTime: new Date(),
      });
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : "获取地形数据失败",
        isLoading: false,
      });
    }
  },

  // 快速刷新 Z 轴
  refreshTerrain: async () => {
    const { zMetric } = get();
    try {
      const res = await fetch(
        `/api/v1/terrain/refresh?z_metric=${zMetric}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: TerrainData = await res.json();
      set({ terrainData: data, lastUpdateTime: new Date() });
    } catch (e) {
      console.error("刷新失败:", e);
    }
  },
}));
