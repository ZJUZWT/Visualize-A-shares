"""
数据引擎 REST API — /api/v1/data/*

提供行情快照、公司概况、日线历史等数据查询接口。
"""

import asyncio

from fastapi import APIRouter, Query, HTTPException
from loguru import logger

from . import get_data_engine
from .schemas import KlineFrequency

router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.get("/health")
async def data_health():
    """数据引擎健康检查"""
    de = get_data_engine()
    return de.health_check()


@router.get("/snapshot")
async def get_snapshot(
    limit: int = Query(6000, description="返回条数限制"),
    offset: int = Query(0, description="偏移量"),
):
    """获取最新行情快照"""
    de = get_data_engine()
    df = await asyncio.to_thread(de.get_snapshot)
    if df.empty:
        return {"stocks": [], "total": 0}

    total = len(df)
    df = df.iloc[offset:offset + limit]
    stocks = df.to_dict(orient="records")
    return {"stocks": stocks, "total": total}


@router.get("/snapshot/dates")
async def get_snapshot_dates():
    """获取历史快照日期列表"""
    de = get_data_engine()
    dates = de.get_snapshot_daily_dates()
    return {"dates": dates, "count": len(dates)}


@router.get("/snapshot/history")
async def get_snapshot_history(
    days: int = Query(7, description="回溯天数"),
):
    """获取指定日期范围的历史快照"""
    de = get_data_engine()
    snapshots = await asyncio.to_thread(de.get_snapshot_daily_range, days)
    result = {}
    for date_str, df in snapshots.items():
        result[date_str] = {
            "count": len(df),
            "stocks": df.to_dict(orient="records"),
        }
    return {"days": len(result), "snapshots": result}


@router.get("/snapshot/{code}")
async def get_snapshot_by_code(code: str):
    """获取单只股票的行情快照"""
    de = get_data_engine()
    df = await asyncio.to_thread(de.get_snapshot)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"未找到股票: {code}")
    row = df[df["code"] == code]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"未找到股票: {code}")
    return row.iloc[0].to_dict()


@router.get("/daily/{code}")
async def get_daily(
    code: str,
    days: int = Query(60, description="回溯天数"),
):
    """获取个股日线历史"""
    import datetime
    de = get_data_engine()
    end = datetime.date.today().strftime("%Y-%m-%d")
    start = (datetime.date.today() - datetime.timedelta(days=days + 10)).strftime("%Y-%m-%d")
    df = await asyncio.to_thread(de.get_daily_history, code, start, end)
    if df.empty:
        return {"code": code, "records": [], "count": 0}
    return {
        "code": code,
        "records": df.to_dict(orient="records"),
        "count": len(df),
    }


@router.get("/kline/{code}")
async def get_kline(
    code: str,
    frequency: KlineFrequency = KlineFrequency.MIN_60,
    days: int = Query(5, description="回溯天数"),
):
    """获取分钟级 K 线数据"""
    if frequency == KlineFrequency.DAILY:
        raise HTTPException(
            status_code=400,
            detail="日线请使用 /daily/{code} 端点",
        )
    de = get_data_engine()
    df = await asyncio.to_thread(de.get_kline, code, frequency.value, days)
    if df.empty:
        return {"code": code, "frequency": frequency.value, "records": [], "count": 0}
    # datetime 列转字符串，NaN/Inf 替换确保 JSON 可序列化
    import math
    if "datetime" in df.columns:
        df["datetime"] = df["datetime"].astype(str)
    records = df.to_dict(orient="records")
    # 清理 NaN/Inf（pandas to_dict 会保留 float('nan')）
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                rec[k] = None
    return {
        "code": code,
        "frequency": frequency.value,
        "records": records,
        "count": len(records),
    }


@router.get("/profiles")
async def get_profiles(
    q: str = Query("", description="搜索关键词（代码/名称/行业）"),
    limit: int = Query(50, description="返回条数限制"),
):
    """获取公司概况列表"""
    de = get_data_engine()
    profiles = de.get_profiles()

    if q:
        q_lower = q.lower()
        filtered = {
            code: p for code, p in profiles.items()
            if q_lower in code.lower()
            or q_lower in p.get("name", "").lower()
            or q_lower in p.get("industry", "").lower()
        }
    else:
        filtered = profiles

    items = list(filtered.values())[:limit]
    return {"profiles": items, "total": len(filtered)}


@router.get("/profiles/{code}")
async def get_profile(code: str):
    """获取单只公司概况"""
    de = get_data_engine()
    profile = de.get_profile(code)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"未找到股票: {code}")
    return profile


@router.post("/fetch/realtime")
async def fetch_realtime():
    """触发实时行情拉取并保存"""
    de = get_data_engine()
    try:
        snapshot = await asyncio.to_thread(de.get_realtime_quotes)
        await asyncio.to_thread(de.save_snapshot, snapshot)
        return {"status": "ok", "stock_count": len(snapshot)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"行情拉取失败: {str(e)}")


@router.get("/assets/search")
async def search_assets(
    q: str = Query(..., description="搜索关键词"),
    market: str = Query("all", description="市场: all/cn/hk/us/fund/futures"),
    limit: int = Query(20, description="返回条数限制"),
):
    de = get_data_engine()
    return {"results": de.search_assets(q, market=market, limit=limit), "market": market}


@router.get("/assets/profile")
async def get_asset_profile(
    symbol: str = Query(..., description="标的代码"),
    market: str = Query(..., description="市场"),
):
    de = get_data_engine()
    return de.get_asset_profile(symbol, market)


@router.get("/assets/quote")
async def get_asset_quote(
    symbol: str = Query(..., description="标的代码"),
    market: str = Query(..., description="市场"),
):
    de = get_data_engine()
    return de.get_asset_quote(symbol, market)


@router.get("/assets/daily")
async def get_asset_daily(
    symbol: str = Query(..., description="标的代码"),
    market: str = Query(..., description="市场"),
    start: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    de = get_data_engine()
    return de.get_asset_daily_history(symbol, market, start, end)
