export type ExpertType = "data" | "quant" | "info" | "industry" | "rag" | "short_term";

export interface ExpertProfile {
  type: ExpertType;
  name: string;
  icon: string;
  color: string;
  description: string;
  suggestions: string[];
}

export type ExpertEventType =
  | "thinking_start"
  | "reasoning_summary"
  | "thinking_round"
  | "graph_recall"
  | "tool_call"
  | "tool_result"
  | "reply_token"
  | "reply_complete"
  | "belief_updated"
  | "error";

export interface GraphNode {
  id: string;
  type: "stock" | "sector" | "event" | "belief" | "stance";
  label: string;
  confidence?: number;
}

export interface ToolCallData {
  engine: string;
  action: string;
  params: Record<string, unknown>;
  /** 展示标签，如 "咨询📊 数据专家" 或 "data.get_daily_history" */
  label?: string;
  /** 多轮渐进模式：所属轮次 */
  round?: number | null;
}

export interface ToolResultData {
  engine: string;
  action: string;
  summary: string;
  /** 展示标签，如 "📊 数据专家" 或 action 名 */
  label?: string;
  /** 专家完整回复内容（仅专家调用有值） */
  content?: string;
  /** 工具调用是否失败 */
  hasError?: boolean;
  /** 多轮渐进模式：所属轮次 */
  round?: number | null;
  /** K 线图表数据（query_history/query_hourly 时有值） */
  chartData?: {
    code: string;
    records: Array<{
      date?: string;
      datetime?: string;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
      [key: string]: unknown;
    }>;
  };
}

export interface BeliefUpdatedData {
  old: { id: string; content: string; confidence: number };
  new: { id: string; content: string; confidence: number };
  reason: string;
}

export interface ClarificationSubChoice {
  id: string;
  label: string;  // "①"
  text: string;    // "短线（1-5日）"
}

export interface ClarificationOption {
  id: string;
  label: string;
  title: string;
  description: string;
  focus: string;
  sub_choices?: ClarificationSubChoice[];
}

export interface ClarificationRequestData {
  should_clarify: boolean;
  question_summary: string;
  options: ClarificationOption[];
  reasoning: string;
  skip_option: ClarificationOption;
  /** 多轮澄清：是否需要继续追问 */
  needs_more?: boolean;
  /** 多轮澄清：当前轮次 */
  round?: number;
  /** 多轮澄清：最大轮数 */
  max_rounds?: number;
  /** 是否允许多选 */
  multi_select?: boolean;
}

export interface ClarificationSelection {
  option_id: string;
  label: string;
  title: string;
  focus: string;
  skip: boolean;
  sub_choice_id?: string | null;
  sub_choice_text?: string | null;
}

/** 多轮澄清中每一轮的用户选择（支持多选） */
export interface ClarificationRoundSelection {
  round: number;
  selections: ClarificationSelection[];  // 本轮所有选择（多选时>1）
  // 旧字段保留向后兼容
  option_id?: string;
  label?: string;
  title?: string;
  focus?: string;
  skip?: boolean;
}

export interface ReasoningSummaryData {
  summary: string;
}

export interface SelfCritiqueData {
  summary: string;
  risks: string[];
  missing_data: string[];
  counterpoints: string[];
  confidence_note: string;
}

export type ThinkingItem =
  | {
      type: "clarification_request";
      data: ClarificationRequestData;
      status: "pending" | "selected" | "skipped";
      selectedOption?: ClarificationSelection;
      /** 多选模式下的所有选中项 */
      selectedOptions?: ClarificationSelection[];
      /** 多轮澄清：该卡片所属轮次 */
      round?: number;
    }
  | { type: "graph_recall"; nodes: GraphNode[] }
  | { type: "reasoning_summary"; data: ReasoningSummaryData }
  | { type: "thinking_round"; round: number; maxRounds: number }
  | { type: "tool_call"; data: ToolCallData; result?: ToolResultData; status: "pending" | "done" | "error" }
  | { type: "tool_result"; data: ToolResultData }
  | { type: "self_critique"; data: SelfCritiqueData }
  | { type: "belief_updated"; data: BeliefUpdatedData };

export interface ExpertMessage {
  id: string;
  role: "user" | "expert";
  content: string;
  thinking: ThinkingItem[];
  isStreaming: boolean;
  /** 用户消息的发送状态（仅 role=user 时有意义） */
  sendStatus?: "pending" | "sent" | "failed";
  /** 消息完成状态（仅 role=expert 时有意义）— partial 表示流中断未完成 */
  status?: "completed" | "partial";
  /** DB 中的消息 ID（用于 resume 续写） */
  dbMessageId?: string;
  /** 用户发送的图片（base64，仅 role=user 时有值） */
  images?: string[];
}

export type ExpertStatus = "idle" | "clarifying" | "thinking" | "error";

export interface PendingClarification {
  sessionId: string | null;
  userMessageId: string;
  expertMessageId: string;
  request: ClarificationRequestData;
  originalMessage: string;
  /** 多轮澄清：之前所有轮次的用户选择 */
  previousSelections: ClarificationRoundSelection[];
}

/** 对话 Session */
export interface Session {
  id: string;
  expert_type: ExpertType;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/** 硬编码的专家默认配置（API 不可用时的 fallback） */
export const DEFAULT_EXPERT_PROFILES: ExpertProfile[] = [
  {
    type: "data",
    name: "数据专家",
    icon: "📊",
    color: "#60A5FA",
    description: "行情查询、股票搜索、聚类分析、全市场概览",
    suggestions: ["今日全市场概览", "搜索新能源相关股票", "查询聚类 0 的成分股", "帮我看看茅台的详情"],
  },
  {
    type: "quant",
    name: "量化专家",
    icon: "🔬",
    color: "#A78BFA",
    description: "技术指标、因子评分、IC 回测、条件选股",
    suggestions: ["贵州茅台的技术指标如何？", "查看因子体系全景", "PE低于20且换手率大于3%的股票", "运行因子IC回测"],
  },
  {
    type: "info",
    name: "资讯专家",
    icon: "📰",
    color: "#F59E0B",
    description: "新闻情感、公告解读、事件影响评估",
    suggestions: ["宁德时代最近有什么新闻？", "比亚迪近期公告", "评估降息对银行股的影响", "半导体行业最近的市场情绪"],
  },
  {
    type: "industry",
    name: "产业链专家",
    icon: "🏭",
    color: "#10B981",
    description: "行业认知、产业链映射、资金构成、周期分析",
    suggestions: ["半导体产业链分析", "锂电池行业现在处于什么周期？", "查看白酒行业板块成分股", "宁德时代的资金构成如何？"],
  },
  {
    type: "rag",
    name: "投资顾问",
    icon: "🧠",
    color: "#EC4899",
    description: "自由对话、知识图谱、信念系统、综合分析",
    suggestions: ["宁德时代近期走势如何？", "A股政策面有什么变化？", "新能源板块值得关注吗？", "帮我做一份市场研判"],
  },
  {
    type: "short_term",
    name: "短线专家",
    icon: "⚡",
    color: "#F97316",
    description: "短线交易、量价节奏、板块轮动、1-5日操作策略",
    suggestions: ["今天有什么短线机会？", "这只票现在能不能做？", "帮我看下支撑位和止损位", "这个板块谁是龙头？"],
  },
];
