"""数据引擎模块 — 行情拉取、持久化、公司概况"""

from .engine import DataEngine

_data_engine: DataEngine | None = None


def get_data_engine() -> DataEngine:
    """获取数据引擎全局单例"""
    global _data_engine
    if _data_engine is None:
        _data_engine = DataEngine()
    return _data_engine


__all__ = ["DataEngine", "get_data_engine"]
