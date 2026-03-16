"""Agent 接口契约 — 请求、响应、中间数据结构"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """分析请求"""
    trigger_type: Literal["user", "schedule", "event"]
    target: str = Field(description="股票代码如 '600519'，或板块名如 '白酒'")
    target_type: Literal["stock", "sector", "market"] = "stock"
    depth: Literal["quick", "standard", "deep"] = "standard"
    user_context: dict | None = None
    event_payload: dict | None = None


class Evidence(BaseModel):
    """单条论据"""
    factor: str
    value: str
    impact: Literal["positive", "negative", "neutral"]
    weight: float = Field(ge=0.0, le=1.0)


class AgentVerdict(BaseModel):
    """单个 Agent 的分析结论"""
    agent_role: str
    signal: Literal["bullish", "bearish", "neutral"]
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]
    risk_flags: list[str]
    metadata: dict = Field(default_factory=dict)


class AggregatedReport(BaseModel):
    """聚合报告"""
    target: str
    overall_signal: Literal["bullish", "bearish", "neutral"]
    overall_score: float = Field(ge=-1.0, le=1.0)
    verdicts: list[AgentVerdict]
    conflicts: list[str]
    summary: str
    risk_level: Literal["low", "medium", "high"]
    timestamp: datetime


class PreScreenResult(BaseModel):
    """预检结果"""
    should_continue: bool
    reason: str | None = None
    critical_events: list[dict] = Field(default_factory=list)
    fast_verdict: AggregatedReport | None = None


# ── 专家辩论系统数据结构 ─────────────────────────────────────


class DataRequest(BaseModel):
    """专家向引擎下发的数据补充请求"""
    requested_by: str                    # 提出请求的角色 ID
    engine: str                          # "data" | "quant" | "info"
    action: str                          # 具体操作名
    params: dict = Field(default_factory=dict)
    result: Any = None                   # 执行结果，初始 None
    status: Literal["pending", "done", "failed"] = "pending"
    round: int = 0                       # 提出请求时的轮次


class DebateEntry(BaseModel):
    """单条辩论发言"""
    role: str                            # bull_expert / bear_expert / retail_investor / smart_money
    round: int

    # 辩论者专属（观察员为 None）
    stance: Literal["insist", "partial_concede", "concede"] | None = None

    # 观察员专属
    speak: bool = True                   # False = 本轮选择沉默

    # 发言内容
    argument: str = ""
    challenges: list[str] = Field(default_factory=list)
    data_requests: list[DataRequest] = Field(default_factory=list)
    confidence: float = 0.5
    inner_confidence: float | None = None  # 专家内心真实 confidence（评委小评系统用）
    retail_sentiment_score: float | None = None  # 仅 retail_investor：+1极度乐观，-1极度悲观


class RoundEvalSide(BaseModel):
    """评委对单方的每轮评估"""
    self_confidence: float = Field(ge=0.0, le=1.0, description="专家公开宣称的 confidence")
    inner_confidence: float = Field(ge=0.0, le=1.0, description="专家内心真实 confidence")
    judge_confidence: float = Field(ge=0.0, le=1.0, description="评委客观评估的 confidence")

class RoundEval(BaseModel):
    """评委每轮小评"""
    round: int
    bull: RoundEvalSide
    bear: RoundEvalSide
    bull_reasoning: str = ""
    bear_reasoning: str = ""
    data_utilization: dict = Field(default_factory=dict)


# IndustryCognition 已迁移至 industry_engine.schemas，此处 re-export 保持兼容
from industry_engine.schemas import IndustryCognition  # noqa: F401


class Blackboard(BaseModel):
    """辩论共享状态 — 所有参与者读写的中心桌面"""
    target: str
    code: str = ""                       # 解析出的股票代码，空字符串表示未解析或非股票辩题
    debate_id: str                       # "{target}_{YYYYMMDDHHMMSS}"
    as_of_date: str = ""                 # 辩论时间锚点（最新交易日 YYYY-MM-DD），数据拉取以此为 end
    mode: Literal["standard", "fast"] = "standard"  # 辩论模式：standard=全量数据, fast=LLM预压缩
    industry_cognition: IndustryCognition | None = None  # 行业认知
    facts_summary: str | None = None     # 快速模式下的 LLM 压缩摘要

    # 事实层（Phase 2/3 产出，只读）
    facts: dict[str, Any] = Field(default_factory=dict)
    worker_verdicts: list[AgentVerdict] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)

    # 辩论层
    transcript: list[DebateEntry] = Field(default_factory=list)

    # 数据请求层
    data_requests: list[DataRequest] = Field(default_factory=list)

    # 评委每轮评估
    round_evals: list[RoundEval] = Field(default_factory=list)

    # 控制层
    round: int = 0
    max_rounds: int = 3
    bull_conceded: bool = False
    bear_conceded: bool = False
    status: Literal["debating", "final_round", "judging", "completed"] = "debating"
    termination_reason: Literal[
        "bull_conceded", "bear_conceded", "both_conceded", "max_rounds"
    ] | None = None


class JudgeVerdict(BaseModel):
    """裁判最终总结"""
    target: str
    debate_id: str
    summary: str
    signal: Literal["bullish", "bearish", "neutral"] | None = None
    score: float | None = None

    key_arguments: list[str]
    bull_core_thesis: str
    bear_core_thesis: str
    retail_sentiment_note: str
    smart_money_note: str
    risk_warnings: list[str]
    debate_quality: Literal["consensus", "strong_disagreement", "one_sided"]
    termination_reason: str
    timestamp: datetime
