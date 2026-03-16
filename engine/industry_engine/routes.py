"""产业链引擎 API 路由"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger

from .schemas import IndustryAnalysisRequest

router = APIRouter(prefix="/api/v1/industry", tags=["industry"])


@router.post("/analyze")
async def analyze_industry(req: IndustryAnalysisRequest):
    """分析产业链认知（SSE 流式推送进度）"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()

    async def event_stream():
        yield f"event: industry_cognition_start\ndata: {json.dumps({'target': req.target}, ensure_ascii=False)}\n\n"
        try:
            cognition = await ie.analyze(
                target=req.target,
                as_of_date=req.as_of_date,
            )
            if cognition:
                yield f"event: industry_cognition_done\ndata: {json.dumps(cognition.model_dump(), ensure_ascii=False)}\n\n"
            else:
                yield f"event: industry_cognition_done\ndata: {json.dumps({'error': '无法生成行业认知'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"产业链分析失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/cognition/{target}")
async def get_cognition(target: str, as_of_date: str = ""):
    """获取产业链认知（JSON，缓存优先）"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    cognition = await ie.analyze(target=target, as_of_date=as_of_date)
    if cognition:
        return cognition.model_dump()
    return {"error": f"无法获取 {target} 的行业认知"}


@router.get("/mapping")
async def get_mapping():
    """获取行业→股票映射"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    industries = ie.list_industries()
    return {
        "total_industries": len(industries),
        "industries": [m.model_dump() for m in industries[:50]],
    }


@router.get("/mapping/{industry}")
async def get_industry_stocks(industry: str):
    """获取指定行业的全部股票"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    stocks = ie.get_industry_stocks(industry)
    return {"industry": industry, "stock_count": len(stocks), "stocks": stocks}


@router.get("/capital/{code}")
async def get_capital_structure(code: str, as_of_date: str = ""):
    """获取资金构成分析"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    cs = await ie.get_capital_structure(code, as_of_date)
    return cs.model_dump()


@router.get("/health")
async def health():
    """健康检查"""
    from industry_engine import get_industry_engine
    return get_industry_engine().health_check()
