"""InfoEngine 数据模型"""

from typing import Literal
from pydantic import BaseModel


class NewsArticle(BaseModel):
    """新闻文章 — 带可选情感标注"""
    title: str
    content: str | None = None
    source: str
    publish_time: str
    url: str | None = None
    sentiment: Literal["positive", "negative", "neutral"] | None = None
    sentiment_score: float | None = None  # -1.0 ~ 1.0


class Announcement(BaseModel):
    """公司公告 — 带可选情感标注"""
    title: str
    type: str
    date: str
    url: str | None = None
    sentiment: Literal["positive", "negative", "neutral"] | None = None


class SentimentResult(BaseModel):
    """情感分析结果"""
    sentiment: Literal["positive", "negative", "neutral"]
    score: float  # -1.0 ~ 1.0
    reason: str | None = None


class EventImpact(BaseModel):
    """事件影响评估结果"""
    event_desc: str
    impact: Literal["positive", "negative", "neutral"]
    magnitude: Literal["high", "medium", "low"]
    reasoning: str
    affected_factors: list[str]
