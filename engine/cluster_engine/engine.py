"""
ClusterEngine — 聚类引擎门面类

依赖 DataEngine 获取原始数据，编排算法流水线。
"""

import numpy as np
import pandas as pd
from loguru import logger

from .algorithm.pipeline import AlgorithmPipeline, TerrainResult
from .algorithm.factor_backtest import run_ic_backtest_from_store


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
        """启动时自动从历史数据计算 ICIR 权重并注入预测器"""
        try:
            dates = self._data.get_snapshot_daily_dates()
            if len(dates) >= 5:
                logger.info(f"🔄 检测到 {len(dates)} 天历史快照，自动运行 IC 回测...")
                result = run_ic_backtest_from_store(self._data.store, rolling_window=20)
                if result.icir_weights:
                    self._pipeline.predictor_v2.set_icir_weights(result.icir_weights)
                    logger.info("✅ 启动时 ICIR 权重自动注入成功")
                else:
                    logger.info("ℹ️ IC 回测无显著权重，使用默认权重")
            else:
                logger.info(
                    f"ℹ️ 历史快照仅 {len(dates)} 天（<5天），跳过 ICIR 自动校准。"
                    f"多次「生成3D地形」积累数据后将自动启用。"
                )
        except Exception as e:
            logger.warning(f"⚠️ 启动时 ICIR 自动校准跳过: {e}")
