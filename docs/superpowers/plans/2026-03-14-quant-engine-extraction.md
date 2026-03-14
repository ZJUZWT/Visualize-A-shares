# QuantEngine 提取 — 路线图 Phase 2 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `predictor_v2.py` 和 `factor_backtest.py` 从 `cluster_engine/algorithm/` 提取为独立的 `quant_engine/` 模块，同时新增技术指标计算器 `indicators.py`、独立 REST API 和 MCP tools，使量化引擎成为与聚类引擎平级的业务引擎。

**Architecture:** QuantEngine 作为独立模块，依赖 DataEngine 获取数据（同 ClusterEngine 的依赖注入模式）。ClusterEngine 通过 `quant_engine` 公共接口调用预测和回测功能，不再直接持有预测器实例。

**Tech Stack:** Python 3.11+ / FastAPI / DuckDB / pandas / numpy / scipy / pytest

**Spec:** `docs/superpowers/specs/2026-03-14-multi-engine-roadmap.md` (Phase 2)

---

## File Structure

### New files

```
engine/
├── quant_engine/                         # 量化引擎（新建目录）
│   ├── __init__.py                       # 导出 get_quant_engine() 单例
│   ├── engine.py                         # QuantEngine 门面类
│   ├── predictor.py                      # 从 cluster_engine/algorithm/predictor_v2.py 迁移
│   ├── factor_backtest.py                # 从 cluster_engine/algorithm/factor_backtest.py 迁移
│   ├── indicators.py                     # 新增：技术指标计算器 (MACD/布林带/KDJ 等)
│   └── routes.py                         # 独立 REST API: /api/v1/quant/*
```

### New test files

```
engine/tests/
├── conftest.py                           # pytest fixtures
├── test_quant_predictor.py               # 预测器单测
├── test_quant_backtest.py                # 回测单测
├── test_quant_indicators.py              # 技术指标计算单测
├── test_quant_engine.py                  # QuantEngine 门面集成测试
└── test_quant_routes.py                  # REST API 测试
```

### Modified files

```
engine/cluster_engine/algorithm/pipeline.py       # 改为 from quant_engine.predictor import StockPredictorV2
engine/cluster_engine/engine.py                   # 改为 from quant_engine import get_quant_engine
engine/cluster_engine/routes.py                   # 改为 from quant_engine 导入
engine/cluster_engine/algorithm/predictor_v2.py   # 保留为兼容 shim（re-export）
engine/cluster_engine/algorithm/factor_backtest.py# 保留为兼容 shim（re-export）
engine/mcpserver/tools.py                         # 改为 from quant_engine 导入
engine/main.py                                    # 注册 quant_router + 自动 ICIR 校准改走 QuantEngine
engine/config.py                                  # 新增 QuantConfig
```

### Import Dependency Map (当前 → 目标)

| Consumer | Current Import | Target Import |
|----------|---------------|---------------|
| `pipeline.py:28` | `from .predictor_v2 import StockPredictorV2` | `from quant_engine.predictor import StockPredictorV2` |
| `pipeline.py:80` | `self.predictor_v2 = StockPredictorV2()` | 不变（类名相同） |
| `cluster_engine/engine.py:12` | `from .algorithm.factor_backtest import run_ic_backtest_from_store` | `from quant_engine.factor_backtest import run_ic_backtest_from_store` |
| `cluster_engine/routes.py:20` | `from cluster_engine.algorithm.factor_backtest import run_ic_backtest_from_store` | `from quant_engine.factor_backtest import run_ic_backtest_from_store` |
| `cluster_engine/routes.py:580` | `from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS` | `from quant_engine.predictor import FACTOR_DEFS` |
| `mcpserver/tools.py:536` | `from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS` | `from quant_engine.predictor import FACTOR_DEFS` |
| `mcpserver/tools.py:852` | `from cluster_engine.algorithm.factor_backtest import FactorBacktester` | `from quant_engine.factor_backtest import FactorBacktester` |

---

## Chunk 1: 核心模块迁移 (Tasks 1-4)

### Task 1: 创建 quant_engine 目录结构 + predictor 迁移

**Files:**
- Create: `engine/quant_engine/__init__.py`
- Create: `engine/quant_engine/predictor.py` (从 `cluster_engine/algorithm/predictor_v2.py` 复制)
- Create: `engine/tests/__init__.py`
- Create: `engine/tests/conftest.py`
- Create: `engine/tests/test_quant_predictor.py`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p engine/quant_engine
touch engine/quant_engine/__init__.py
mkdir -p engine/tests
touch engine/tests/__init__.py
```

- [ ] **Step 2: 编写 predictor 迁移测试**

`engine/tests/test_quant_predictor.py`:

```python
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
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_predictor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quant_engine.predictor'`

- [ ] **Step 4: 复制 predictor_v2.py 到 quant_engine/predictor.py**

将 `engine/cluster_engine/algorithm/predictor_v2.py` 完整复制到 `engine/quant_engine/predictor.py`。

唯一需要修改的导入：

```python
# 旧 (predictor_v2.py line 152):
from .features import FeatureEngineer

# 新 (predictor.py):
from cluster_engine.algorithm.features import FeatureEngineer
```

- [ ] **Step 5: 编写 `__init__.py`**

`engine/quant_engine/__init__.py`:

```python
"""量化引擎模块 — 因子预测、IC 回测、技术指标"""

from .engine import QuantEngine

_quant_engine: QuantEngine | None = None


def get_quant_engine() -> QuantEngine:
    """获取量化引擎全局单例（依赖数据引擎）"""
    global _quant_engine
    if _quant_engine is None:
        from data_engine import get_data_engine
        _quant_engine = QuantEngine(get_data_engine())
    return _quant_engine


__all__ = ["QuantEngine", "get_quant_engine"]
```

注意：此时 `engine.py` 还未创建，先占位。创建一个最小 engine.py 让导入不失败：

`engine/quant_engine/engine.py` (临时最小版本):

```python
"""QuantEngine — 量化引擎门面类（Task 4 完善）"""


class QuantEngine:
    def __init__(self, data_engine=None):
        self._data = data_engine
```

- [ ] **Step 6: 编写 conftest.py**

`engine/tests/conftest.py`:

```python
"""量化引擎测试 fixtures"""

import sys
from pathlib import Path

# 确保 engine/ 在 sys.path 中
engine_dir = Path(__file__).resolve().parent.parent
if str(engine_dir) not in sys.path:
    sys.path.insert(0, str(engine_dir))
```

- [ ] **Step 7: 运行测试验证通过**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_predictor.py -v`
Expected: 7 passed

- [ ] **Step 8: Commit**

```bash
git add engine/quant_engine/__init__.py engine/quant_engine/predictor.py engine/quant_engine/engine.py engine/tests/__init__.py engine/tests/conftest.py engine/tests/test_quant_predictor.py
git commit -m "feat(quant-engine): 迁移 predictor_v2 到 quant_engine/predictor"
```

---

### Task 2: factor_backtest 迁移

**Files:**
- Create: `engine/quant_engine/factor_backtest.py` (从 `cluster_engine/algorithm/factor_backtest.py` 复制)
- Create: `engine/tests/test_quant_backtest.py`

- [ ] **Step 1: 编写回测测试**

`engine/tests/test_quant_backtest.py`:

```python
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
        assert len(result.factor_reports) == 0  # 不足 3 天

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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_backtest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quant_engine.factor_backtest'`

- [ ] **Step 3: 复制 factor_backtest.py 到 quant_engine/**

将 `engine/cluster_engine/algorithm/factor_backtest.py` 完整复制到 `engine/quant_engine/factor_backtest.py`。

修改导入：

```python
# 旧 (line 30):
from .predictor_v2 import FACTOR_DEFS, StockPredictorV2

# 新:
from .predictor import FACTOR_DEFS, StockPredictorV2
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_backtest.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/quant_engine/factor_backtest.py engine/tests/test_quant_backtest.py
git commit -m "feat(quant-engine): 迁移 factor_backtest 到 quant_engine"
```

---

### Task 3: 新增 indicators.py 技术指标计算器

**Files:**
- Create: `engine/quant_engine/indicators.py`
- Create: `engine/tests/test_quant_indicators.py`

**设计说明:** `features.py` 中的 `FeatureEngineer.compute_technical_features()` 和 `_compute_rsi()` 计算 6 个技术指标。这些属于量化引擎的职责。本 Task 在 `indicators.py` 中扩展实现更多指标（MACD、布林带、KDJ），同时保留 `features.py` 中原有的计算函数不动（避免破坏聚类引擎）。Multi-Agent MVP 计划中的 Agent 将调用 `indicators.py` 获取技术分析数据。

- [ ] **Step 1: 编写技术指标测试**

`engine/tests/test_quant_indicators.py`:

```python
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
        from quant_engine.indicators import compute_rsi
        daily = _make_daily(30)
        rsi = compute_rsi(daily["close"].values, period=14)
        assert 0 <= rsi <= 100

    def test_insufficient_data(self):
        from quant_engine.indicators import compute_rsi
        rsi = compute_rsi(np.array([10.0, 11.0, 10.5]), period=14)
        assert rsi == 50.0  # 数据不足返回中性值


class TestMACD:
    def test_basic(self):
        from quant_engine.indicators import compute_macd
        daily = _make_daily(60)
        macd, signal, hist = compute_macd(daily["close"].values)
        assert len(macd) == len(daily)
        assert len(signal) == len(daily)
        assert len(hist) == len(daily)

    def test_latest_values_finite(self):
        from quant_engine.indicators import compute_macd
        daily = _make_daily(60)
        macd, signal, hist = compute_macd(daily["close"].values)
        assert np.isfinite(macd[-1])
        assert np.isfinite(signal[-1])


class TestBollingerBands:
    def test_basic(self):
        from quant_engine.indicators import compute_bollinger_bands
        daily = _make_daily(30)
        upper, mid, lower = compute_bollinger_bands(daily["close"].values, period=20)
        # 上轨 > 中轨 > 下轨
        assert upper[-1] >= mid[-1] >= lower[-1]

    def test_bandwidth_positive(self):
        from quant_engine.indicators import compute_bollinger_bands
        daily = _make_daily(30)
        upper, mid, lower = compute_bollinger_bands(daily["close"].values, period=20)
        assert upper[-1] - lower[-1] > 0


class TestKDJ:
    def test_basic(self):
        from quant_engine.indicators import compute_kdj
        daily = _make_daily(30)
        k, d, j = compute_kdj(
            daily["high"].values,
            daily["low"].values,
            daily["close"].values,
        )
        assert len(k) == len(daily)
        # K 和 D 值在 0~100 范围（J 可超出）
        assert 0 <= k[-1] <= 100
        assert 0 <= d[-1] <= 100


class TestComputeAllIndicators:
    def test_returns_dict(self):
        from quant_engine.indicators import compute_all_indicators
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
        # 也包含原有 features.py 中的指标
        assert "volatility_20d" in result
        assert "momentum_20d" in result
        assert "ma_deviation_20" in result

    def test_insufficient_data_returns_partial(self):
        from quant_engine.indicators import compute_all_indicators
        daily = _make_daily(10)
        result = compute_all_indicators(daily)
        # 数据不足，部分指标为空
        assert isinstance(result, dict)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quant_engine.indicators'`

- [ ] **Step 3: 实现 indicators.py**

`engine/quant_engine/indicators.py`:

```python
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

    Args:
        close: 收盘价序列
        fast: 快线 EMA 周期
        slow: 慢线 EMA 周期
        signal_period: 信号线 EMA 周期

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

    Args:
        close: 收盘价序列
        period: 移动平均周期
        num_std: 标准差倍数

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

    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列
        period: RSV 周期
        k_smooth: K 值平滑周期
        d_smooth: D 值平滑周期

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

    # K = SMA(RSV, k_smooth)
    k = np.full(n, 50.0)
    for i in range(1, n):
        k[i] = (k[i - 1] * (k_smooth - 1) + rsv[i]) / k_smooth

    # D = SMA(K, d_smooth)
    d = np.full(n, 50.0)
    for i in range(1, n):
        d[i] = (d[i - 1] * (d_smooth - 1) + k[i]) / d_smooth

    # J = 3K - 2D
    j = 3 * k - 2 * d

    # 将 K、D 裁剪到 [0, 100]
    k = np.clip(k, 0, 100)
    d = np.clip(d, 0, 100)

    return k, d, j


def compute_all_indicators(daily_df: pd.DataFrame) -> dict:
    """
    计算单只股票的所有技术指标

    综合 indicators.py 新增指标和 features.py 已有指标，
    提供统一的全指标输出。

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
        # 布林带宽度百分比
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_indicators.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add engine/quant_engine/indicators.py engine/tests/test_quant_indicators.py
git commit -m "feat(quant-engine): 新增技术指标计算器 (MACD/布林带/KDJ)"
```

---

### Task 4: QuantEngine 门面类

**Files:**
- Modify: `engine/quant_engine/engine.py` (替换 Task 1 的占位版本)
- Create: `engine/tests/test_quant_engine.py`

- [ ] **Step 1: 编写门面类测试**

`engine/tests/test_quant_engine.py`:

```python
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
        from quant_engine.engine import QuantEngine
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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_engine.py -v`
Expected: FAIL — `AttributeError: 'QuantEngine' object has no attribute 'predictor'`

- [ ] **Step 3: 实现 QuantEngine 门面类**

`engine/quant_engine/engine.py`:

```python
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_engine.py -v`
Expected: 4 passed

- [ ] **Step 5: 运行全部量化引擎测试**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/ -v`
Expected: 25 passed (全部 Task 1-4 的测试: 7+5+9+4)

- [ ] **Step 6: Commit**

```bash
git add engine/quant_engine/engine.py engine/tests/test_quant_engine.py
git commit -m "feat(quant-engine): 实现 QuantEngine 门面类"
```

---

## Chunk 2: 导入重定向 + 兼容 shim (Tasks 5-7)

### Task 5: 更新 ClusterEngine 内部导入

**Files:**
- Modify: `engine/cluster_engine/algorithm/pipeline.py` (line 28)
- Modify: `engine/cluster_engine/engine.py` (line 12, 全部重写 ICIR 逻辑)

- [ ] **Step 1: 更新 pipeline.py 导入**

`engine/cluster_engine/algorithm/pipeline.py` line 28:

```python
# 旧:
from .predictor_v2 import StockPredictorV2

# 新:
from quant_engine.predictor import StockPredictorV2
```

- [ ] **Step 2: 更新 cluster_engine/engine.py**

`engine/cluster_engine/engine.py`:

删除旧顶层导入（line 12，已不再直接使用）：
```python
# 删除这行:
from .algorithm.factor_backtest import run_ic_backtest_from_store
```

修改 `try_auto_inject_icir_weights` 方法，委托给 QuantEngine：

```python
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
```

**注意：** 此处传递 `_icir_weights`（ICIR 原始稀疏权重）而非 `_get_weights()`（含默认值的完整 dict），保持与原有行为语义一致。

- [ ] **Step 3: 验证 cluster_engine 仍可正常导入**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "from cluster_engine import get_cluster_engine; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add engine/cluster_engine/algorithm/pipeline.py engine/cluster_engine/engine.py
git commit -m "refactor: cluster_engine 内部导入改为 quant_engine"
```

---

### Task 6: 更新 routes.py 和 mcpserver 导入

**Files:**
- Modify: `engine/cluster_engine/routes.py` (lines 20, 580)
- Modify: `engine/mcpserver/tools.py` (lines 536, 852)

- [ ] **Step 1: 更新 cluster_engine/routes.py**

Line 20:
```python
# 旧:
from cluster_engine.algorithm.factor_backtest import run_ic_backtest_from_store

# 新:
from quant_engine.factor_backtest import run_ic_backtest_from_store
```

Line 580:
```python
# 旧:
from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS

# 新:
from quant_engine.predictor import FACTOR_DEFS
```

- [ ] **Step 2: 更新 mcpserver/tools.py**

Line 536:
```python
# 旧:
from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS

# 新:
from quant_engine.predictor import FACTOR_DEFS
```

Line 852:
```python
# 旧:
from cluster_engine.algorithm.factor_backtest import FactorBacktester

# 新:
from quant_engine.factor_backtest import FactorBacktester
```

- [ ] **Step 3: 验证导入完整性**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "from mcpserver.tools import *; print('MCP OK')" && python -c "from cluster_engine.routes import router; print('Routes OK')"`
Expected: `MCP OK` 和 `Routes OK`

- [ ] **Step 4: Commit**

```bash
git add engine/cluster_engine/routes.py engine/mcpserver/tools.py
git commit -m "refactor: routes 和 MCP 导入改为 quant_engine"
```

**关于旧路由的说明：** `cluster_engine/routes.py` 中的 `/api/v1/factor/weights` 和 `/api/v1/factor/backtest` 端点保持不变，它们通过 `pipeline.predictor_v2` 直接访问 pipeline 内的预测器实例。新的 `/api/v1/quant/*` 端点操作 QuantEngine 独立的预测器实例。启动时通过 `try_auto_inject_icir_weights()` 同步两个实例的 ICIR 权重。运行时通过旧端点触发的回测只影响 pipeline 预测器，通过新端点触发的只影响 QuantEngine 预测器。这是过渡期可接受的双实例状态——在 Multi-Agent MVP Phase 1 中，旧端点将被标记为 deprecated，所有新功能统一走 `/api/v1/quant/*`。

---

### Task 7: 兼容 shim + 旧文件处理

**Files:**
- Modify: `engine/cluster_engine/algorithm/predictor_v2.py` (改为 re-export shim)
- Modify: `engine/cluster_engine/algorithm/factor_backtest.py` (改为 re-export shim)

**设计说明:** 将旧文件改为兼容 shim（仅 re-export），而非删除。这样如果有遗漏的第三方导入也不会崩溃。旧文件保留 deprecation 警告。

- [ ] **Step 1: 替换 predictor_v2.py 为 shim**

`engine/cluster_engine/algorithm/predictor_v2.py` — 替换全部内容：

```python
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
```

- [ ] **Step 2: 替换 factor_backtest.py 为 shim**

`engine/cluster_engine/algorithm/factor_backtest.py` — 替换全部内容：

```python
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
```

- [ ] **Step 3: 验证 shim 仍可导入**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -W error::DeprecationWarning -c "from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS" 2>&1; echo "Exit: $?"`
Expected: 非零退出码（DeprecationWarning 被提升为 error），证明 shim 发出了警告

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS; print(f'Shim OK: {len(FACTOR_DEFS)} factors')"`
Expected: `Shim OK: 13 factors`（默认不视为错误）

- [ ] **Step 4: 运行全部测试确认无回归**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/ -v`
Expected: 25 passed

- [ ] **Step 5: Commit**

```bash
git add engine/cluster_engine/algorithm/predictor_v2.py engine/cluster_engine/algorithm/factor_backtest.py
git commit -m "refactor: 旧 predictor_v2/factor_backtest 改为兼容 shim (re-export)"
```

---

## Chunk 3: REST API + 配置 + 注册 (Tasks 8-10)

### Task 8: 量化引擎 REST API

**Files:**
- Create: `engine/quant_engine/routes.py`
- Create: `engine/tests/test_quant_routes.py`

- [ ] **Step 1: 编写 API 测试**

`engine/tests/test_quant_routes.py`:

```python
"""量化引擎 — REST API 测试"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


@pytest.fixture
def app():
    """创建测试 FastAPI 应用"""
    from quant_engine.routes import router
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestQuantHealth:
    def test_health(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            mock_qe = MagicMock()
            mock_qe.health_check.return_value = {
                "status": "ok",
                "predictor": "v2.0",
                "factor_count": 13,
                "weight_source": "default",
            }
            mock_get.return_value = mock_qe
            resp = client.get("/api/v1/quant/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


class TestFactorWeights:
    def test_get_weights(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            mock_qe = MagicMock()
            mock_qe.get_factor_weights.return_value = ({"reversal": 0.15}, "default")
            mock_qe.get_factor_defs.return_value = []
            mock_get.return_value = mock_qe
            resp = client.get("/api/v1/quant/factor/weights")
            assert resp.status_code == 200
            assert resp.json()["weight_source"] == "default"


class TestIndicators:
    def test_get_indicators(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get, \
             patch("quant_engine.routes.get_data_engine") as mock_data:
            mock_qe = MagicMock()
            mock_qe.compute_indicators.return_value = {"rsi_14": 55.0, "macd": 0.5}
            mock_get.return_value = mock_qe

            import pandas as pd
            mock_de = MagicMock()
            mock_de.get_daily_history.return_value = pd.DataFrame({
                "close": [10, 11, 12],
                "high": [10.5, 11.5, 12.5],
                "low": [9.5, 10.5, 11.5],
                "pct_chg": [0, 10, 9],
            })
            mock_data.return_value = mock_de

            resp = client.get("/api/v1/quant/indicators/000001")
            assert resp.status_code == 200
            assert "rsi_14" in resp.json()["indicators"]

    def test_get_indicators_not_found(self, client):
        """股票无日线数据时返回 404"""
        with patch("quant_engine.routes.get_quant_engine") as mock_get, \
             patch("quant_engine.routes.get_data_engine") as mock_data:
            import pandas as pd
            mock_de = MagicMock()
            mock_de.get_daily_history.return_value = pd.DataFrame()
            mock_data.return_value = mock_de
            mock_get.return_value = MagicMock()

            resp = client.get("/api/v1/quant/indicators/999999")
            assert resp.status_code == 404


class TestBacktest:
    def test_run_backtest(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            mock_qe = MagicMock()
            mock_result = MagicMock()
            mock_result.backtest_days = 10
            mock_result.total_stocks_avg = 500
            mock_result.computation_time_ms = 123.4
            mock_result.icir_weights = {"reversal": 0.2}
            mock_result.factor_reports = {}
            mock_qe.run_backtest.return_value = mock_result
            mock_get.return_value = mock_qe

            resp = client.post("/api/v1/quant/factor/backtest?rolling_window=20")
            assert resp.status_code == 200
            assert resp.json()["backtest_days"] == 10
            assert resp.json()["weights_injected"] is True


class TestFactorDefs:
    def test_get_defs(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            from quant_engine.predictor import FactorDef
            mock_qe = MagicMock()
            mock_qe.get_factor_defs.return_value = [
                FactorDef("test_factor", "col", 1, "group", 0.1, "测试因子")
            ]
            mock_get.return_value = mock_qe

            resp = client.get("/api/v1/quant/factor/defs")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
            assert resp.json()[0]["name"] == "test_factor"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quant_engine.routes'`

- [ ] **Step 3: 实现 routes.py**

`engine/quant_engine/routes.py`:

```python
"""
量化引擎 REST API

独立路由前缀: /api/v1/quant/*
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from loguru import logger

from quant_engine import get_quant_engine
from data_engine import get_data_engine

router = APIRouter(prefix="/api/v1/quant", tags=["quant"])


@router.get("/health")
async def quant_health():
    """量化引擎健康检查"""
    qe = get_quant_engine()
    return qe.health_check()


@router.get("/factor/weights")
async def get_factor_weights():
    """查看当前因子权重"""
    qe = get_quant_engine()
    weights, source = qe.get_factor_weights()
    factor_defs = qe.get_factor_defs()

    factors = []
    for fdef in factor_defs:
        factors.append({
            "name": fdef.name,
            "source_col": fdef.source_col,
            "direction": fdef.direction,
            "group": fdef.group,
            "weight": weights.get(fdef.name, 0.0),
            "default_weight": fdef.default_weight,
            "desc": fdef.desc,
        })

    return {
        "weight_source": source,
        "factors": factors,
    }


@router.get("/factor/defs")
async def get_factor_defs():
    """获取全部因子定义"""
    qe = get_quant_engine()
    return [
        {
            "name": f.name,
            "source_col": f.source_col,
            "direction": f.direction,
            "group": f.group,
            "default_weight": f.default_weight,
            "desc": f.desc,
        }
        for f in qe.get_factor_defs()
    ]


@router.post("/factor/backtest")
async def run_backtest(
    rolling_window: int = Query(default=20, ge=3, le=60),
    auto_inject: bool = Query(default=True),
):
    """执行因子 IC 回测"""
    qe = get_quant_engine()

    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: qe.run_backtest(rolling_window=rolling_window)
    )

    if auto_inject and result.icir_weights:
        qe.predictor.set_icir_weights(result.icir_weights)

    return {
        "backtest_days": result.backtest_days,
        "total_stocks_avg": result.total_stocks_avg,
        "computation_time_ms": round(result.computation_time_ms, 0),
        "icir_weights": result.icir_weights,
        "weights_injected": auto_inject and bool(result.icir_weights),
        "factor_reports": {
            name: {
                "ic_mean": r.ic_mean,
                "ic_std": r.ic_std,
                "icir": r.icir,
                "ic_positive_rate": r.ic_positive_rate,
                "t_stat": r.t_stat,
                "p_value": r.p_value,
            }
            for name, r in result.factor_reports.items()
        },
    }


@router.get("/indicators/{code}")
async def get_indicators(
    code: str,
    days: int = Query(default=120, ge=20, le=365),
):
    """获取单只股票的全部技术指标"""
    qe = get_quant_engine()
    de = get_data_engine()

    import datetime
    end = datetime.date.today().strftime("%Y-%m-%d")
    start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    daily = await asyncio.get_event_loop().run_in_executor(
        None, lambda: de.get_daily_history(code, start, end)
    )

    if daily is None or daily.empty:
        raise HTTPException(status_code=404, detail=f"股票 {code} 无日线数据")

    indicators = qe.compute_indicators(daily)
    return {
        "code": code,
        "data_days": len(daily),
        "indicators": indicators,
    }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/test_quant_routes.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add engine/quant_engine/routes.py engine/tests/test_quant_routes.py
git commit -m "feat(quant-engine): 新增独立 REST API (/api/v1/quant/*)"
```

---

### Task 9: main.py 注册 + config.py 扩展

**Files:**
- Modify: `engine/main.py`
- Modify: `engine/config.py`

- [ ] **Step 1: config.py 新增 QuantConfig**

在 `engine/config.py` 的 `RedisConfig` 类之后、`AppConfig` 之前插入：

```python
# ─── 量化引擎配置 ─────────────────────────────────────
class QuantConfig(BaseModel):
    """量化引擎配置"""
    icir_rolling_window: int = 20        # ICIR 滚动窗口天数
    auto_inject_on_startup: bool = True  # 启动时自动注入 ICIR 权重
    min_history_days: int = 5            # 自动校准最少需要的历史天数
```

在 `AppConfig` 中添加：

```python
class AppConfig(BaseModel):
    datasource: DataSourceConfig = DataSourceConfig()
    umap: UMAPConfig = UMAPConfig()
    hdbscan: HDBSCANConfig = HDBSCANConfig()
    feature_fusion: FeatureFusionConfig = FeatureFusionConfig()
    interpolation: InterpolationConfig = InterpolationConfig()
    server: ServerConfig = ServerConfig()
    redis: RedisConfig = RedisConfig()
    quant: QuantConfig = QuantConfig()    # ← 新增
```

- [ ] **Step 2: main.py 注册 quant_router**

在 `engine/main.py` 的导入区域添加：

```python
from quant_engine.routes import router as quant_router
```

在路由注册区域添加：

```python
app.include_router(quant_router)
```

修改 startup 事件中的 ICIR 自动校准，改为走 QuantEngine：

```python
@app.on_event("startup")
async def startup():
    from llm.config import llm_settings
    logger.info("=" * 60)
    logger.info("🏔️  StockTerrain Engine 启动")
    logger.info(f"   数据源: AKShare(主力) + BaoStock(备选)")
    logger.info(f"   算法: HDBSCAN + UMAP + RBF")
    logger.info(f"   预测: v2.0 (MAD去极值 + 正交化 + ICIR自适应权重)")
    logger.info(f"   量化引擎: 已加载 (13因子 + 技术指标)")
    logger.info(f"   LLM: {'已配置 (' + llm_settings.provider + '/' + llm_settings.model + ')' if llm_settings.api_key else '未配置 (可在设置中启用)'}")
    logger.info(f"   端口: {settings.server.port}")
    logger.info(f"   API 文档: http://localhost:{settings.server.port}/docs")
    logger.info("=" * 60)

    # 自动尝试 ICIR 权重校准（通过 QuantEngine）
    if settings.quant.auto_inject_on_startup:
        try:
            from quant_engine import get_quant_engine
            qe = get_quant_engine()
            qe.try_auto_inject_icir_weights()
            # 同步到 ClusterEngine 的 pipeline（单独 try 避免掩盖 ClusterEngine 初始化错误）
            if qe.predictor._icir_weights is not None:
                try:
                    from cluster_engine import get_cluster_engine
                    get_cluster_engine().pipeline.predictor_v2.set_icir_weights(
                        qe.predictor._icir_weights
                    )
                except Exception as e:
                    logger.warning(f"⚠️ ICIR 权重同步到 ClusterEngine 失败: {e}")
        except Exception as e:
            logger.warning(f"⚠️ ICIR 自动校准跳过: {e}")
```

在 root 路由的 endpoints 字典中添加：

```python
"quant_health": "GET /api/v1/quant/health",
"quant_factor_weights": "GET /api/v1/quant/factor/weights",
"quant_factor_defs": "GET /api/v1/quant/factor/defs",
"quant_backtest": "POST /api/v1/quant/factor/backtest",
"quant_indicators": "GET /api/v1/quant/indicators/{code}",
```

- [ ] **Step 3: 验证应用可启动**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "from main import app; print(f'Routes: {len(app.routes)}')" `
Expected: 打印路由数量，无 ImportError

- [ ] **Step 4: Commit**

```bash
git add engine/main.py engine/config.py
git commit -m "feat: 注册 QuantEngine 路由 + 新增 QuantConfig"
```

---

### Task 10: 端到端验证 + 整理

**Files:**
- 无新文件，纯验证

- [ ] **Step 1: 运行全部测试**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -m pytest tests/ -v`
Expected: 全部 passed (31 tests: 7+5+9+4+6)

- [ ] **Step 2: 验证全部导入路径**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "
# 新路径
from quant_engine.predictor import FACTOR_DEFS, StockPredictorV2, PredictionResult, FactorDef
from quant_engine.factor_backtest import FactorBacktester, BacktestResult, run_ic_backtest_from_store
from quant_engine.indicators import compute_rsi, compute_macd, compute_bollinger_bands, compute_kdj, compute_all_indicators
from quant_engine.engine import QuantEngine
from quant_engine import get_quant_engine

# 旧路径 shim（应触发 DeprecationWarning）
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS as _
    from cluster_engine.algorithm.factor_backtest import FactorBacktester as _
    shim_warnings = [x for x in w if 'quant_engine' in str(x.message)]
    assert len(shim_warnings) == 2, f'Expected 2 shim DeprecationWarnings, got {len(shim_warnings)}'

# ClusterEngine 正常
from cluster_engine import get_cluster_engine

# MCP 正常
from mcpserver.tools import server

# Routes 正常
from cluster_engine.routes import router as cr
from quant_engine.routes import router as qr

print('✅ 全部导入验证通过')
"
```

Expected: `✅ 全部导入验证通过`

- [ ] **Step 3: 验证应用启动无错误**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "import subprocess, sys, time; p = subprocess.Popen([sys.executable, 'main.py'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True); time.sleep(5); p.terminate(); print(p.stdout.read())" 2>&1 | head -20`
Expected: 看到 "StockTerrain Engine 启动" 日志，无 ImportError 或 AttributeError

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git status  # 确认没有意外文件
git commit -m "feat(quant-engine): 量化引擎独立完成 — 路线图 Phase 2 ✅

- quant_engine/ 模块: predictor + factor_backtest + indicators + engine 门面
- 13 因子预测器 + IC 回测从 cluster_engine 迁移
- 新增 MACD/布林带/KDJ 技术指标计算器
- 独立 REST API: /api/v1/quant/*
- 旧路径保留兼容 shim (DeprecationWarning)
- 31 单元测试覆盖"
```

---

## 验收标准

| 项目 | 标准 |
|------|------|
| 模块独立 | `quant_engine/` 可独立导入，不依赖 `cluster_engine` |
| 向后兼容 | 旧导入路径 `cluster_engine.algorithm.predictor_v2` 仍可用，有 DeprecationWarning |
| API 独立 | `/api/v1/quant/*` 路由正常响应 |
| 测试覆盖 | 31 测试全部通过 |
| ClusterEngine 不受影响 | 聚类引擎所有功能正常（pipeline 仍使用 StockPredictorV2） |
| MCP 不受影响 | 10 个 MCP tools 全部正常（导入路径已更新） |
| 应用启动 | `python main.py` 无错误，ICIR 自动校准正常 |
