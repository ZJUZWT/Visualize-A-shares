"""量化引擎模块 — 因子预测、IC 回测、技术指标"""

from .engine import QuantEngine

_quant_engine: QuantEngine | None = None


def get_quant_engine() -> QuantEngine:
    """获取量化引擎全局单例（依赖数据引擎）"""
    global _quant_engine
    if _quant_engine is None:
        from data_engine import get_data_engine
        _quant_engine = QuantEngine(get_data_engine())
    return _quant_engine


__all__ = ["QuantEngine", "get_quant_engine"]
