"""产业链专家 Skills — 行业认知、产业链映射、资金构成"""

import asyncio
import json

from loguru import logger

from engine.expert.skill_registry import SkillRegistry


# ─── 工具 1: query_industry_cognition ────────────────

@SkillRegistry.register(
    name="query_industry_cognition",
    description="产业链认知分析（股票代码或行业名）",
    expert_types=["industry"],
    params=[{"name": "target", "type": "str", "description": "股票代码或行业名称"}],
    category="industry",
)
async def query_industry_cognition(target: str = "", **ctx):
    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    try:
        result = await ie.analyze(target=target)
        if result:
            return json.dumps(result, ensure_ascii=False, default=str)
        return json.dumps({"error": "需要后端在线且配置 LLM 才能获取产业链认知"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"产业链认知查询失败: {e}"}, ensure_ascii=False)


# ─── 工具 2: query_industry_mapping ──────────────────

@SkillRegistry.register(
    name="query_industry_mapping",
    description="行业板块列表及成分股映射",
    expert_types=["industry"],
    params=[{"name": "industry", "type": "str", "description": "行业名称（可选）",
             "required": False}],
    category="industry",
)
async def query_industry_mapping(industry: str = None, **ctx):
    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    try:
        result = await asyncio.to_thread(ie.get_industry_mapping)
        if result:
            return json.dumps(result, ensure_ascii=False, default=str)
        return json.dumps({"empty": True, "note": "无映射数据"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"行业映射查询失败: {e}"}, ensure_ascii=False)


# ─── 工具 3: query_capital_structure ─────────────────

@SkillRegistry.register(
    name="query_capital_structure",
    description="资金构成分析（需要具体股票代码）",
    expert_types=["industry"],
    params=[{"name": "code", "type": "str", "description": "股票代码或名称"}],
    category="capital",
)
async def query_capital_structure(code: str = "", resolve_code=None, **ctx):
    # 泛化词汇拦截
    if code in ("市场整体", "A股市场", "全市场", "市场板块", "板块轮动"):
        return json.dumps({
            "error": "资金构成需要具体股票代码",
            "hint": "请使用 query_industry_mapping 查询板块成分股，或用 search_stocks 搜索具体股票",
        }, ensure_ascii=False)

    if resolve_code:
        code = resolve_code(code)

    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    try:
        result = await ie.get_capital_structure(code)
        if result:
            return json.dumps(result, ensure_ascii=False, default=str)
        return json.dumps({"empty": True, "note": f"无 {code} 资金构成数据"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"资金构成查询失败: {e}"}, ensure_ascii=False)
