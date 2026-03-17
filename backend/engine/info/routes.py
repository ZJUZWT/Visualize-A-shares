"""信息引擎 REST API

路由前缀: /api/v1/info/*
注: 路线图原定 /api/v1/news/*，改为 /api/v1/info/* 因为覆盖新闻+公告+事件评估
"""

import asyncio

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from pydantic import BaseModel
from loguru import logger

from engine.info import get_info_engine

router = APIRouter(prefix="/api/v1/info", tags=["info"])


@router.get("/health")
async def info_health():
    """信息引擎健康检查"""
    ie = get_info_engine()
    return ie.health_check()


@router.get("/news/{code}")
async def get_news(
    code: str = PathParam(..., pattern=r"^\d{6}$"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """获取个股新闻 + 情感分析"""
    ie = get_info_engine()
    news = await ie.get_news(code, limit)

    # 情感统计
    summary = {"positive": 0, "negative": 0, "neutral": 0}
    for n in news:
        if n.sentiment in summary:
            summary[n.sentiment] += 1

    return {
        "code": code,
        "news": [n.model_dump() for n in news],
        "sentiment_summary": summary,
    }


@router.get("/announcements/{code}")
async def get_announcements(
    code: str = PathParam(..., pattern=r"^\d{6}$"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """获取公司公告 + 情感分析"""
    ie = get_info_engine()
    announcements = await ie.get_announcements(code, limit)
    return {
        "code": code,
        "announcements": [a.model_dump() for a in announcements],
    }


class AssessRequest(BaseModel):
    code: str
    event_desc: str


@router.post("/assess")
async def assess_event(req: AssessRequest):
    """事件影响评估"""
    ie = get_info_engine()
    impact = await ie.assess_event_impact(req.code, req.event_desc)
    return impact.model_dump()
