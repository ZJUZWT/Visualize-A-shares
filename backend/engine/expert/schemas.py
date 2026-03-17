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


class SectorNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["sector"] = "sector"
    name: str
    category: str = ""           # "industry" | "zjh" | "concept"


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


class RegionNode(BaseModel):
    """地理区域节点"""
    id: str = Field(default_factory=new_id)
    type: Literal["region"] = "region"
    name: str                    # 如 "深圳" "上海" "北京"


class BeliefNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["belief"] = "belief"
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
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
    session_id: str | None = None


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
