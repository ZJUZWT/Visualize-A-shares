"""数据专家 Skills — 行情查询、股票搜索、聚类分析、全市场概览

每个 Skill 通过 @SkillRegistry.register 装饰器自动注册。
handler 接收两类参数：
- LLM 传入的业务参数（code, days, filters 等）
- 上下文参数（de=DataEngine, ensure_snapshot=callable, resolve_code=callable）
"""

import asyncio
import datetime
import json

import pandas as pd
from loguru import logger

from engine.expert.skill_registry import SkillRegistry


# ─── 工具 1: get_current_date ────────────────────────

@SkillRegistry.register(
    name="get_current_date",
    description="获取当前日期、时间、星期几、是否交易日",
    expert_types=["data"],
    params=[],
    category="time",
)
async def get_current_date(**ctx):
    now = datetime.datetime.now()
    return json.dumps({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
        "is_trading_day": now.weekday() < 5,
    }, ensure_ascii=False)


# ─── 工具 2: query_market_overview ───────────────────

@SkillRegistry.register(
    name="query_market_overview",
    description="全市场概览快照，返回涨/跌/平统计",
    expert_types=["data"],
    params=[],
    category="market",
)
async def query_market_overview(de=None, ensure_snapshot=None, **ctx):
    snap = await ensure_snapshot(de) if ensure_snapshot else de.get_snapshot()
    if snap is None or snap.empty:
        return json.dumps({"error": "无快照数据，请先在主页刷新行情"}, ensure_ascii=False)

    total = len(snap)
    up = int((snap.get("pct_chg", pd.Series()) > 0).sum()) if "pct_chg" in snap.columns else 0
    down = int((snap.get("pct_chg", pd.Series()) < 0).sum()) if "pct_chg" in snap.columns else 0
    flat = total - up - down

    # ── 增强：附带 updated_at 让 LLM 知道数据时效 ──
    updated_at = ""
    if "updated_at" in snap.columns:
        try:
            updated_at = str(pd.to_datetime(snap["updated_at"]).max())
        except Exception:
            pass

    return json.dumps({
        "total_stocks": total,
        "up": up, "down": down, "flat": flat,
        "updated_at": updated_at,
    }, ensure_ascii=False)


# ─── 工具 3: search_stocks ──────────────────────────

@SkillRegistry.register(
    name="search_stocks",
    description="股票搜索（模糊匹配代码或名称）",
    expert_types=["data"],
    params=[{"name": "query", "type": "str", "description": "搜索关键词（代码或名称）"}],
    category="search",
)
async def search_stocks(query: str = "", de=None, ensure_snapshot=None, **ctx):
    snap = await ensure_snapshot(de) if ensure_snapshot else de.get_snapshot()
    if snap is None or snap.empty:
        return json.dumps({"error": "无快照数据，请先在主页刷新行情"}, ensure_ascii=False)

    q = query.lower()
    results = []
    for _, row in snap.iterrows():
        code = str(row.get("code", ""))
        name = str(row.get("name", ""))
        if q in code.lower() or q in name.lower():
            results.append({
                "code": code, "name": name,
                "price": float(row.get("price", 0)),
                "pct_chg": float(row.get("pct_chg", 0)),
            })
        if len(results) >= 20:
            break
    return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, default=str)


# ─── 工具 4: query_stock ────────────────────────────

@SkillRegistry.register(
    name="query_stock",
    description="单股全维度详情（行情+基本面+技术面），code 示例: '000001'",
    expert_types=["data"],
    params=[{"name": "code", "type": "str", "description": "股票代码或名称"}],
    category="stock",
)
async def query_stock(code: str = "", de=None, ensure_snapshot=None, resolve_code=None, **ctx):
    if resolve_code:
        code = resolve_code(code)
    snap = await ensure_snapshot(de) if ensure_snapshot else de.get_snapshot()
    if snap is None or snap.empty:
        return json.dumps({"error": "无快照数据，请先在主页刷新行情"}, ensure_ascii=False)
    row = snap[snap["code"].astype(str) == code]
    if row.empty:
        return json.dumps({"error": f"未找到 {code}"}, ensure_ascii=False)
    return row.iloc[0].to_json(force_ascii=False, default_handler=str)


# ─── 工具 5: query_history ──────────────────────────

@SkillRegistry.register(
    name="query_history",
    description="历史日线K线数据。days 是交易日天数（非日历天），用户问30天就传30，问60天就传60，默认60",
    expert_types=["data"],
    params=[
        {"name": "code", "type": "str", "description": "股票代码或名称"},
        {"name": "days", "type": "int", "description": "交易日天数", "default": 60},
    ],
    category="kline",
)
async def query_history(code: str = "", days: int = 60, de=None, resolve_code=None, **ctx):
    if resolve_code:
        code = resolve_code(code)

    calendar_days = max(days, 10) * 1.8 + 10
    today = datetime.date.today()
    end = today.strftime("%Y-%m-%d")
    start = (today - datetime.timedelta(days=int(calendar_days))).strftime("%Y-%m-%d")
    df = await asyncio.to_thread(de.get_daily_history, code, start, end)
    if df is None or df.empty:
        return json.dumps({"empty": True, "note": f"无 {code} 日线数据"}, ensure_ascii=False)

    # ── 用实时快照补充当天数据（仅交易时段） ──
    try:
        now = datetime.datetime.now()
        is_trading_hours = (
            now.weekday() < 5
            and datetime.time(9, 15) <= now.time() <= datetime.time(15, 30)
        )
        if is_trading_hours:
            snap = de.get_snapshot()
            if snap is not None and not snap.empty:
                row = snap[snap["code"].astype(str) == code]
                if not row.empty:
                    r = row.iloc[0]
                    realtime_price = float(r.get("price", 0))
                    today_str = today.strftime("%Y-%m-%d")
                    date_col = "date" if "date" in df.columns else (
                        "trade_date" if "trade_date" in df.columns else None
                    )
                    last_date = str(df[date_col].iloc[-1])[:10] if date_col else ""
                    if realtime_price > 0 and last_date != today_str:
                        prev_close = float(df["close"].iloc[-1]) if "close" in df.columns and len(df) > 0 else 0
                        pct_chg = round((realtime_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
                        new_row = {
                            "close": realtime_price,
                            "open": float(r.get("open", realtime_price)),
                            "high": float(r.get("high", realtime_price)),
                            "low": float(r.get("low", realtime_price)),
                            "volume": float(r.get("volume", 0)),
                            "amount": float(r.get("amount", 0)),
                            "pct_chg": pct_chg,
                            "turnover_rate": float(r.get("turnover_rate", 0)),
                        }
                        if date_col:
                            new_row[date_col] = today_str
                        if "code" in df.columns:
                            new_row["code"] = code
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    except Exception:
        pass

    return_rows = max(days, 20)
    records = df.tail(return_rows).to_dict("records")
    return json.dumps({"code": code, "records": records, "total_days": len(df)},
                      ensure_ascii=False, default=str)


# ─── 工具 6: query_hourly ───────────────────────────

@SkillRegistry.register(
    name="query_hourly",
    description="查询个股小时线K线（60分钟级别），默认5个交易日",
    expert_types=["data", "quant"],
    params=[
        {"name": "code", "type": "str", "description": "股票代码或名称"},
        {"name": "days", "type": "int", "description": "交易日天数", "default": 5},
    ],
    category="kline",
)
async def query_hourly(code: str = "", days: int = 5, de=None, resolve_code=None, **ctx):
    if resolve_code:
        code = resolve_code(code)
    df = await asyncio.to_thread(de.get_kline, code, "60m", days)
    if df is None or df.empty:
        return json.dumps({"empty": True, "note": f"无 {code} 小时线数据"}, ensure_ascii=False)
    records = df.tail(20).to_dict("records")
    return json.dumps({"code": code, "frequency": "60m", "records": records,
                        "total_bars": len(df)},
                      ensure_ascii=False, default=str)


# ─── 工具 7: query_cluster ──────────────────────────

@SkillRegistry.register(
    name="query_cluster",
    description="查询指定聚类的成分股",
    expert_types=["data"],
    params=[{"name": "cluster_id", "type": "int", "description": "聚类ID"}],
    category="cluster",
)
async def query_cluster(cluster_id: int = 0, **ctx):
    from engine.cluster import get_cluster_engine
    ce = get_cluster_engine()
    result = ce.get_cluster_stocks(cluster_id)
    if result:
        return json.dumps(result, ensure_ascii=False, default=str)
    return json.dumps({"empty": True, "note": f"聚类 {cluster_id} 无数据"}, ensure_ascii=False)


# ─── 工具 8: find_similar_stocks ─────────────────────

@SkillRegistry.register(
    name="find_similar_stocks",
    description="跨簇相似股票搜索",
    expert_types=["data"],
    params=[
        {"name": "code", "type": "str", "description": "股票代码或名称"},
        {"name": "top_k", "type": "int", "description": "返回数量", "default": 10},
    ],
    category="cluster",
)
async def find_similar_stocks(code: str = "", top_k: int = 10, resolve_code=None, **ctx):
    if resolve_code:
        code = resolve_code(code)
    from engine.cluster import get_cluster_engine
    ce = get_cluster_engine()
    result = ce.find_similar(code, top_k)
    if result:
        return json.dumps(result, ensure_ascii=False, default=str)
    return json.dumps({"empty": True, "note": f"未找到 {code} 的相似股票"}, ensure_ascii=False)


# ─── 工具 9: run_screen ─────────────────────────────

@SkillRegistry.register(
    name="run_screen",
    description="条件选股筛选，支持 gt/lt 条件过滤",
    expert_types=["data", "quant"],
    params=[{"name": "filters", "type": "dict", "description": "筛选条件，格式: {列名: {gt: 值, lt: 值}}"}],
    category="screen",
)
async def run_screen(filters: dict = None, de=None, ensure_snapshot=None, **ctx):
    snap = await ensure_snapshot(de) if ensure_snapshot else de.get_snapshot()
    if snap is None or snap.empty:
        return json.dumps({"error": "无快照数据，请先在主页刷新行情"}, ensure_ascii=False)

    filters = filters or {}
    result = snap.copy()
    for col, cond in filters.items():
        if col in result.columns:
            if isinstance(cond, dict):
                if "gt" in cond:
                    result = result[pd.to_numeric(result[col], errors="coerce") > cond["gt"]]
                if "lt" in cond:
                    result = result[pd.to_numeric(result[col], errors="coerce") < cond["lt"]]

    # ── 增强：附带 updated_at 让 LLM 知道数据时效 ──
    updated_at = ""
    if "updated_at" in snap.columns:
        try:
            updated_at = str(pd.to_datetime(snap["updated_at"]).max())
        except Exception:
            pass

    records = result.head(30).to_dict("records")
    return json.dumps({
        "count": len(result),
        "results": records,
        "updated_at": updated_at,
    }, ensure_ascii=False, default=str)
