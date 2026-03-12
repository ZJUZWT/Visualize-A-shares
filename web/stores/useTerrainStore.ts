/**
 * 地形状态管理 v3.0 (Zustand)
 *
 * v3.0 新增：
 * - 静态快照模式（GitHub Pages 部署时自动加载预计算数据）
 * - 多指标网格缓存（切换指标零延迟）
 * - 影响半径滑块控制
 */

import { create } from "zustand";
import type { TerrainData, StockPoint, ZMetric } from "@/types/terrain";

/** 获取资源的 base path（兼容 GitHub Pages 子路径部署） */
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

/** 是否为静态部署模式（无后端 API） */
const IS_STATIC = process.env.NEXT_PUBLIC_STATIC_MODE === "true";

interface TerrainState {
  // ─── 数据 ────────────────────────────
  terrainData: TerrainData | null;
  isLoading: boolean;
  error: string | null;
  lastUpdateTime: Date | null;
  isStaticMode: boolean;

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

  // v6.0: XY 轴缩放控制
  xyScale: number;      // 整体 XY 缩放
  xScaleRatio: number;  // X 轴比例因子 (相对于 xyScale)
  yScaleRatio: number;  // Y 轴比例因子 (相对于 xyScale)

  // v6.1: 网格分辨率
  gridResolution: number;

  // v3.0: 聚类权重
  weightEmbedding: number;
  weightIndustry: number;
  weightNumeric: number;
  pcaTargetDim: number;
  embeddingPcaDim: number;

  // v5.0: 球体拍平
  flattenBalls: boolean;

  // v6.2: 球体垂线（到 Y=0 平面）
  showDropLines: boolean;

  // v5.0: 历史回放
  playbackFrames: PlaybackFrame[] | null;
  playbackIndex: number;
  isPlaying: boolean;
  playbackSpeed: number; // 秒/帧
  playbackLoading: boolean;

  // ─── Actions ─────────────────────────
  setTerrainData: (data: TerrainData) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedStock: (stock: StockPoint | null) => void;
  setHoveredStock: (stock: StockPoint | null) => void;
  setZMetric: (metric: ZMetric) => void;
  setRadiusScale: (scale: number) => void;
  setHeightScale: (scale: number) => void;
  setXYScale: (scale: number) => void;
  setXScaleRatio: (ratio: number) => void;
  setYScaleRatio: (ratio: number) => void;
  setGridResolution: (res: number) => void;
  setWeightEmbedding: (v: number) => void;
  setWeightIndustry: (v: number) => void;
  setWeightNumeric: (v: number) => void;
  setPcaTargetDim: (v: number) => void;
  setEmbeddingPcaDim: (v: number) => void;
  toggleLabels: () => void;
  toggleGrid: () => void;
  toggleContours: () => void;
  toggleFlattenBalls: () => void;
  toggleDropLines: () => void;
  fetchTerrain: () => Promise<void>;
  refreshTerrain: () => Promise<void>;
  loadSnapshot: () => Promise<void>;
  
  // v2.0: 本地切换指标（零延迟）
  switchMetricLocal: (metric: ZMetric) => void;

  // v5.0: 历史回放
  fetchHistory: (days?: number) => Promise<void>;
  setPlaybackIndex: (index: number) => void;
  togglePlayback: () => void;
  setPlaybackSpeed: (speed: number) => void;
  stopPlayback: () => void;
}

/** 历史回放帧 */
export interface PlaybackFrame {
  date: string;
  terrain_grid: number[];
  bounds: { xmin: number; xmax: number; ymin: number; ymax: number; zmin: number; zmax: number };
  stock_z_values: Record<string, number>; // code -> z value
}

export const useTerrainStore = create<TerrainState>((set, get) => ({
  // ─── 初始状态 ────────────────────────
  terrainData: null,
  isLoading: false,
  error: null,
  lastUpdateTime: null,
  isStaticMode: IS_STATIC,

  selectedStock: null,
  hoveredStock: null,
  zMetric: "pct_chg",
  showLabels: true,
  showGrid: true,
  showContours: true,
  radiusScale: 2.0,
  heightScale: 8.0,

  // v6.0: XY 轴缩放
  xyScale: 1.5,
  xScaleRatio: 1.0,
  yScaleRatio: 1.0,

  // v6.1: 网格分辨率
  gridResolution: 512,

  // v4.0: 聚类权重默认值（产业链拓扑）
  weightEmbedding: 2.0,
  weightIndustry: 0.0,
  weightNumeric: 0.5,
  pcaTargetDim: 50,
  embeddingPcaDim: 50,

  // v5.0: 球体拍平
  flattenBalls: false,

  // v6.2: 球体垂线
  showDropLines: false,

  // v5.0: 历史回放
  playbackFrames: null,
  playbackIndex: 0,
  isPlaying: false,
  playbackSpeed: 2.0,
  playbackLoading: false,

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
  setXYScale: (scale) => set({ xyScale: scale }),
  setXScaleRatio: (ratio) => set({ xScaleRatio: ratio }),
  setYScaleRatio: (ratio) => set({ yScaleRatio: ratio }),
  setGridResolution: (res) => set({ gridResolution: res }),
  setWeightEmbedding: (v) => set({ weightEmbedding: v }),
  setWeightIndustry: (v) => set({ weightIndustry: v }),
  setWeightNumeric: (v) => set({ weightNumeric: v }),
  setPcaTargetDim: (v) => set({ pcaTargetDim: v }),
  setEmbeddingPcaDim: (v) => set({ embeddingPcaDim: v }),

  toggleLabels: () => set((s) => ({ showLabels: !s.showLabels })),
  toggleGrid: () => set((s) => ({ showGrid: !s.showGrid })),
  toggleContours: () => set((s) => ({ showContours: !s.showContours })),
  toggleFlattenBalls: () => set((s) => ({ flattenBalls: !s.flattenBalls })),
  toggleDropLines: () => set((s) => ({ showDropLines: !s.showDropLines })),

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

  // 加载静态快照（GitHub Pages 模式）
  loadSnapshot: async () => {
    set({ isLoading: true, error: null });
    try {
      const url = `${BASE_PATH}/terrain_snapshot.json`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`加载快照失败: HTTP ${res.status}`);
      const data: TerrainData = await res.json();
      set({
        terrainData: data,
        isLoading: false,
        lastUpdateTime: new Date(),
        isStaticMode: true,
      });
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : "加载快照失败",
        isLoading: false,
      });
    }
  },

  // 全量计算（需要后端 API）
  fetchTerrain: async () => {
    // 静态模式下加载快照
    if (IS_STATIC) {
      return get().loadSnapshot();
    }

    set({ isLoading: true, error: null });
    try {
      const {
        zMetric, radiusScale, gridResolution,
        weightEmbedding, weightIndustry, weightNumeric,
        pcaTargetDim, embeddingPcaDim,
      } = get();
      const res = await fetch("/api/v1/terrain/compute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          z_metric: zMetric,
          resolution: gridResolution,
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

  // 快速刷新 Z 轴（需要后端 API）
  refreshTerrain: async () => {
    if (IS_STATIC) return; // 静态模式不支持刷新
    
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

  // v5.0: 获取历史数据帧（支持超时）
  fetchHistory: async (days = 7) => {
    if (IS_STATIC) return;
    set({ playbackLoading: true, error: null });
    try {
      const { zMetric } = get();
      
      // 60 秒超时
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 60000);
      
      const res = await fetch("/api/v1/terrain/history", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days, z_metric: zMetric }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      
      if (!res.ok) {
        const errBody = await res.text();
        // 解析后端的错误信息
        let detail = `HTTP ${res.status}`;
        try {
          const errJson = JSON.parse(errBody);
          detail = errJson.detail || detail;
        } catch {
          detail = errBody || detail;
        }
        throw new Error(detail);
      }
      const data = await res.json();
      
      if (!data.frames || data.frames.length === 0) {
        throw new Error("无可用历史帧数据");
      }
      
      set({
        playbackFrames: data.frames,
        playbackIndex: data.frames.length - 1,
        playbackLoading: false,
        isPlaying: false,
      });
    } catch (e) {
      const msg = e instanceof Error 
        ? (e.name === "AbortError" ? "请求超时，请稍后重试" : e.message) 
        : "获取历史数据失败";
      set({
        error: msg,
        playbackLoading: false,
      });
    }
  },

  setPlaybackIndex: (index) => set({ playbackIndex: index }),

  togglePlayback: () => set((s) => ({ isPlaying: !s.isPlaying })),

  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),

  stopPlayback: () => set({
    isPlaying: false,
    playbackFrames: null,
    playbackIndex: 0,
  }),
}));
