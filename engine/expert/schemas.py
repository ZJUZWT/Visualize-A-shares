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


class SectorNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["sector"] = "sector"
    name: str


class EventNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["event"] = "event"
    name: str
    date: str
    description: str


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


GraphNode = StockNode | SectorNode | EventNode | BeliefNode | StanceNode


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation: Literal[
        "belongs_to", "influenced_by", "supports",
        "contradicts", "updated_by", "researched"
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
