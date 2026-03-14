"""量化引擎 — 因子回测单元测试"""

import numpy as np
import pandas as pd
import pytest


def _make_daily_snapshots(n_days: int = 5, n_stocks: int = 100) -> dict[str, pd.DataFrame]:
    """构造多日快照"""
    rng = np.random.default_rng(42)
    snapshots = {}
    codes = [f"{i:06d}" for i in range(n_stocks)]
    for day in range(n_days):
        date_str = f"2025-03-{10 + day:02d}"
        snapshots[date_str] = pd.DataFrame({
            "code": codes,
            "name": [f"测试{i}" for i in range(n_stocks)],
            "pct_chg": rng.normal(0, 2, n_stocks),
            "turnover_rate": rng.uniform(0.5, 10, n_stocks),
            "amount": rng.uniform(1e6, 1e9, n_stocks),
            "pe_ttm": rng.uniform(5, 100, n_stocks),
            "pb": rng.uniform(0.5, 10, n_stocks),
            "total_mv": rng.uniform(1e8, 1e12, n_stocks),
        })
    return snapshots


class TestFactorBacktester:
    """FactorBacktester 核心逻辑"""

    def test_import_from_quant_engine(self):
        from quant_engine.factor_backtest import FactorBacktester, BacktestResult
        bt = FactorBacktester(rolling_window=20)
        assert bt.rolling_window == 20

    def test_run_backtest_basic(self):
        from quant_engine.factor_backtest import FactorBacktester
        bt = FactorBacktester(rolling_window=3)
        snapshots = _make_daily_snapshots(5, 200)
        result = bt.run_backtest(snapshots)
        assert result.backtest_days == 5
        assert result.total_stocks_avg > 0

    def test_run_backtest_too_few_days(self):
        from quant_engine.factor_backtest import FactorBacktester
        bt = FactorBacktester()
        snapshots = _make_daily_snapshots(2, 200)
        result = bt.run_backtest(snapshots)
        assert result.backtest_days == 2
        assert len(result.factor_reports) == 0

    def test_icir_weights_normalized(self):
        from quant_engine.factor_backtest import FactorBacktester
        bt = FactorBacktester(rolling_window=3)
        snapshots = _make_daily_snapshots(10, 200)
        result = bt.run_backtest(snapshots)
        if result.icir_weights:
            total_abs = sum(abs(v) for v in result.icir_weights.values())
            assert abs(total_abs - 1.0) < 0.01, f"权重绝对值之和应为1，实际={total_abs}"


class TestRunICBacktestFromStore:
    """便捷函数测试"""

    def test_import(self):
        from quant_engine.factor_backtest import run_ic_backtest_from_store
        assert callable(run_ic_backtest_from_store)
