"""
量化引擎 — 技术指标计算器

提供独立的技术指标计算函数，不依赖聚类引擎。
每个函数接受 numpy 数组，返回计算结果。

指标列表:
  - RSI (Relative Strength Index)
  - MACD (Moving Average Convergence Divergence)
  - 布林带 (Bollinger Bands)
  - KDJ (随机指标)
  - 波动率、动量、均线偏离（复用 features.py 计算逻辑）
"""

import numpy as np
import pandas as pd
from loguru import logger


def compute_rsi(close: np.ndarray, period: int = 14) -> float:
    """
    计算 RSI 指标（最新值）

    Args:
        close: 收盘价序列
        period: RSI 周期（默认 14）

    Returns:
        RSI 值 (0~100)，数据不足返回 50.0
    """
    if len(close) < period + 1:
        return 50.0

    changes = np.diff(close[-period - 1:])
    gains = np.where(changes > 0, changes, 0)
    losses = np.where(changes < 0, -changes, 0)

    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def compute_macd(
    close: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    计算 MACD 指标

    Returns:
        (macd_line, signal_line, histogram) 三个等长数组
    """
    n = len(close)

    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        alpha = 2.0 / (period + 1)
        result = np.zeros(n)
        result[0] = data[0]
        for i in range(1, n):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal_period)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def compute_bollinger_bands(
    close: np.ndarray,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    计算布林带

    Returns:
        (upper_band, middle_band, lower_band) 三个等长数组
    """
    n = len(close)
    mid = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)

    for i in range(period - 1, n):
        window = close[i - period + 1: i + 1]
        ma = np.mean(window)
        std = np.std(window, ddof=1) if len(window) > 1 else 0.0
        mid[i] = ma
        upper[i] = ma + num_std * std
        lower[i] = ma - num_std * std

    return upper, mid, lower


def compute_kdj(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 9,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    计算 KDJ 随机指标

    Returns:
        (K, D, J) 三个等长数组
    """
    n = len(close)
    rsv = np.full(n, 50.0)

    for i in range(period - 1, n):
        hh = np.max(high[i - period + 1: i + 1])
        ll = np.min(low[i - period + 1: i + 1])
        if hh - ll > 1e-10:
            rsv[i] = (close[i] - ll) / (hh - ll) * 100
        else:
            rsv[i] = 50.0

    k = np.full(n, 50.0)
    for i in range(1, n):
        k[i] = (k[i - 1] * (k_smooth - 1) + rsv[i]) / k_smooth

    d = np.full(n, 50.0)
    for i in range(1, n):
        d[i] = (d[i - 1] * (d_smooth - 1) + k[i]) / d_smooth

    j = 3 * k - 2 * d

    k = np.clip(k, 0, 100)
    d = np.clip(d, 0, 100)

    return k, d, j


def compute_all_indicators(daily_df: pd.DataFrame) -> dict:
    """
    计算单只股票的所有技术指标

    Args:
        daily_df: 单只股票日线 DataFrame，需含 close, high, low, pct_chg 列

    Returns:
        { indicator_name: value } 字典，值为最新一天的标量
    """
    if daily_df.empty or len(daily_df) < 5:
        return {}

    result = {}
    close = daily_df["close"].values.astype(float)
    pct = daily_df["pct_chg"].values.astype(float) if "pct_chg" in daily_df.columns else np.diff(close) / close[:-1] * 100

    # ── 原有指标（复用 features.py 逻辑）──────
    if len(pct) >= 20:
        result["volatility_20d"] = float(np.nanstd(pct[-20:]) * np.sqrt(252))
    if len(pct) >= 60:
        result["volatility_60d"] = float(np.nanstd(pct[-60:]) * np.sqrt(252))
    if len(close) >= 21:
        result["momentum_20d"] = float((close[-1] / close[-21] - 1) * 100)
    if len(close) >= 20:
        ma20 = np.mean(close[-20:])
        result["ma_deviation_20"] = float((close[-1] / ma20 - 1) * 100)
    if len(close) >= 60:
        ma60 = np.mean(close[-60:])
        result["ma_deviation_60"] = float((close[-1] / ma60 - 1) * 100)

    # ── RSI ──────
    if len(close) >= 15:
        result["rsi_14"] = compute_rsi(close, 14)

    # ── MACD ──────
    if len(close) >= 35:
        macd, signal, hist = compute_macd(close)
        result["macd"] = float(macd[-1])
        result["macd_signal"] = float(signal[-1])
        result["macd_hist"] = float(hist[-1])

    # ── 布林带 ──────
    if len(close) >= 20:
        upper, mid, lower = compute_bollinger_bands(close, period=20)
        result["bb_upper"] = float(upper[-1])
        result["bb_mid"] = float(mid[-1])
        result["bb_lower"] = float(lower[-1])
        if mid[-1] > 0:
            result["bb_width_pct"] = float((upper[-1] - lower[-1]) / mid[-1] * 100)

    # ── KDJ ──────
    if "high" in daily_df.columns and "low" in daily_df.columns and len(close) >= 9:
        high = daily_df["high"].values.astype(float)
        low = daily_df["low"].values.astype(float)
        k, d, j = compute_kdj(high, low, close)
        result["kdj_k"] = float(k[-1])
        result["kdj_d"] = float(d[-1])
        result["kdj_j"] = float(j[-1])

    return result
