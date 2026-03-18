/** 产业链图谱类型定义 */

/** 产业环节的物理约束 */
export interface PhysicalConstraint {
  node: string;
  shutdown_recovery_time: string;
  restart_cost: string;
  capacity_ramp_curve: string;
  capacity_ceiling: string;
  expansion_lead_time: string;
  logistics_mode: string;
  logistics_bottleneck: string;
  logistics_vulnerability: string;
  substitution_path: string;
  switching_cost: string;
  switching_time: string;
  inventory_buffer_days: string;
  strategic_reserve: string;
  import_dependency: string;
  export_ratio: string;
  key_trade_routes: string;
}

/** 产业链图谱节点 */
export interface ChainNode {
  id: string;
  name: string;
  node_type: "material" | "industry" | "company" | "event" | "logistics" | "macro" | "commodity";
  impact: "benefit" | "hurt" | "neutral" | "source";
  impact_score: number;
  /** 价格变动方向 — 商品/材料节点沿产业链同向传导 */
  price_change: number; // -1.0(暴跌) ~ +1.0(暴涨)，0=无变动
  depth: number;
  representative_stocks: string[];
  constraint: PhysicalConstraint | null;
  summary: string;
  // react-force-graph 需要的位置字段（可选）
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

/** 产业链传导边 */
export interface ChainLink {
  source: string;
  target: string;
  relation: string;
  impact: "positive" | "negative" | "neutral";
  impact_reason: string;
  confidence: number;
  transmission_speed: string;
  transmission_strength: string;
  transmission_mechanism: string;
  dampening_factors: string[];
  amplifying_factors: string[];
  constraint: PhysicalConstraint | null;
}

/** 用户施加的冲击 */
export interface NodeShock {
  node_name: string;
  shock: number; // -1.0 ~ +1.0
  shock_label: string;
}

/** SSE 事件 */
export interface ChainSSEEvent {
  event: string;
  data: Record<string, unknown>;
}

/** 探索状态 */
export type ExploreStatus =
  | "idle"
  | "building"     // 构建中性网络中
  | "ready"        // 网络已建好，等待用户操控
  | "simulating"   // 冲击传播推演中
  | "exploring"    // 旧模式兼容
  | "expanding"
  | "adding"       // 正在添加节点
  | "done"
  | "error";

/** 节点颜色映射（A股风格：红涨绿跌）*/
export const IMPACT_COLORS: Record<string, string> = {
  benefit: "#ef4444",   // 红色 — 利好/涨（A股红涨）
  hurt: "#22c55e",      // 绿色 — 利空/跌（A股绿跌）
  neutral: "#64748b",   // 灰色 — 中性（未被冲击）
  source: "#3b82f6",    // 蓝色 — 事件源 / 冲击源
};

/** 节点类型图标映射 */
export const NODE_TYPE_ICONS: Record<string, string> = {
  material: "⚗️",
  industry: "🏭",
  company: "🏢",
  event: "⚡",
  logistics: "🚢",
  macro: "🌍",
  commodity: "💰",
};

/** 节点类型底色（neutral 状态下按类型区分） */
export const NODE_TYPE_BASE_COLORS: Record<string, string> = {
  material: "#64748b",
  industry: "#64748b",
  company: "#6366f1",
  event: "#f59e0b",
  logistics: "#06b6d4",
  macro: "#8b5cf6",
  commodity: "#d97706",
};
