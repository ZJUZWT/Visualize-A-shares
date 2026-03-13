/**
 * StockTerrain v2.0 核心类型定义
 * 前后端共享的数据契约
 */

/** 同簇关联股票 */
export interface RelatedStock {
  code: string;
  name: string;
  industry: string;
  pct_chg: number;
}

/** 跨簇相似股票 */
export interface SimilarStock {
  code: string;
  name: string;
  industry: string;
  pct_chg: number;
  cluster_id: number;
}

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
  // v8.0: 委比
  z_wb_ratio?: number;
  // v7.0: 明日上涨概率
  z_rise_prob?: number;
  // v3.1: 同簇关联股票
  related_stocks?: RelatedStock[];
  // v4.0: 跨簇相似股票
  similar_stocks?: SimilarStock[];
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
  // v4.0: 自动生成的语义标签
  label?: string;
}

/** 聚类质量评分 */
export interface ClusterQuality {
  silhouette_score: number;    // [-1, 1]，越高越好
  calinski_harabasz: number;   // 越高越好
  noise_ratio: number;         // 噪声比例
  n_clusters: number;          // 簇数
  avg_cluster_size: number;    // 平均簇大小
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

  // v4.0: 聚类质量评分
  cluster_quality?: ClusterQuality;
}

/** Z 轴可选指标 */
export type ZMetric = "pct_chg" | "turnover_rate" | "volume" | "amount" | "pe_ttm" | "pb" | "wb_ratio" | "rise_prob";

/** Z 轴指标显示信息 */
export const Z_METRIC_LABELS: Record<ZMetric, string> = {
  pct_chg: "涨跌幅 %",
  turnover_rate: "换手率 %",
  volume: "成交量",
  amount: "成交额",
  pe_ttm: "市盈率(TTM)",
  pb: "市净率",
  wb_ratio: "委比 %",
  rise_prob: "🔮 明日上涨概率",
};

/** Z 轴指标图标 */
export const Z_METRIC_ICONS: Record<ZMetric, string> = {
  pct_chg: "📈",
  turnover_rate: "🔄",
  volume: "📊",
  amount: "💰",
  pe_ttm: "📋",
  pb: "📖",
  wb_ratio: "⚖️",
  rise_prob: "🔮",
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

/**
 * 根据当前 Z 轴指标格式化股票数值展示
 * @param stock   股票点数据
 * @param metric  当前 Z 轴指标
 * @returns { text: 格式化文本, color: 颜色 }
 */
export function formatZValue(
  stock: StockPoint,
  metric: ZMetric,
): { text: string; color: string } {
  // 获取当前指标对应的 z_ 字段值
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = (stock as any)[`z_${metric}`] as number | undefined;
  const val = raw ?? stock.z;

  switch (metric) {
    case "rise_prob": {
      // 后端存的是 prob - 0.5（范围 -0.5~+0.5），加回 50% 还原为真实概率
      const pct = (val + 0.5) * 100;
      const text = `${pct.toFixed(1)}%`;
      // 概率着色：>55% 看涨红 | <45% 看跌绿 | 中性灰
      const color =
        pct > 55 ? "#EF4444" : pct < 45 ? "#22C55E" : "#9CA3AF";
      return { text, color };
    }
    case "pct_chg":
    case "turnover_rate":
    case "wb_ratio": {
      // 百分比类指标
      const sign = val > 0 ? "+" : "";
      const text = `${sign}${val.toFixed(2)}%`;
      const color =
        val > 0 ? "#EF4444" : val < 0 ? "#22C55E" : "#9CA3AF";
      return { text, color };
    }
    case "volume": {
      // 成交量（手）→ 万/亿
      let text: string;
      if (Math.abs(val) >= 1e8) text = `${(val / 1e8).toFixed(1)}亿`;
      else if (Math.abs(val) >= 1e4) text = `${(val / 1e4).toFixed(1)}万`;
      else text = val.toFixed(0);
      return { text, color: "#6B7BF7" };
    }
    case "amount": {
      // 成交额（元）→ 万/亿
      let text: string;
      if (Math.abs(val) >= 1e8) text = `${(val / 1e8).toFixed(2)}亿`;
      else if (Math.abs(val) >= 1e4) text = `${(val / 1e4).toFixed(0)}万`;
      else text = val.toFixed(0);
      return { text, color: "#F59E0B" };
    }
    case "pe_ttm": {
      const text = val > 0 ? `PE ${val.toFixed(1)}` : "PE -";
      return { text, color: "#8B5CF6" };
    }
    case "pb": {
      const text = val > 0 ? `PB ${val.toFixed(2)}` : "PB -";
      return { text, color: "#EC4899" };
    }
    default: {
      const sign = val > 0 ? "+" : "";
      return {
        text: `${sign}${val.toFixed(2)}`,
        color: val > 0 ? "#EF4444" : val < 0 ? "#22C55E" : "#9CA3AF",
      };
    }
  }
}
