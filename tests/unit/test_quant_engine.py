"""量化引擎 — 门面类集成测试"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock


def _make_snapshot(n: int = 200) -> pd.DataFrame:
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


class TestQuantEngine:

    def _make_engine(self):
        from engine.quant.engine import QuantEngine
        mock_data = MagicMock()
        mock_data.store = MagicMock()
        mock_data.store.get_snapshot_daily_dates.return_value = []
        return QuantEngine(mock_data)

    def test_init(self):
        qe = self._make_engine()
        assert qe.predictor is not None
        assert qe.backtester is not None

    def test_predict(self):
        qe = self._make_engine()
        snap = _make_snapshot()
        result = qe.predict(snap)
        assert result.total_count == 200

    def test_get_factor_defs(self):
        qe = self._make_engine()
        defs = qe.get_factor_defs()
        assert len(defs) == 13

    def test_compute_indicators(self):
        qe = self._make_engine()
        daily = pd.DataFrame({
            "close": np.random.default_rng(42).normal(10, 1, 60).cumsum() + 50,
            "high": np.random.default_rng(43).normal(10.5, 1, 60).cumsum() + 51,
            "low": np.random.default_rng(44).normal(9.5, 1, 60).cumsum() + 49,
            "pct_chg": np.random.default_rng(42).normal(0, 2, 60),
        })
        result = qe.compute_indicators(daily)
        assert "rsi_14" in result
        assert "macd" in result
