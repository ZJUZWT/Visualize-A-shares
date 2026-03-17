export interface ScheduledTask {
  id: string;
  name: string;
  expert_type: string;
  persona: string;
  message: string;
  cron_expr: string;
  session_id: string | null;
  status: "active" | "paused";
  last_run_at: string | null;
  last_result_summary: string | null;
  next_run_at: string | null;
  created_at: string;
}

export interface CreateTaskRequest {
  name: string;
  expert_type: string;
  persona?: string;
  message: string;
  cron_expr: string;
  create_session?: boolean;
}

/** cron 预设 */
export const CRON_PRESETS = [
  { label: "每日收盘后 (15:00)", value: "0 15 * * 1-5" },
  { label: "每日开盘前 (9:15)", value: "15 9 * * 1-5" },
  { label: "每周一早盘 (9:30)", value: "30 9 * * 1" },
  { label: "每周五收盘 (15:00)", value: "0 15 * * 5" },
  { label: "每日午盘 (11:30)", value: "30 11 * * 1-5" },
] as const;

/** 专家类型选项 */
export const EXPERT_OPTIONS = [
  { value: "rag", label: "🧠 总顾问（综合分析）" },
  { value: "short_term", label: "⚡ 短线专家" },
  { value: "data", label: "📊 数据专家" },
  { value: "quant", label: "🔬 量化专家" },
  { value: "info", label: "📰 资讯专家" },
  { value: "industry", label: "🏭 产业链专家" },
] as const;
