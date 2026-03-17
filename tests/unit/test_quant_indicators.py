"""量化引擎 — 技术指标计算单元测试"""

import numpy as np
import pandas as pd
import pytest


def _make_daily(n: int = 60) -> pd.DataFrame:
    """构造日线数据"""
    rng = np.random.default_rng(42)
    base_price = 10.0
    closes = base_price + np.cumsum(rng.normal(0, 0.3, n))
    closes = np.abs(closes) + 1  # 确保正数
    return pd.DataFrame({
        "close": closes,
        "high": closes * rng.uniform(1.0, 1.03, n),
        "low": closes * rng.uniform(0.97, 1.0, n),
        "volume": rng.uniform(1e6, 1e8, n),
        "pct_chg": np.concatenate([[0], np.diff(closes) / closes[:-1] * 100]),
    })


class TestRSI:
    def test_basic(self):
        from engine.quant.indicators import compute_rsi
        daily = _make_daily(30)
        rsi = compute_rsi(daily["close"].values, period=14)
        assert 0 <= rsi <= 100

    def test_insufficient_data(self):
        from engine.quant.indicators import compute_rsi
        rsi = compute_rsi(np.array([10.0, 11.0, 10.5]), period=14)
        assert rsi == 50.0


class TestMACD:
    def test_basic(self):
        from engine.quant.indicators import compute_macd
        daily = _make_daily(60)
        macd, signal, hist = compute_macd(daily["close"].values)
        assert len(macd) == len(daily)
        assert len(signal) == len(daily)
        assert len(hist) == len(daily)

    def test_latest_values_finite(self):
        from engine.quant.indicators import compute_macd
        daily = _make_daily(60)
        macd, signal, hist = compute_macd(daily["close"].values)
        assert np.isfinite(macd[-1])
        assert np.isfinite(signal[-1])


class TestBollingerBands:
    def test_basic(self):
        from engine.quant.indicators import compute_bollinger_bands
        daily = _make_daily(30)
        upper, mid, lower = compute_bollinger_bands(daily["close"].values, period=20)
        assert upper[-1] >= mid[-1] >= lower[-1]

    def test_bandwidth_positive(self):
        from engine.quant.indicators import compute_bollinger_bands
        daily = _make_daily(30)
        upper, mid, lower = compute_bollinger_bands(daily["close"].values, period=20)
        assert upper[-1] - lower[-1] > 0


class TestKDJ:
    def test_basic(self):
        from engine.quant.indicators import compute_kdj
        daily = _make_daily(30)
        k, d, j = compute_kdj(
            daily["high"].values,
            daily["low"].values,
            daily["close"].values,
        )
        assert len(k) == len(daily)
        assert 0 <= k[-1] <= 100
        assert 0 <= d[-1] <= 100


class TestComputeAllIndicators:
    def test_returns_dict(self):
        from engine.quant.indicators import compute_all_indicators
        daily = _make_daily(60)
        result = compute_all_indicators(daily)
        assert isinstance(result, dict)
        assert "rsi_14" in result
        assert "macd" in result
        assert "macd_signal" in result
        assert "macd_hist" in result
        assert "bb_upper" in result
        assert "bb_lower" in result
        assert "kdj_k" in result
        assert "kdj_d" in result
        assert "kdj_j" in result
        assert "volatility_20d" in result
        assert "momentum_20d" in result
        assert "ma_deviation_20" in result

    def test_insufficient_data_returns_partial(self):
        from engine.quant.indicators import compute_all_indicators
        daily = _make_daily(10)
        result = compute_all_indicators(daily)
        assert isinstance(result, dict)
