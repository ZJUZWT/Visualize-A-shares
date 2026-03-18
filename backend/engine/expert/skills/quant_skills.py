"""量化专家 Skills — 技术指标、因子评分、IC 回测

注意：run_screen 和 query_hourly 已在 data_skills.py 中注册为
expert_types=["data", "quant"] 的共享 Skill，这里不重复定义。
"""

import asyncio
import datetime
import json

import pandas as pd
from loguru import logger

from engine.expert.skill_registry import SkillRegistry


# ─── 工具 1: get_technical_indicators ────────────────

@SkillRegistry.register(
    name="get_technical_indicators",
    description="获取技术指标（RSI/MACD/布林带等），附带实时价格",
    expert_types=["quant"],
    params=[{"name": "code", "type": "str", "description": "股票代码或名称"}],
    category="technical",
)
async def get_technical_indicators(code: str = "", de=None, resolve_code=None, **ctx):
    from engine.quant import get_quant_engine
    qe = get_quant_engine()

    if resolve_code:
        code = resolve_code(code)

    days = 120
    today = datetime.date.today()
    end = today.strftime("%Y-%m-%d")
    start = (today - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    daily = await asyncio.to_thread(de.get_daily_history, code, start, end)
    if daily is None or daily.empty:
        return json.dumps({"error": f"无 {code} 日线数据，无法计算技术指标"}, ensure_ascii=False)

    # ── 用实时快照补充当天数据 ──
    realtime_price = None
    realtime_pct = None
    try:
        snap = de.get_snapshot()
        if snap is not None and not snap.empty:
            row = snap[snap["code"].astype(str) == code]
            if not row.empty:
                r = row.iloc[0]
                realtime_price = float(r.get("price", 0))
                realtime_pct = float(r.get("pct_chg", 0))
                today_str = today.strftime("%Y-%m-%d")
                date_col = "date" if "date" in daily.columns else (
                    "trade_date" if "trade_date" in daily.columns else None
                )
                last_date = ""
                if date_col:
                    last_date = str(daily[date_col].iloc[-1])[:10]

                if realtime_price > 0 and last_date != today_str:
                    new_row = {
                        "close": realtime_price,
                        "volume": float(r.get("volume", 0)),
                        "amount": float(r.get("amount", 0)),
                        "turnover_rate": float(r.get("turnover_rate", 0)),
                        "open": float(r.get("open", realtime_price)),
                        "high": float(r.get("high", realtime_price)),
                        "low": float(r.get("low", realtime_price)),
                    }
                    if date_col:
                        new_row[date_col] = today_str
                    if "code" in daily.columns:
                        new_row["code"] = code
                    daily = pd.concat([daily, pd.DataFrame([new_row])], ignore_index=True)
    except Exception:
        pass

    indicators = qe.compute_indicators(daily)
    result = {"code": code, "data_days": len(daily), "indicators": indicators}
    if realtime_price and realtime_price > 0:
        result["realtime_price"] = realtime_price
        result["realtime_pct_chg"] = realtime_pct
    return json.dumps(result, ensure_ascii=False, default=str)


# ─── 工具 2: get_factor_scores ───────────────────────

@SkillRegistry.register(
    name="get_factor_scores",
    description="获取多因子评分（含权重和方向）",
    expert_types=["quant"],
    params=[{"name": "code", "type": "str", "description": "股票代码或名称"}],
    category="factor",
)
async def get_factor_scores(code: str = "", de=None, ensure_snapshot=None, resolve_code=None, **ctx):
    from engine.quant import get_quant_engine
    qe = get_quant_engine()

    if resolve_code:
        code = resolve_code(code)

    snap = await ensure_snapshot(de) if ensure_snapshot else de.get_snapshot()
    if snap is None or snap.empty:
        return json.dumps({"error": "无快照数据，请先在主页刷新行情"}, ensure_ascii=False)

    row = snap[snap["code"].astype(str) == code]
    if row.empty:
        return json.dumps({"error": f"快照中未找到 {code}"}, ensure_ascii=False)

    weights, source = qe.get_factor_weights()
    factor_defs = qe.get_factor_defs()
    factors = {}
    for fdef in factor_defs:
        val = row.iloc[0].get(fdef.source_col)
        factors[fdef.name] = {
            "value": float(val) if val is not None and str(val) != "nan" else None,
            "weight": weights.get(fdef.name, 0),
            "direction": fdef.direction,
            "desc": fdef.desc,
        }
    return json.dumps({"code": code, "factors": factors, "weight_source": source},
                      ensure_ascii=False, default=str)


# ─── 工具 3: query_factor_analysis ───────────────────

@SkillRegistry.register(
    name="query_factor_analysis",
    description="查看因子体系，不传名称返回全景",
    expert_types=["quant"],
    params=[{"name": "factor_name", "type": "str", "description": "因子名称（可选，不传返回全景）",
             "required": False}],
    category="factor",
)
async def query_factor_analysis(factor_name: str = None, **ctx):
    from engine.quant import get_quant_engine
    qe = get_quant_engine()

    factor_defs = qe.get_factor_defs()
    weights, source = qe.get_factor_weights()

    if factor_name:
        matched = [f for f in factor_defs if f.name == factor_name]
        if not matched:
            return json.dumps({"error": f"未找到因子: {factor_name}"}, ensure_ascii=False)
        f = matched[0]
        return json.dumps({
            "name": f.name, "source_col": f.source_col, "direction": f.direction,
            "group": f.group, "weight": weights.get(f.name, 0), "desc": f.desc,
        }, ensure_ascii=False)

    # 全景
    all_factors = [{
        "name": f.name, "group": f.group, "direction": f.direction,
        "weight": weights.get(f.name, 0), "desc": f.desc,
    } for f in factor_defs]
    return json.dumps({"weight_source": source, "factors": all_factors}, ensure_ascii=False)


# ─── 工具 4: run_backtest ───────────────────────────

@SkillRegistry.register(
    name="run_backtest",
    description="因子 IC 回测",
    expert_types=["quant"],
    params=[
        {"name": "rolling_window", "type": "int", "description": "滚动窗口天数", "default": 20},
    ],
    category="backtest",
)
async def run_backtest(rolling_window: int = 20, **ctx):
    from engine.quant import get_quant_engine
    qe = get_quant_engine()

    result = await asyncio.to_thread(qe.run_backtest, rolling_window=rolling_window)
    return json.dumps({
        "backtest_days": result.backtest_days,
        "icir_weights": result.icir_weights,
    }, ensure_ascii=False, default=str)
