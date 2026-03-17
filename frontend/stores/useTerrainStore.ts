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

/**
 * SSE 流式请求直连后端地址
 * Next.js rewrites 代理会缓冲 SSE 响应，导致 progress 事件无法实时推送
 * 所以 SSE 请求需要绕过代理，直接连后端
 */
const SSE_API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

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
  
  // v5.1: SSE 拉取进度
  fetchProgress: FetchProgress | null;

  // v5.2: 地形计算进度
  computeProgress: ComputeProgress | null;

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

/** SSE 拉取进度 */
export interface FetchProgress {
  phase: "checking" | "fetching" | "computing";
  message: string;
  done: number;
  total: number;
  success: number;
  failed: number;
  elapsed?: number;
}

/** 地形计算进度（步骤化） */
export interface ComputeProgress {
  step: number;
  totalSteps: number;
  stepName: string;
  message: string;
  elapsed: number;
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
  fetchProgress: null,
  computeProgress: null,

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

  // 全量计算（v5.2: SSE 流式进度推送）
  fetchTerrain: async () => {
    // 静态模式下加载快照
    if (IS_STATIC) {
      return get().loadSnapshot();
    }

    set({ isLoading: true, error: null, computeProgress: null });
    try {
      const {
        zMetric, radiusScale, gridResolution,
        weightEmbedding, weightIndustry, weightNumeric,
        pcaTargetDim, embeddingPcaDim,
      } = get();

      const res = await fetch(`${SSE_API_BASE}/api/v1/terrain/compute`, {
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
        let detail = `HTTP ${res.status}`;
        try {
          const errJson = JSON.parse(errBody);
          detail = errJson.detail || detail;
        } catch {
          detail = errBody || detail;
        }
        throw new Error(detail);
      }

      // SSE 流式读取
      const reader = res.body?.getReader();
      if (!reader) throw new Error("浏览器不支持流式读取");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const eventBlock of events) {
          if (!eventBlock.trim()) continue;

          const lines = eventBlock.split("\n");
          let eventType = "";
          let eventData = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              eventData = line.slice(6);
            }
          }

          if (!eventType || !eventData) continue;

          try {
            const parsed = JSON.parse(eventData);

            if (eventType === "progress") {
              set({ computeProgress: parsed as ComputeProgress });
            } else if (eventType === "complete") {
              set({
                terrainData: parsed as TerrainData,
                isLoading: false,
                lastUpdateTime: new Date(),
                computeProgress: null,
              });
              return; // 成功完成
            } else if (eventType === "error") {
              throw new Error(parsed.message || "地形计算失败");
            }
          } catch (parseErr) {
            if (eventType === "error" || eventType === "complete") {
              throw parseErr;
            }
          }
        }
      }

      // 流结束但没收到 complete 事件
      const { terrainData } = get();
      if (!terrainData) {
        throw new Error("数据流异常中断");
      }
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : "获取地形数据失败",
        isLoading: false,
        computeProgress: null,
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

  // v5.1: 获取历史数据帧（SSE 流式进度推送，无超时限制）
  fetchHistory: async (days = 7) => {
    if (IS_STATIC) return;
    set({ playbackLoading: true, error: null, fetchProgress: null });
    try {
      const { zMetric } = get();

      const res = await fetch(`${SSE_API_BASE}/api/v1/terrain/history`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days, z_metric: zMetric }),
      });

      if (!res.ok) {
        const errBody = await res.text();
        let detail = `HTTP ${res.status}`;
        try {
          const errJson = JSON.parse(errBody);
          detail = errJson.detail || detail;
        } catch {
          detail = errBody || detail;
        }
        throw new Error(detail);
      }

      // SSE 流式读取
      const reader = res.body?.getReader();
      if (!reader) throw new Error("浏览器不支持流式读取");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件（格式: "event: xxx\ndata: {...}\n\n"）
        const events = buffer.split("\n\n");
        buffer = events.pop() || ""; // 最后一段可能不完整

        for (const eventBlock of events) {
          if (!eventBlock.trim()) continue;

          const lines = eventBlock.split("\n");
          let eventType = "";
          let eventData = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              eventData = line.slice(6);
            }
          }

          if (!eventType || !eventData) continue;

          try {
            const parsed = JSON.parse(eventData);

            if (eventType === "progress") {
              set({ fetchProgress: parsed });
            } else if (eventType === "complete") {
              if (!parsed.frames || parsed.frames.length === 0) {
                throw new Error("无可用历史帧数据");
              }
              set({
                playbackFrames: parsed.frames,
                playbackIndex: parsed.frames.length - 1,
                playbackLoading: false,
                isPlaying: false,
                fetchProgress: null,
              });
              return; // 成功完成
            } else if (eventType === "error") {
              throw new Error(parsed.message || "历史回放失败");
            }
          } catch (parseErr) {
            // JSON 解析失败，可能是不完整的数据
            if (eventType === "error" || eventType === "complete") {
              throw parseErr;
            }
          }
        }
      }

      // 如果流结束但没收到 complete 事件
      const { playbackFrames } = get();
      if (!playbackFrames) {
        throw new Error("数据流异常中断");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "获取历史数据失败";
      set({
        error: msg,
        playbackLoading: false,
        fetchProgress: null,
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
