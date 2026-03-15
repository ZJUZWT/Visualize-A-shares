"""
ClusterEngine — 聚类引擎门面类

依赖 DataEngine 获取原始数据，编排算法流水线。
"""

import numpy as np
import pandas as pd
from loguru import logger

from .algorithm.pipeline import AlgorithmPipeline, TerrainResult


class ClusterEngine:
    """聚类引擎 — 算法消费者，从 DataEngine 获取数据"""

    def __init__(self, data_engine):
        """
        Args:
            data_engine: DataEngine 实例（通过依赖注入）
        """
        self._data = data_engine
        self._pipeline = AlgorithmPipeline(profiles=data_engine.get_profiles())

    @property
    def pipeline(self) -> AlgorithmPipeline:
        """暴露 pipeline 给路由层"""
        return self._pipeline

    @property
    def last_result(self) -> TerrainResult | None:
        return self._pipeline.last_result

    def search_stocks(self, query: str, limit: int = 20) -> list[dict]:
        """搜索股票（代码/名称模糊匹配）"""
        if not self._pipeline.last_result or not self._pipeline.last_result.stocks:
            return []

        q_lower = query.lower()
        results = []
        for s in self._pipeline.last_result.stocks:
            if q_lower in s["code"].lower() or q_lower in s["name"].lower():
                results.append(s)
            if len(results) >= limit:
                break
        return results

    def try_auto_inject_icir_weights(self):
        """启动时自动从历史数据计算 ICIR 权重并注入预测器（委托 QuantEngine）"""
        try:
            from quant_engine import get_quant_engine
            qe = get_quant_engine()
            qe.try_auto_inject_icir_weights()
            # 同步 ICIR 权重到 pipeline 中的预测器实例
            if qe.predictor._icir_weights is not None:
                self._pipeline.predictor_v2.set_icir_weights(
                    qe.predictor._icir_weights
                )
        except Exception as e:
            logger.warning(f"⚠️ 启动时 ICIR 自动校准跳过: {e}")

    def get_cluster_for_stock(self, code: str) -> dict | None:
        """获取某只股票的聚类信息及关联/相似股票（供辩论系统使用）"""
        if not self._pipeline.last_result:
            return None
        for s in self._pipeline.last_result.stocks:
            if s["code"] == code:
                return {
                    "code": s["code"],
                    "name": s["name"],
                    "cluster_id": s.get("cluster_id"),
                    "industry": s.get("industry", ""),
                    "related_stocks": s.get("related_stocks", []),
                    "similar_stocks": s.get("similar_stocks", []),
                    "cluster_affinities": s.get("cluster_affinities", []),
                }
        return None
