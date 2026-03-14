"""
QuantEngine — 量化引擎门面类

统一管理因子预测、IC 回测、技术指标计算。
对外提供单一接口，内部编排 predictor + backtester + indicators。
"""

import pandas as pd
import numpy as np
from loguru import logger

from .predictor import StockPredictorV2, PredictionResult, FACTOR_DEFS, FactorDef
from .factor_backtest import FactorBacktester, BacktestResult, run_ic_backtest_from_store
from .indicators import compute_all_indicators


class QuantEngine:
    """量化引擎 — 因子预测、回测、技术指标的门面"""

    def __init__(self, data_engine):
        """
        Args:
            data_engine: DataEngine 实例（通过依赖注入）
        """
        self._data = data_engine
        self._predictor = StockPredictorV2()
        self._backtester = FactorBacktester(rolling_window=20)

    @property
    def predictor(self) -> StockPredictorV2:
        return self._predictor

    @property
    def backtester(self) -> FactorBacktester:
        return self._backtester

    # ── 预测 ──

    def predict(
        self,
        snapshot_df: pd.DataFrame,
        cluster_labels: np.ndarray | None = None,
        daily_df_map: dict[str, pd.DataFrame] | None = None,
    ) -> PredictionResult:
        """计算全市场明日上涨概率"""
        return self._predictor.predict(snapshot_df, cluster_labels, daily_df_map)

    # ── 回测 ──

    def run_backtest(
        self,
        daily_snapshots: dict[str, pd.DataFrame] | None = None,
        rolling_window: int = 20,
    ) -> BacktestResult:
        """
        执行因子 IC 回测

        Args:
            daily_snapshots: 多日快照。为 None 时从 DataEngine 的 DuckDB 读取。
            rolling_window: ICIR 滚动窗口
        """
        if daily_snapshots is None:
            return run_ic_backtest_from_store(self._data.store, rolling_window)
        backtester = FactorBacktester(rolling_window=rolling_window)
        return backtester.run_backtest(daily_snapshots)

    def try_auto_inject_icir_weights(self):
        """启动时自动从历史数据计算 ICIR 权重并注入预测器"""
        try:
            dates = self._data.store.get_snapshot_daily_dates()
            if len(dates) >= 5:
                logger.info(f"🔄 检测到 {len(dates)} 天历史快照，自动运行 IC 回测...")
                result = run_ic_backtest_from_store(self._data.store, rolling_window=20)
                if result.icir_weights:
                    self._predictor.set_icir_weights(result.icir_weights)
                    logger.info("✅ 启动时 ICIR 权重自动注入成功")
                else:
                    logger.info("ℹ️ IC 回测无显著权重，使用默认权重")
            else:
                logger.info(
                    f"ℹ️ 历史快照仅 {len(dates)} 天（<5天），跳过 ICIR 自动校准。"
                )
        except Exception as e:
            logger.warning(f"⚠️ 启动时 ICIR 自动校准跳过: {e}")

    # ── 技术指标 ──

    def compute_indicators(self, daily_df: pd.DataFrame) -> dict:
        """计算单只股票的全部技术指标"""
        return compute_all_indicators(daily_df)

    # ── 因子信息 ──

    def get_factor_defs(self) -> list[FactorDef]:
        """获取全部因子定义"""
        return FACTOR_DEFS

    def get_factor_weights(self) -> tuple[dict[str, float], str]:
        """获取当前权重和来源"""
        return self._predictor._get_weights(), self._predictor._weight_source

    # ── 健康检查 ──

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "predictor": "v2.0",
            "factor_count": len(FACTOR_DEFS),
            "weight_source": self._predictor._weight_source,
        }
