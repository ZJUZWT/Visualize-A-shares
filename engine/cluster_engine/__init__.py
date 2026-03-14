"""聚类引擎模块 — 特征提取、聚类、降维、插值、预测"""

from .engine import ClusterEngine as ClusterEngineFacade

# 同时导出 ClusterEngine 名称，方便外部使用
ClusterEngine = ClusterEngineFacade

_cluster_engine: ClusterEngineFacade | None = None


def get_cluster_engine() -> ClusterEngineFacade:
    """获取聚类引擎全局单例（依赖数据引擎）"""
    global _cluster_engine
    if _cluster_engine is None:
        from data_engine import get_data_engine
        _cluster_engine = ClusterEngineFacade(get_data_engine())
    return _cluster_engine


__all__ = ["ClusterEngine", "ClusterEngineFacade", "get_cluster_engine"]
