"""Agent 接口契约 — 请求、响应、中间数据结构"""

from datetime import datetime
from typing import Literal

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
