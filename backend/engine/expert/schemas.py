"""投资专家 Agent 数据结构"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid.uuid4())


class StockNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["stock"] = "stock"
    code: str
    name: str
    industry: str = ""           # 行业（如"银行"）
    zjh_industry: str = ""       # 证监会二级行业
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SectorNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["sector"] = "sector"
    name: str
    category: str = ""           # "industry" | "zjh" | "concept"
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class EventNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["event"] = "event"
    name: str
    date: str
    description: str


class MaterialNode(BaseModel):
    """原材料 / 产品 / 关键资源节点"""
    id: str = Field(default_factory=new_id)
    type: Literal["material"] = "material"
    name: str
    category: str = ""           # "raw_material" | "product" | "resource"
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class RegionNode(BaseModel):
    """地理区域节点"""
    id: str = Field(default_factory=new_id)
    type: Literal["region"] = "region"
    name: str                    # 如 "深圳" "上海" "北京"
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class BeliefNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["belief"] = "belief"
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    persona: str = "rag"         # "rag"(投资顾问) | "short_term"(短线专家)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StanceNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["stance"] = "stance"
    target: str
    signal: Literal["bullish", "bearish", "neutral"]
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


GraphNode = StockNode | SectorNode | EventNode | BeliefNode | StanceNode | MaterialNode | RegionNode


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation: Literal[
        # 组织归属
        "belongs_to",        # stock → sector (公司属于行业)
        "located_in",        # stock → region (公司注册地)
        # 产业链
        "supplies",          # stock/material → stock (供应给)
        "consumes",          # stock → material (消耗/使用)
        "upstream",          # sector → sector (上游行业)
        "downstream",        # sector → sector (下游行业)
        "competes_with",     # stock → stock (竞争关系)
        # 知识演化
        "influenced_by",     # stock → event (受事件影响)
        "supports",          # belief → belief (支持)
        "contradicts",       # belief → belief (矛盾)
        "updated_by",        # belief → belief (更新)
        "researched",        # 标记已研究
    ]
    reason: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ToolCall(BaseModel):
    engine: str
    action: str
    params: dict


class ThinkOutput(BaseModel):
    needs_data: bool
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning: str = ""


class ClarificationSubChoice(BaseModel):
    """选项内的互斥子选项（适合"你是 X 还是 Y？"型问题）"""
    id: str          # "short_term"
    label: str       # "①"
    text: str        # "短线（1-5日）"


class ClarificationOption(BaseModel):
    id: str
    label: str
    title: str
    description: str
    focus: str
    sub_choices: list[ClarificationSubChoice] = Field(default_factory=list)  # 空=普通选项，非空=问题型选项


class ClarificationOutput(BaseModel):
    should_clarify: bool = True
    question_summary: str
    options: list[ClarificationOption] = Field(default_factory=list)
    reasoning: str = ""
    skip_option: ClarificationOption
    # 多轮澄清字段
    needs_more: bool = True        # LLM 是否需要继续追问
    round: int = 1                 # 当前轮次
    max_rounds: int = 3            # 最大轮数安全限制
    multi_select: bool = False     # LLM 决定本轮是否多选


class ClarificationSelection(BaseModel):
    option_id: str
    label: str
    title: str
    focus: str
    skip: bool = False
    sub_choice_id: str | None = None    # 选中了哪个子选项
    sub_choice_text: str | None = None  # 子选项文本


class ClarificationRoundSelection(BaseModel):
    """多轮澄清中每一轮的用户选择（支持多选）"""
    round: int
    selections: list[ClarificationSelection] = Field(default_factory=list)  # 本轮所有选择（多选时>1）
    # 保留旧字段向后兼容（单选模式降级）
    option_id: str = ""
    label: str = ""
    title: str = ""
    focus: str = ""
    skip: bool = False


class ClarifyRequest(BaseModel):
    """多轮澄清请求体"""
    message: str
    session_id: str | None = None
    previous_selections: list[ClarificationRoundSelection] = Field(default_factory=list)


class SelfCritiqueOutput(BaseModel):
    summary: str
    risks: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    counterpoints: list[str] = Field(default_factory=list)
    confidence_note: str = ""


class BeliefChange(BaseModel):
    old_belief_id: str
    new_content: str
    new_confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class BeliefUpdateOutput(BaseModel):
    updated: bool
    changes: list[BeliefChange] = Field(default_factory=list)


class ExpertChatRequest(BaseModel):
    message: str
    images: list[str] = Field(default_factory=list)  # base64 编码的图片列表（粘贴/上传）
    session_id: str | None = None
    deep_think: bool = False          # 多轮渐进工具调用（AI 看数据后可以继续补查）
    max_rounds: int = Field(default=3, ge=1, le=5)  # 最大工具调用轮数
    clarification_selection: ClarificationSelection | None = None  # 向后兼容：单轮选择
    clarification_chain: list[ClarificationRoundSelection] | None = None  # 多轮澄清链
    use_clarification: bool = True
    enable_trade_plan: bool = False    # 是否启用策略卡片（交易计划）生成


class ExpertResumeRequest(BaseModel):
    """续写被中断的 expert 回复"""
    session_id: str
    message_id: str  # partial 消息的 DB id
    check_completed: bool = False  # 可选：对已 completed 但疑似截断的消息也执行完整性检查


class ResumeCompletionCheckResult(BaseModel):
    """resume 前的完整性检查结果"""
    is_complete: bool = False
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


FeedbackIssueType = Literal[
    "load_failed",
    "llm_truncated",
    "resume_misjudged_complete",
    "clarify_missing_options",
    "clarify_auto_advance",
    "clarify_subchoice_stuck",
    "other",
]

FeedbackSourceType = Literal["reply", "clarification", "resume"]


class FeedbackReportCreateRequest(BaseModel):
    session_id: str
    message_id: str
    expert_type: str = "rag"
    report_source: FeedbackSourceType = "reply"
    issue_type: FeedbackIssueType
    user_note: str = ""
    context: dict = Field(default_factory=dict)


class FeedbackResolveRequest(BaseModel):
    resolution_note: str = ""


class FeedbackSubmitResponse(BaseModel):
    ok: bool = True
    feedback_id: str


class FeedbackReportSummary(BaseModel):
    id: str
    user_id: str
    session_id: str
    message_id: str
    expert_type: str
    report_source: FeedbackSourceType
    issue_type: FeedbackIssueType
    user_note: str = ""
    message_status: str = "completed"
    created_at: str
    resolved_at: str | None = None
    resolver: str | None = None


class FeedbackReportDetail(BaseModel):
    id: str
    user_id: str
    session_id: str
    message_id: str
    expert_type: str
    report_source: FeedbackSourceType
    issue_type: FeedbackIssueType
    user_note: str = ""
    user_message: str
    assistant_content: str
    message_status: str = "completed"
    thinking_json: list = Field(default_factory=list)
    context_json: dict = Field(default_factory=dict)
    created_at: str
    resolved_at: str | None = None
    resolver: str | None = None
    resolution_note: str = ""


class FeedbackResolveResponse(BaseModel):
    ok: bool = True


class SessionCreateRequest(BaseModel):
    """创建 session 请求体"""
    expert_type: str = "rag"
    title: str = "新对话"


class SessionInfo(BaseModel):
    """对话 Session 元数据"""
    id: str = Field(default_factory=new_id)
    expert_type: str = "rag"
    title: str = "新对话"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    message_count: int = 0


class ScheduledTaskRequest(BaseModel):
    """创建定时任务请求体"""
    name: str                    # "每日看茅台"
    expert_type: str = "rag"     # rag / short_term / data / quant / info / industry
    persona: str = "rag"         # rag / short_term
    message: str                 # "帮我分析一下贵州茅台今天的走势"
    cron_expr: str               # "0 15 * * 1-5" (周一到周五15:00)
    create_session: bool = True  # 是否自动创建专属 session
