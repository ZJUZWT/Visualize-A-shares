"""
兼容 shim — 因子回测已迁移至 quant_engine.factor_backtest

保留此文件用于向后兼容，所有新代码请直接导入:
    from quant_engine.factor_backtest import FactorBacktester
"""

import warnings

warnings.warn(
    "cluster_engine.algorithm.factor_backtest 已迁移至 quant_engine.factor_backtest，"
    "请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from quant_engine.factor_backtest import (  # noqa: F401
    FactorICReport,
    BacktestResult,
    FactorBacktester,
    run_ic_backtest_from_store,
)
