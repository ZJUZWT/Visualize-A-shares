"""
量化引擎 REST API

独立路由前缀: /api/v1/quant/*
"""

import asyncio
import datetime

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from loguru import logger

from quant_engine import get_quant_engine
from data_engine import get_data_engine

router = APIRouter(prefix="/api/v1/quant", tags=["quant"])


@router.get("/health")
async def quant_health():
    """量化引擎健康检查"""
    qe = get_quant_engine()
    return qe.health_check()


@router.get("/factor/weights")
async def get_factor_weights():
    """查看当前因子权重"""
    qe = get_quant_engine()
    weights, source = qe.get_factor_weights()
    factor_defs = qe.get_factor_defs()

    factors = []
    for fdef in factor_defs:
        factors.append({
            "name": fdef.name,
            "source_col": fdef.source_col,
            "direction": fdef.direction,
            "group": fdef.group,
            "weight": weights.get(fdef.name, 0.0),
            "default_weight": fdef.default_weight,
            "desc": fdef.desc,
        })

    return {
        "weight_source": source,
        "factors": factors,
    }


@router.get("/factor/defs")
async def get_factor_defs():
    """获取全部因子定义"""
    qe = get_quant_engine()
    return [
        {
            "name": f.name,
            "source_col": f.source_col,
            "direction": f.direction,
            "group": f.group,
            "default_weight": f.default_weight,
            "desc": f.desc,
        }
        for f in qe.get_factor_defs()
    ]


@router.post("/factor/backtest")
async def run_backtest(
    rolling_window: int = Query(default=20, ge=3, le=60),
    auto_inject: bool = Query(default=True),
):
    """执行因子 IC 回测"""
    qe = get_quant_engine()

    result = await asyncio.to_thread(qe.run_backtest, rolling_window=rolling_window)

    if auto_inject and result.icir_weights:
        qe.predictor.set_icir_weights(result.icir_weights)
        # 同步到 ClusterEngine 的 pipeline
        try:
            from cluster_engine import get_cluster_engine
            get_cluster_engine().pipeline.predictor_v2.set_icir_weights(result.icir_weights)
        except Exception:
            pass

    return {
        "backtest_days": result.backtest_days,
        "total_stocks_avg": result.total_stocks_avg,
        "computation_time_ms": round(result.computation_time_ms, 0),
        "icir_weights": result.icir_weights,
        "weights_injected": auto_inject and bool(result.icir_weights),
        "factor_reports": {
            name: {
                "ic_mean": r.ic_mean,
                "ic_std": r.ic_std,
                "icir": r.icir,
                "ic_positive_rate": r.ic_positive_rate,
                "t_stat": r.t_stat,
                "p_value": r.p_value,
            }
            for name, r in result.factor_reports.items()
        },
    }


@router.get("/indicators/{code}")
async def get_indicators(
    code: str = PathParam(..., pattern=r"^\d{6}$"),
    days: int = Query(default=120, ge=20, le=365),
):
    """获取单只股票的全部技术指标"""
    qe = get_quant_engine()
    de = get_data_engine()

    end = datetime.date.today().strftime("%Y-%m-%d")
    start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    daily = await asyncio.to_thread(de.get_daily_history, code, start, end)

    if daily is None or daily.empty:
        raise HTTPException(status_code=404, detail=f"股票 {code} 无日线数据")

    indicators = qe.compute_indicators(daily)
    return {
        "code": code,
        "data_days": len(daily),
        "indicators": indicators,
    }
