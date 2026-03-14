"""量化引擎 — 预测器单元测试"""

import numpy as np
import pandas as pd
import pytest


def _make_snapshot(n: int = 100) -> pd.DataFrame:
    """构造最小可行快照"""
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)],
        "name": [f"测试{i}" for i in range(n)],
        "pct_chg": rng.normal(0, 2, n),
        "turnover_rate": rng.uniform(0.5, 10, n),
        "amount": rng.uniform(1e6, 1e9, n),
        "pe_ttm": rng.uniform(5, 100, n),
        "pb": rng.uniform(0.5, 10, n),
        "total_mv": rng.uniform(1e8, 1e12, n),
        "wb_ratio": rng.uniform(-1, 1, n),
    })


class TestFactorDefs:
    """FACTOR_DEFS 常量完整性"""

    def test_import_from_quant_engine(self):
        from quant_engine.predictor import FACTOR_DEFS, FactorDef
        assert len(FACTOR_DEFS) == 13
        assert all(isinstance(f, FactorDef) for f in FACTOR_DEFS)

    def test_factor_names_unique(self):
        from quant_engine.predictor import FACTOR_DEFS
        names = [f.name for f in FACTOR_DEFS]
        assert len(names) == len(set(names))

    def test_factor_groups_not_empty(self):
        from quant_engine.predictor import FACTOR_DEFS
        for f in FACTOR_DEFS:
            assert f.group, f"因子 {f.name} 缺少 group"


class TestStockPredictorV2:
    """预测器核心逻辑"""

    def test_predict_basic(self):
        from quant_engine.predictor import StockPredictorV2, PredictionResult
        pred = StockPredictorV2()
        snap = _make_snapshot(200)
        result = pred.predict(snap)
        assert isinstance(result, PredictionResult)
        assert result.total_count == 200
        assert 0 < result.avg_probability < 1

    def test_predict_too_few_stocks(self):
        from quant_engine.predictor import StockPredictorV2
        pred = StockPredictorV2()
        snap = _make_snapshot(10)
        result = pred.predict(snap)
        assert result.total_count == 0  # 不足 50 只，返回空

    def test_icir_weight_injection(self):
        from quant_engine.predictor import StockPredictorV2
        pred = StockPredictorV2()
        weights = {"reversal": 0.2, "momentum_20d": 0.3}
        pred.set_icir_weights(weights)
        assert pred._weight_source == "icir_adaptive"

    def test_probability_range(self):
        from quant_engine.predictor import StockPredictorV2
        pred = StockPredictorV2()
        snap = _make_snapshot(200)
        result = pred.predict(snap)
        for prob in result.predictions.values():
            assert 0.12 <= prob <= 0.88, f"概率 {prob} 超出 [0.12, 0.88] 范围"
