"""资讯专家 Skills — 新闻情感、公告解读、事件影响评估"""

import asyncio
import json

from loguru import logger

from engine.expert.skill_registry import SkillRegistry


# ─── 工具 1: get_news ────────────────────────────────

@SkillRegistry.register(
    name="get_news",
    description="获取个股新闻+情感分析",
    expert_types=["info"],
    params=[
        {"name": "code", "type": "str", "description": "股票代码或名称"},
        {"name": "limit", "type": "int", "description": "返回条数", "default": 20},
    ],
    category="news",
)
async def get_news(code: str = "", limit: int = 20, de=None, resolve_code=None, **ctx):
    if resolve_code:
        code = resolve_code(code)
    news_df = await asyncio.to_thread(de.get_news, code, limit)
    if news_df is None or (hasattr(news_df, "empty") and news_df.empty):
        return json.dumps({"empty": True, "note": f"{code} 近期无新闻数据"}, ensure_ascii=False)
    if hasattr(news_df, "to_dict"):
        records = news_df.to_dict("records")
    else:
        records = news_df
    return json.dumps({"code": code, "news": records}, ensure_ascii=False, default=str)


# ─── 工具 2: get_announcements ──────────────────────

@SkillRegistry.register(
    name="get_announcements",
    description="获取公司公告",
    expert_types=["info"],
    params=[
        {"name": "code", "type": "str", "description": "股票代码或名称"},
        {"name": "limit", "type": "int", "description": "返回条数", "default": 10},
    ],
    category="announcements",
)
async def get_announcements(code: str = "", limit: int = 10, de=None, resolve_code=None, **ctx):
    if resolve_code:
        code = resolve_code(code)
    try:
        ann_df = await asyncio.to_thread(de.get_announcements, code, limit)
        if ann_df is None or (hasattr(ann_df, "empty") and ann_df.empty):
            return json.dumps({"empty": True, "note": f"{code} 近7天无公告"}, ensure_ascii=False)
        if hasattr(ann_df, "to_dict"):
            records = ann_df.to_dict("records")
        else:
            records = ann_df
        return json.dumps({"code": code, "announcements": records}, ensure_ascii=False, default=str)
    except AttributeError:
        return json.dumps({"error": "公告功能暂未实现"}, ensure_ascii=False)


# ─── 工具 3: assess_event_impact ────────────────────

@SkillRegistry.register(
    name="assess_event_impact",
    description="评估事件对个股的影响",
    expert_types=["info"],
    params=[
        {"name": "code", "type": "str", "description": "股票代码或名称"},
        {"name": "event_desc", "type": "str", "description": "事件描述"},
    ],
    category="event",
)
async def assess_event_impact(code: str = "", event_desc: str = "", resolve_code=None, **ctx):
    if resolve_code:
        code = resolve_code(code)
    return json.dumps({
        "code": code,
        "event": event_desc,
        "note": "事件影响评估需结合新闻和技术面综合分析",
    }, ensure_ascii=False)
