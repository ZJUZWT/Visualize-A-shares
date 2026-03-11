/**
 * StockTerrain v2.0 核心类型定义
 * 前后端共享的数据契约
 */

/** 单只股票在 3D 空间中的表示 */
export interface StockPoint {
  code: string;
  name: string;
  x: number;
  y: number;
  z: number;
  cluster_id: number;
  // v2.0: 行业信息（来自申万分类）
  industry?: string;
  // v2.0: 所有指标的原始值
  z_pct_chg?: number;
  z_turnover_rate?: number;
  z_volume?: number;
  z_amount?: number;
  z_pe_ttm?: number;
  z_pb?: number;
}

/** 聚类簇信息 */
export interface ClusterInfo {
  cluster_id: number;
  is_noise: boolean;
  size: number;
  avg_probability: number;
  top_stocks: string[];
  stock_codes: string[];
  feature_profile: Record<string, number>;
  // v2.0: 簇内行业分布 (top 5)
  top_industries?: { name: string; count: number }[];
}

/** 地形边界 */
export interface TerrainBounds {
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
  zmin: number;
  zmax: number;
}

/** 后端返回的完整地形数据 v2.0 */
export interface TerrainData {
  stocks: StockPoint[];
  clusters: ClusterInfo[];
  
  // v2.0: 所有指标的网格
  grids: Record<string, number[]>;
  bounds_per_metric: Record<string, { zmin: number; zmax: number }>;
  
  // 兼容 v1
  terrain_grid: number[];
  terrain_resolution: number;
  bounds: TerrainBounds;
  
  stock_count: number;
  cluster_count: number;
  computation_time_ms: number;
  active_metric: string;
}

/** Z 轴可选指标 */
export type ZMetric = "pct_chg" | "turnover_rate" | "volume" | "amount" | "pe_ttm" | "pb";

/** Z 轴指标显示信息 */
export const Z_METRIC_LABELS: Record<ZMetric, string> = {
  pct_chg: "涨跌幅 %",
  turnover_rate: "换手率 %",
  volume: "成交量",
  amount: "成交额",
  pe_ttm: "市盈率(TTM)",
  pb: "市净率",
};

/** Z 轴指标图标 */
export const Z_METRIC_ICONS: Record<ZMetric, string> = {
  pct_chg: "📈",
  turnover_rate: "🔄",
  volume: "📊",
  amount: "💰",
  pe_ttm: "📋",
  pb: "📖",
};

/** v2.0 清爽简约配色方案 */
export const CLUSTER_COLORS = [
  "#4F8EF7", // 天蓝
  "#FF7E67", // 珊瑚
  "#6DD47E", // 薄荷绿
  "#FFB347", // 暖橙
  "#9B8FE8", // 薰衣草
  "#FF6B9D", // 玫瑰粉
  "#4ECDC4", // 青绿
  "#FFD93D", // 向日葵黄
  "#A8D8EA", // 浅蓝
  "#F5A6C9", // 粉红
  "#8BC6A5", // 草绿
  "#DDA0DD", // 梅红
  "#87CEEB", // 天空蓝
  "#F0E68C", // 卡其
  "#B0C4DE", // 淡钢蓝
];

/** 噪声聚类颜色 */
export const NOISE_COLOR = "#C0C0C0";
