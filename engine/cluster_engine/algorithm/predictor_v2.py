"""
兼容 shim — 预测模块已迁移至 quant_engine.predictor

保留此文件用于向后兼容，所有新代码请直接导入:
    from quant_engine.predictor import StockPredictorV2, FACTOR_DEFS
"""

import warnings

warnings.warn(
    "cluster_engine.algorithm.predictor_v2 已迁移至 quant_engine.predictor，"
    "请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from quant_engine.predictor import (  # noqa: F401
    FactorDef,
    FACTOR_DEFS,
    PredictionResult,
    StockPredictorV2,
)
