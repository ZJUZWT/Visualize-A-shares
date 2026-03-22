# 数据源升级 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 DataProvider 统一抽象层，修复数据质量问题，增加盘中定时快照刷新和分钟K线全频率支持，加固降级链可靠性。

**Architecture:** 在现有 DataCollector 和 DataEngine 之间插入 ProviderManager 层。每个数据源适配为 DataProvider 实现。ProviderManager 负责路由、重试、熔断、健康追踪。DataEngine 对外接口不变。

**Tech Stack:** Python, DuckDB, APScheduler, AKShare, BaoStock, pandas

**Spec:** `docs/superpowers/specs/2026-03-21-data-source-upgrade-design.md`

---

## File Structure

```
backend/engine/data/
├── provider/
│   ├── __init__.py          — 导出所有 Provider + ProviderManager
│   ├── base.py              — DataProvider ABC
│   ├── manager.py           — ProviderManager (路由+重试+熔断+健康)
│   ├── tencent.py           — TencentProvider (wrap TencentSource)
│   ├── akshare.py           — AKShareProvider (wrap AKShareSource)
│   ├── eastmoney.py         — EastMoneyProvider (wrap EastMoneyDirectSource)
│   ├── ths.py               — THSProvider (wrap THSSource)
│   └── baostock.py          — BaoStockProvider (wrap BaoStockSource)
├── calendar.py              — TradingCalendar
├── snapshot_scheduler.py    — SnapshotScheduler
├── collector.py             — 保留，标记 deprecated
├── engine.py                — DataEngine (内部切换到 ProviderManager)
├── store.py                 — DuckDBStore (新增表)
└── ...

tests/unit/
├── test_data_provider.py    — DataProvider + ProviderManager 测试
├── test_trading_calendar.py — TradingCalendar 测试
├── test_snapshot_scheduler.py — SnapshotScheduler 测试
└── test_data_kline_multi.py — 多频率K线测试
```

---

## Chunk 1: Foundation — DataProvider ABC + ProviderManager + Tests

### Task 1: DataProvider 抽象基类

**Files:**
- Create: `backend/engine/data/provider/__init__.py`
- Create: `backend/engine/data/provider/base.py`
- Test: `tests/unit/test_data_provider.py`

- [ ] **Step 1: Create provider package**

```bash
mkdir -p backend/engine/data/provider
```

- [ ] **Step 2: Write DataProvider ABC**

Create `backend/engine/data/provider/base.py`:

```python
"""DataProvider — 数据源统一抽象基类"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """数据源统一接口

    所有方法为同步方法。不支持的方法返回空 DataFrame，不抛异常。
    """

    name: str = ""
    priority: int = 99  # 数字越小优先级越高
    capabilities: set[str] = set()

    @abstractmethod
    def get_snapshot(self) -> pd.DataFrame:
        """全市场实时快照"""
        return pd.DataFrame()

    @abstractmethod
    def get_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        """个股日线历史"""
        return pd.DataFrame()

    @abstractmethod
    def get_kline(self, code: str, freq: str, days: int) -> pd.DataFrame:
        """分钟K线"""
        return pd.DataFrame()

    @abstractmethod
    def get_financial(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """季频财务数据"""
        return pd.DataFrame()

    @abstractmethod
    def get_news(self, code: str, limit: int) -> pd.DataFrame:
        """个股新闻"""
        return pd.DataFrame()

    @abstractmethod
    def get_announcements(self, code: str, limit: int) -> pd.DataFrame:
        """公司公告"""
        return pd.DataFrame()

    @abstractmethod
    def get_sector_board_list(self, board_type: str) -> pd.DataFrame:
        """板块列表+行情"""
        return pd.DataFrame()

    @abstractmethod
    def get_sector_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        """板块历史K线"""
        return pd.DataFrame()

    @abstractmethod
    def get_sector_fund_flow_rank(self, indicator: str, sector_type: str) -> pd.DataFrame:
        """板块资金流排行"""
        return pd.DataFrame()

    @abstractmethod
    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        """板块成分股"""
        return pd.DataFrame()

    @abstractmethod
    def get_intraday_history(self, code: str, freq: str, start: str, end: str) -> pd.DataFrame:
        """分钟级历史数据"""
        return pd.DataFrame()

    @abstractmethod
    def get_market_history_batch(self, codes: list[str], days: int, on_progress=None, on_batch_done=None) -> dict[str, pd.DataFrame]:
        """全市场历史批量"""
        return {}

    def supports(self, capability: str) -> bool:
        """检查是否支持某能力"""
        return capability in self.capabilities
```

- [ ] **Step 3: Write __init__.py**

Create `backend/engine/data/provider/__init__.py`:

```python
from .base import DataProvider
from .manager import ProviderManager

__all__ = ["DataProvider", "ProviderManager"]
```

- [ ] **Step 4: Write failing test for DataProvider**

Create `tests/unit/test_data_provider.py`:

```python
"""DataProvider + ProviderManager 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import pandas as pd
import pytest

from engine.data.provider.base import DataProvider


class DummyProvider(DataProvider):
    """测试用 Provider"""
    name = "dummy"
    priority = 0
    capabilities = {"snapshot", "daily"}

    def __init__(self, snapshot_data=None, fail=False):
        self._snapshot_data = snapshot_data
        self._fail = fail

    def get_snapshot(self):
        if self._fail:
            raise ConnectionError("模拟连接失败")
        return self._snapshot_data if self._snapshot_data is not None else pd.DataFrame()

    def get_daily(self, code, start, end):
        return pd.DataFrame({"date": ["2026-01-01"], "close": [10.0]})

    def get_kline(self, code, freq, days):
        return pd.DataFrame()

    def get_financial(self, code, year, quarter):
        return pd.DataFrame()

    def get_news(self, code, limit):
        return pd.DataFrame()

    def get_announcements(self, code, limit):
        return pd.DataFrame()

    def get_sector_board_list(self, board_type):
        return pd.DataFrame()

    def get_sector_board_history(self, board_name, board_type, start_date, end_date):
        return pd.DataFrame()

    def get_sector_fund_flow_rank(self, indicator, sector_type):
        return pd.DataFrame()

    def get_sector_constituents(self, board_name):
        return pd.DataFrame()

    def get_intraday_history(self, code, freq, start, end):
        return pd.DataFrame()

    def get_market_history_batch(self, codes, days, on_progress=None, on_batch_done=None):
        return {}


class TestDataProvider:
    def test_supports_capability(self):
        p = DummyProvider()
        assert p.supports("snapshot") is True
        assert p.supports("financial") is False

    def test_provider_returns_data(self):
        df = pd.DataFrame({"code": ["600519"], "price": [1800.0]})
        p = DummyProvider(snapshot_data=df)
        result = p.get_snapshot()
        assert len(result) == 1
        assert result.iloc[0]["code"] == "600519"

    def test_provider_fail_raises(self):
        p = DummyProvider(fail=True)
        with pytest.raises(ConnectionError):
            p.get_snapshot()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_data_provider.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/engine/data/provider/ tests/unit/test_data_provider.py
git commit -m "feat(data): DataProvider 抽象基类"
```

---

### Task 2: ProviderManager — 路由 + 重试 + 熔断

**Files:**
- Create: `backend/engine/data/provider/manager.py`
- Modify: `tests/unit/test_data_provider.py`

- [ ] **Step 1: Write failing tests for ProviderManager**

Append to `tests/unit/test_data_provider.py`:

```python
import time
from engine.data.provider.manager import ProviderManager


class DummyProviderB(DataProvider):
    """第二优先级 Provider"""
    name = "dummy_b"
    priority = 1
    capabilities = {"snapshot", "daily"}

    def get_snapshot(self):
        return pd.DataFrame({"code": ["000001"], "price": [15.0]})

    def get_daily(self, code, start, end):
        return pd.DataFrame()

    def get_kline(self, code, freq, days):
        return pd.DataFrame()

    def get_financial(self, code, year, quarter):
        return pd.DataFrame()

    def get_news(self, code, limit):
        return pd.DataFrame()

    def get_announcements(self, code, limit):
        return pd.DataFrame()

    def get_sector_board_list(self, board_type):
        return pd.DataFrame()

    def get_sector_board_history(self, board_name, board_type, start_date, end_date):
        return pd.DataFrame()

    def get_sector_fund_flow_rank(self, indicator, sector_type):
        return pd.DataFrame()

    def get_sector_constituents(self, board_name):
        return pd.DataFrame()

    def get_intraday_history(self, code, freq, start, end):
        return pd.DataFrame()

    def get_market_history_batch(self, codes, days, on_progress=None, on_batch_done=None):
        return {}


class TestProviderManager:
    def test_routes_to_highest_priority(self):
        """请求路由到最高优先级的 provider"""
        pa = DummyProvider(snapshot_data=pd.DataFrame({"code": ["600519"], "price": [1800.0]}))
        pb = DummyProviderB()
        mgr = ProviderManager([pb, pa])  # 乱序传入
        result = mgr.get_snapshot()
        assert result.iloc[0]["code"] == "600519"  # pa priority=0 先被调用

    def test_fallback_on_failure(self):
        """第一个 provider 失败时降级到第二个"""
        pa = DummyProvider(fail=True)
        pb = DummyProviderB()
        mgr = ProviderManager([pa, pb])
        result = mgr.get_snapshot()
        assert result.iloc[0]["code"] == "000001"  # 降级到 pb

    def test_circuit_breaker(self):
        """连续失败触发熔断"""
        pa = DummyProvider(fail=True)
        pb = DummyProviderB()
        mgr = ProviderManager([pa, pb], circuit_threshold=3, circuit_timeout=1)
        # 触发 3 次失败
        for _ in range(3):
            mgr.get_snapshot()
        # pa 应该被熔断，直接跳到 pb
        health = mgr.get_health()
        assert health["providers"]["dummy"]["status"] == "circuit_broken"

    def test_circuit_breaker_recovery(self):
        """熔断后探活恢复"""
        pa = DummyProvider(fail=True)
        pb = DummyProviderB()
        mgr = ProviderManager([pa, pb], circuit_threshold=3, circuit_timeout=1)
        for _ in range(3):
            mgr.get_snapshot()
        # 等待熔断超时
        time.sleep(1.1)
        # 修复 pa
        pa._fail = False
        pa._snapshot_data = pd.DataFrame({"code": ["600519"], "price": [1800.0]})
        result = mgr.get_snapshot()
        assert result.iloc[0]["code"] == "600519"  # pa 恢复
        health = mgr.get_health()
        assert health["providers"]["dummy"]["status"] == "healthy"

    def test_capability_routing(self):
        """只路由到支持该 capability 的 provider"""
        pa = DummyProvider()
        pa.capabilities = {"snapshot"}  # 不支持 daily
        pb = DummyProviderB()
        pb.capabilities = {"daily"}
        mgr = ProviderManager([pa, pb])
        result = mgr.get_daily("600519", "2026-01-01", "2026-03-01")
        assert len(result) == 0  # pb 返回空 DataFrame

    def test_all_fail_returns_empty(self):
        """所有 provider 都失败返回空 DataFrame"""
        pa = DummyProvider(fail=True)
        mgr = ProviderManager([pa])
        result = mgr.get_snapshot()
        assert result.empty

    def test_health_report(self):
        """健康报告包含所有 provider 状态"""
        pa = DummyProvider()
        pb = DummyProviderB()
        mgr = ProviderManager([pa, pb])
        mgr.get_snapshot()
        health = mgr.get_health()
        assert "dummy" in health["providers"]
        assert "dummy_b" in health["providers"]
        assert health["providers"]["dummy"]["status"] == "healthy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_data_provider.py::TestProviderManager -v`
Expected: FAIL (manager.py not found)

- [ ] **Step 3: Implement ProviderManager**

Create `backend/engine/data/provider/manager.py`:

```python
"""ProviderManager — 数据源路由 + 重试 + 熔断 + 健康追踪"""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime

import pandas as pd
from loguru import logger

from .base import DataProvider


class _ProviderState:
    """单个 Provider 的运行状态"""

    def __init__(self, provider: DataProvider, circuit_threshold: int, circuit_timeout: float):
        self.provider = provider
        self.circuit_threshold = circuit_threshold
        self.circuit_timeout = circuit_timeout
        self.consecutive_failures = 0
        self.circuit_broken_until: float | None = None
        self.history: deque[dict] = deque(maxlen=100)

    @property
    def is_circuit_broken(self) -> bool:
        if self.circuit_broken_until is None:
            return False
        if time.monotonic() >= self.circuit_broken_until:
            # 熔断期满，允许探活
            return False
        return True

    def record_success(self, latency_ms: float):
        self.consecutive_failures = 0
        self.circuit_broken_until = None
        self.history.append({"ok": True, "latency_ms": latency_ms, "ts": datetime.now().isoformat()})

    def record_failure(self, error: str, latency_ms: float):
        self.consecutive_failures += 1
        self.history.append({"ok": False, "error": error, "latency_ms": latency_ms, "ts": datetime.now().isoformat()})
        if self.consecutive_failures >= self.circuit_threshold:
            self.circuit_broken_until = time.monotonic() + self.circuit_timeout
            logger.warning(f"🔌 {self.provider.name} 熔断 {self.circuit_timeout}s (连续失败 {self.consecutive_failures} 次)")

    def get_status(self) -> dict:
        successes = sum(1 for h in self.history if h["ok"])
        total = len(self.history)
        avg_latency = sum(h["latency_ms"] for h in self.history) / total if total > 0 else 0
        last_failure = None
        for h in reversed(self.history):
            if not h["ok"]:
                last_failure = h["ts"]
                break

        if self.is_circuit_broken:
            status = "circuit_broken"
        elif total > 0 and successes / total < 0.5:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "success_rate": round(successes / total, 2) if total > 0 else 1.0,
            "avg_latency_ms": round(avg_latency, 1),
            "last_failure": last_failure,
            "circuit_broken_until": datetime.fromtimestamp(self.circuit_broken_until).isoformat() if self.circuit_broken_until and self.is_circuit_broken else None,
        }


# capability → method name 映射
_CAPABILITY_METHOD_MAP = {
    "snapshot": "get_snapshot",
    "daily": "get_daily",
    "kline_5m": "get_kline",
    "kline_15m": "get_kline",
    "kline_30m": "get_kline",
    "kline_60m": "get_kline",
    "financial": "get_financial",
    "news": "get_news",
    "announcements": "get_announcements",
    "sector_board": "get_sector_board_list",
    "sector_history": "get_sector_board_history",
    "sector_fund_flow": "get_sector_fund_flow_rank",
    "sector_constituents": "get_sector_constituents",
    "market_history_batch": "get_market_history_batch",
}


class ProviderManager:
    """数据源管理器 — 路由 + 重试 + 熔断 + 健康追踪"""

    def __init__(
        self,
        providers: list[DataProvider],
        max_retries: int = 2,
        retry_delays: tuple[float, ...] = (0.5, 1.0),
        circuit_threshold: int = 3,
        circuit_timeout: float = 60.0,
    ):
        # 按 priority 排序
        sorted_providers = sorted(providers, key=lambda p: p.priority)
        self._states: list[_ProviderState] = [
            _ProviderState(p, circuit_threshold, circuit_timeout)
            for p in sorted_providers
        ]
        self._max_retries = max_retries
        self._retry_delays = retry_delays

    def _call_with_fallback(self, capability: str, method_name: str, *args, **kwargs):
        """通用调用：按优先级尝试，带重试和熔断"""
        for state in self._states:
            if not state.provider.supports(capability):
                continue
            if state.is_circuit_broken:
                continue

            # 尝试调用（含重试）
            last_error = None
            for attempt in range(1 + self._max_retries):
                start = time.monotonic()
                try:
                    method = getattr(state.provider, method_name)
                    result = method(*args, **kwargs)
                    latency = (time.monotonic() - start) * 1000
                    state.record_success(latency)
                    return result
                except Exception as e:
                    latency = (time.monotonic() - start) * 1000
                    last_error = e
                    if attempt < self._max_retries:
                        delay = self._retry_delays[min(attempt, len(self._retry_delays) - 1)]
                        time.sleep(delay)

            # 重试耗尽，记录失败
            state.record_failure(str(last_error), latency)
            logger.warning(f"📡 {state.provider.name}.{method_name} 失败: {last_error}")

        # 所有 provider 都失败
        logger.error(f"📡 所有数据源 {method_name} 均失败")
        return pd.DataFrame()

    def _call_dict_with_fallback(self, capability: str, method_name: str, *args, **kwargs):
        """返回 dict 的调用（如 get_market_history_batch）"""
        for state in self._states:
            if not state.provider.supports(capability):
                continue
            if state.is_circuit_broken:
                continue

            last_error = None
            for attempt in range(1 + self._max_retries):
                start = time.monotonic()
                try:
                    method = getattr(state.provider, method_name)
                    result = method(*args, **kwargs)
                    latency = (time.monotonic() - start) * 1000
                    state.record_success(latency)
                    return result
                except Exception as e:
                    latency = (time.monotonic() - start) * 1000
                    last_error = e
                    if attempt < self._max_retries:
                        delay = self._retry_delays[min(attempt, len(self._retry_delays) - 1)]
                        time.sleep(delay)

            state.record_failure(str(last_error), latency)
            logger.warning(f"📡 {state.provider.name}.{method_name} 失败: {last_error}")

        logger.error(f"📡 所有数据源 {method_name} 均失败")
        return {}

    # ── 公开方法（与 DataProvider 一一对应）──

    def get_snapshot(self) -> pd.DataFrame:
        return self._call_with_fallback("snapshot", "get_snapshot")

    def get_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        return self._call_with_fallback("daily", "get_daily", code, start, end)

    def get_kline(self, code: str, freq: str, days: int) -> pd.DataFrame:
        cap = f"kline_{freq}" if not freq.endswith("m") else f"kline_{freq}"
        return self._call_with_fallback(cap, "get_kline", code, freq, days)

    def get_financial(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        return self._call_with_fallback("financial", "get_financial", code, year, quarter)

    def get_news(self, code: str, limit: int) -> pd.DataFrame:
        return self._call_with_fallback("news", "get_news", code, limit)

    def get_announcements(self, code: str, limit: int) -> pd.DataFrame:
        return self._call_with_fallback("announcements", "get_announcements", code, limit)

    def get_sector_board_list(self, board_type: str) -> pd.DataFrame:
        return self._call_with_fallback("sector_board", "get_sector_board_list", board_type)

    def get_sector_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self._call_with_fallback("sector_history", "get_sector_board_history", board_name, board_type, start_date, end_date)

    def get_sector_fund_flow_rank(self, indicator: str, sector_type: str) -> pd.DataFrame:
        return self._call_with_fallback("sector_fund_flow", "get_sector_fund_flow_rank", indicator, sector_type)

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        return self._call_with_fallback("sector_constituents", "get_sector_constituents", board_name)

    def get_intraday_history(self, code: str, freq: str, start: str, end: str) -> pd.DataFrame:
        cap = f"kline_{freq}m" if not freq.endswith("m") else f"kline_{freq}"
        return self._call_with_fallback(cap, "get_intraday_history", code, freq, start, end)

    def get_market_history_batch(self, codes: list[str], days: int, on_progress=None, on_batch_done=None) -> dict[str, pd.DataFrame]:
        return self._call_dict_with_fallback("market_history_batch", "get_market_history_batch", codes, days, on_progress, on_batch_done)

    # ── 健康状态 ──

    def get_health(self) -> dict:
        return {
            "providers": {
                state.provider.name: state.get_status()
                for state in self._states
            }
        }

    @property
    def available_sources(self) -> list[str]:
        return [s.provider.name for s in self._states]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_data_provider.py -v`
Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/engine/data/provider/ tests/unit/test_data_provider.py
git commit -m "feat(data): ProviderManager 路由+重试+熔断+健康追踪"
```

---

## Chunk 2: Provider 适配 + TradingCalendar

### Task 3: TradingCalendar — 交易日历

**Files:**
- Create: `backend/engine/data/calendar.py`
- Modify: `backend/engine/data/store.py` (新增 trading_calendar 表)
- Test: `tests/unit/test_trading_calendar.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_trading_calendar.py`:

```python
"""TradingCalendar 单元测试"""
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import duckdb
import pytest

from engine.data.calendar import TradingCalendar


class TestTradingCalendar:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._db_path = Path(self._tmp) / "test_cal.duckdb"
        self._conn = duckdb.connect(str(self._db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_calendar (
                trade_date DATE PRIMARY KEY
            )
        """)
        # 插入一些测试交易日（2026年3月的工作日，排除周末）
        dates = [
            "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06",
            "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12", "2026-03-13",
            "2026-03-16", "2026-03-17", "2026-03-18", "2026-03-19", "2026-03-20",
        ]
        for d in dates:
            self._conn.execute("INSERT INTO trading_calendar VALUES (?)", [d])
        self._cal = TradingCalendar(self._conn)

    def teardown_method(self):
        self._conn.close()

    def test_is_trading_day_true(self):
        assert self._cal.is_trading_day(date(2026, 3, 2)) is True

    def test_is_trading_day_weekend(self):
        assert self._cal.is_trading_day(date(2026, 3, 1)) is False  # 周日

    def test_is_trading_day_fallback_when_empty(self):
        """日历为空时 fallback 到周末排除"""
        conn2 = duckdb.connect(str(Path(self._tmp) / "empty.duckdb"))
        conn2.execute("CREATE TABLE trading_calendar (trade_date DATE PRIMARY KEY)")
        cal2 = TradingCalendar(conn2)
        # 周一应该返回 True（fallback）
        assert cal2.is_trading_day(date(2026, 3, 2)) is True
        # 周六应该返回 False
        assert cal2.is_trading_day(date(2026, 2, 28)) is False
        conn2.close()

    def test_last_trading_day(self):
        result = self._cal.last_trading_day()
        assert result == date(2026, 3, 20)

    def test_trading_days_between(self):
        count = self._cal.trading_days_between(date(2026, 3, 2), date(2026, 3, 6))
        assert count == 3  # 3,4,5 (不含首尾)

    def test_is_trading_hours(self):
        from unittest.mock import patch
        from datetime import datetime, time as dtime
        # 盘中
        with patch("engine.data.calendar.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2, 10, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert self._cal.is_trading_hours() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_trading_calendar.py -v`
Expected: FAIL (calendar.py not found)

- [ ] **Step 3: Implement TradingCalendar**

Create `backend/engine/data/calendar.py`:

```python
"""TradingCalendar — 交易日历工具类"""
from __future__ import annotations

from datetime import date, datetime, time as dtime

from loguru import logger


class TradingCalendar:
    """交易日历

    从 DuckDB trading_calendar 表加载交易日。
    如果表为空，fallback 到周末排除逻辑。
    """

    # 盘中时段
    _MORNING_OPEN = dtime(9, 30)
    _MORNING_CLOSE = dtime(11, 30)
    _AFTERNOON_OPEN = dtime(13, 0)
    _AFTERNOON_CLOSE = dtime(15, 0)

    def __init__(self, conn):
        self._conn = conn
        self._trading_days: set[date] = set()
        self._load()

    def _load(self):
        """从 DuckDB 加载交易日"""
        try:
            rows = self._conn.execute(
                "SELECT trade_date FROM trading_calendar ORDER BY trade_date"
            ).fetchall()
            self._trading_days = {r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0])) for r in rows}
            if self._trading_days:
                logger.info(f"📅 交易日历已加载: {len(self._trading_days)} 个交易日")
        except Exception as e:
            logger.warning(f"📅 交易日历加载失败: {e}")

    @property
    def _has_calendar(self) -> bool:
        return len(self._trading_days) > 0

    def is_trading_day(self, d: date) -> bool:
        if self._has_calendar:
            return d in self._trading_days
        # fallback: 排除周末
        return d.weekday() < 5

    def last_trading_day(self) -> date:
        if self._has_calendar:
            today = date.today()
            candidates = sorted([d for d in self._trading_days if d <= today], reverse=True)
            if candidates:
                return candidates[0]
        # fallback
        d = date.today()
        while d.weekday() >= 5:
            from datetime import timedelta
            d -= timedelta(days=1)
        return d

    def trading_days_between(self, start: date, end: date) -> int:
        """start 和 end 之间的交易日数（不含 start 和 end）"""
        if self._has_calendar:
            return sum(1 for d in self._trading_days if start < d < end)
        # fallback
        count = 0
        from datetime import timedelta
        cur = start + timedelta(days=1)
        while cur < end:
            if cur.weekday() < 5:
                count += 1
            cur += timedelta(days=1)
        return count

    def is_trading_hours(self) -> bool:
        """当前是否在盘中时段"""
        now = datetime.now().time()
        return (self._MORNING_OPEN <= now <= self._MORNING_CLOSE or
                self._AFTERNOON_OPEN <= now <= self._AFTERNOON_CLOSE)

    def refresh(self):
        """从 AKShare 拉取交易日历并持久化"""
        try:
            import akshare as ak
            df = ak.tool_trade_date_hist_sina()
            if df is not None and len(df) > 0:
                col = df.columns[0]
                import pandas as pd
                dates = pd.to_datetime(df[col]).dt.date.tolist()
                current_year = date.today().year
                dates = [d for d in dates if d.year >= current_year - 1]
                self._conn.execute("DELETE FROM trading_calendar WHERE 1=1")
                for d in dates:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO trading_calendar VALUES (?)", [d]
                    )
                self._trading_days = set(dates)
                logger.info(f"📅 交易日历已刷新: {len(dates)} 个交易日")
        except Exception as e:
            logger.warning(f"📅 交易日历刷新失败（使用 fallback）: {e}")
```

- [ ] **Step 4: Add trading_calendar table to DuckDBStore._init_tables**

在 `backend/engine/data/store.py` 的 `_init_tables` 方法中追加：

```python
self._conn.execute("""
    CREATE TABLE IF NOT EXISTS trading_calendar (
        trade_date DATE PRIMARY KEY
    )
""")
```

- [ ] **Step 5: Run tests**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_trading_calendar.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/engine/data/calendar.py backend/engine/data/store.py tests/unit/test_trading_calendar.py
git commit -m "feat(data): TradingCalendar 交易日历"
```

---

### Task 4: Provider 适配 — 包装现有 Source 类

**Files:**
- Create: `backend/engine/data/provider/tencent.py`
- Create: `backend/engine/data/provider/akshare.py`
- Create: `backend/engine/data/provider/eastmoney.py`
- Create: `backend/engine/data/provider/ths.py`
- Create: `backend/engine/data/provider/baostock.py`
- Modify: `backend/engine/data/provider/__init__.py`

每个 Provider 是对现有 Source 类的薄包装。以 TencentProvider 为例：

- [ ] **Step 1: Implement TencentProvider**

Create `backend/engine/data/provider/tencent.py`:

```python
"""TencentProvider — 包装 TencentSource"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from .base import DataProvider


class TencentProvider(DataProvider):
    name = "tencent"
    priority = 0
    capabilities = {
        "snapshot", "daily",
        "kline_5m", "kline_15m", "kline_30m", "kline_60m",
    }

    def __init__(self):
        try:
            from engine.data.collector import TencentSource
            self._source = TencentSource()
        except Exception as e:
            logger.warning(f"TencentProvider 初始化失败: {e}")
            self._source = None

    def get_snapshot(self) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_realtime_quotes()

    def get_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_daily_history(code, start, end)

    def get_kline(self, code: str, freq: str, days: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        freq_key = freq.replace("m", "")
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=days + 5)
        return self._source.get_intraday_history(code, freq_key, start.isoformat(), end.isoformat())

    def get_financial(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()  # Tencent 不支持

    def get_news(self, code: str, limit: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_announcements(self, code: str, limit: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_sector_board_list(self, board_type: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_sector_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_sector_fund_flow_rank(self, indicator: str, sector_type: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        return pd.DataFrame()

    def get_intraday_history(self, code: str, freq: str, start: str, end: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_intraday_history(code, freq, start, end)

    def get_market_history_batch(self, codes, days, on_progress=None, on_batch_done=None):
        return {}  # Tencent 不支持批量历史
```

- [ ] **Step 2: Implement AKShareProvider**

Create `backend/engine/data/provider/akshare.py`:

```python
"""AKShareProvider — 包装 AKShareSource"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from .base import DataProvider


class AKShareProvider(DataProvider):
    name = "akshare"
    priority = 1
    capabilities = {
        "snapshot", "daily",
        "kline_5m", "kline_15m", "kline_30m", "kline_60m",
        "financial", "news", "announcements",
        "sector_board", "sector_history", "sector_fund_flow", "sector_constituents",
        "market_history_batch",
    }

    def __init__(self):
        try:
            from engine.data.collector import AKShareSource
            self._source = AKShareSource()
        except Exception as e:
            logger.warning(f"AKShareProvider 初始化失败: {e}")
            self._source = None

    def get_snapshot(self) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_realtime_quotes()

    def get_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_daily_history(code, start, end)

    def get_kline(self, code: str, freq: str, days: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        freq_key = freq.replace("m", "")
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=days + 5)
        return self._source.get_intraday_history(code, freq_key, start.isoformat(), end.isoformat())

    def get_financial(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_financial_data(code, year, quarter)

    def get_news(self, code: str, limit: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_stock_news(code, limit)

    def get_announcements(self, code: str, limit: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_announcements(code, limit)

    def get_sector_board_list(self, board_type: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_board_list(board_type)

    def get_sector_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_board_history(board_name, board_type, start_date, end_date)

    def get_sector_fund_flow_rank(self, indicator: str, sector_type: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_fund_flow_rank(indicator, sector_type)

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_constituents(board_name)

    def get_intraday_history(self, code: str, freq: str, start: str, end: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_intraday_history(code, freq, start, end)

    def get_market_history_batch(self, codes, days, on_progress=None, on_batch_done=None):
        if not self._source:
            return {}
        return self._source.get_market_history_streaming(codes, days, on_progress, on_batch_done)
```

- [ ] **Step 3: Implement EastMoneyProvider**

Create `backend/engine/data/provider/eastmoney.py`:

```python
"""EastMoneyProvider — 包装 EastMoneyDirectSource"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from .base import DataProvider


class EastMoneyProvider(DataProvider):
    name = "eastmoney"
    priority = 0  # 板块首选，与 Tencent 同级
    capabilities = {
        "snapshot", "daily",
        "kline_5m", "kline_15m", "kline_30m", "kline_60m",
        "news", "announcements",
        "sector_board", "sector_history", "sector_fund_flow", "sector_constituents",
    }

    def __init__(self):
        try:
            from engine.data.collector import EastMoneyDirectSource
            self._source = EastMoneyDirectSource()
        except Exception as e:
            logger.warning(f"EastMoneyProvider 初始化失败: {e}")
            self._source = None

    def get_snapshot(self) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_realtime_quotes()

    def get_daily(self, code: str, start: str, end: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_daily_history(code, start, end)

    def get_kline(self, code: str, freq: str, days: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        freq_key = freq.replace("m", "")
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=days + 5)
        return self._source.get_intraday_history(code, freq_key, start.isoformat(), end.isoformat())

    def get_financial(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        return pd.DataFrame()

    def get_news(self, code: str, limit: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_stock_news(code, limit)

    def get_announcements(self, code: str, limit: int) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_announcements(code, limit)

    def get_sector_board_list(self, board_type: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_board_list(board_type)

    def get_sector_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_board_history(board_name, board_type, start_date, end_date)

    def get_sector_fund_flow_rank(self, indicator: str, sector_type: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_fund_flow_rank(indicator, sector_type)

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_constituents(board_name)

    def get_intraday_history(self, code: str, freq: str, start: str, end: str) -> pd.DataFrame:
        if not self._source:
            return pd.DataFrame()
        return self._source.get_intraday_history(code, freq, start, end)

    def get_market_history_batch(self, codes, days, on_progress=None, on_batch_done=None):
        return {}
```

- [ ] **Step 4: Implement THSProvider**

Create `backend/engine/data/provider/ths.py`:

```python
"""THSProvider — 包装 THSSource"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from .base import DataProvider


class THSProvider(DataProvider):
    name = "ths"
    priority = 2
    capabilities = {"sector_board", "sector_history"}

    def __init__(self):
        try:
            from engine.data.collector import THSSource
            self._source = THSSource()
        except Exception as e:
            logger.warning(f"THSProvider 初始化失败: {e}")
            self._source = None

    def get_snapshot(self):
        return pd.DataFrame()

    def get_daily(self, code, start, end):
        return pd.DataFrame()

    def get_kline(self, code, freq, days):
        return pd.DataFrame()

    def get_financial(self, code, year, quarter):
        return pd.DataFrame()

    def get_news(self, code, limit):
        return pd.DataFrame()

    def get_announcements(self, code, limit):
        return pd.DataFrame()

    def get_sector_board_list(self, board_type):
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_board_list(board_type)

    def get_sector_board_history(self, board_name, board_type, start_date, end_date):
        if not self._source:
            return pd.DataFrame()
        return self._source.get_sector_board_history(board_name, board_type, start_date, end_date)

    def get_sector_fund_flow_rank(self, indicator, sector_type):
        return pd.DataFrame()

    def get_sector_constituents(self, board_name):
        return pd.DataFrame()

    def get_intraday_history(self, code, freq, start, end):
        return pd.DataFrame()

    def get_market_history_batch(self, codes, days, on_progress=None, on_batch_done=None):
        return {}
```

- [ ] **Step 5: Implement BaoStockProvider**

Create `backend/engine/data/provider/baostock.py`:

```python
"""BaoStockProvider — 包装 BaoStockSource"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from .base import DataProvider


class BaoStockProvider(DataProvider):
    name = "baostock"
    priority = 3
    capabilities = {"daily", "financial", "market_history_batch"}

    def __init__(self):
        try:
            from engine.data.collector import BaoStockSource
            self._source = BaoStockSource()
        except Exception as e:
            logger.warning(f"BaoStockProvider 初始化失败: {e}")
            self._source = None

    def get_snapshot(self):
        return pd.DataFrame()

    def get_daily(self, code, start, end):
        if not self._source:
            return pd.DataFrame()
        return self._source.get_daily_history(code, start, end)

    def get_kline(self, code, freq, days):
        return pd.DataFrame()

    def get_financial(self, code, year, quarter):
        if not self._source:
            return pd.DataFrame()
        return self._source.get_financial_data(code, year, quarter)

    def get_news(self, code, limit):
        return pd.DataFrame()

    def get_announcements(self, code, limit):
        return pd.DataFrame()

    def get_sector_board_list(self, board_type):
        return pd.DataFrame()

    def get_sector_board_history(self, board_name, board_type, start_date, end_date):
        return pd.DataFrame()

    def get_sector_fund_flow_rank(self, indicator, sector_type):
        return pd.DataFrame()

    def get_sector_constituents(self, board_name):
        return pd.DataFrame()

    def get_intraday_history(self, code, freq, start, end):
        return pd.DataFrame()

    def get_market_history_batch(self, codes, days, on_progress=None, on_batch_done=None):
        if not self._source:
            return {}
        return self._source.get_market_history_streaming(codes, days, on_progress, on_batch_done)
```

- [ ] **Step 6: Update __init__.py**

Update `backend/engine/data/provider/__init__.py`:

```python
from .base import DataProvider
from .manager import ProviderManager
from .tencent import TencentProvider
from .akshare import AKShareProvider
from .eastmoney import EastMoneyProvider
from .ths import THSProvider
from .baostock import BaoStockProvider

__all__ = [
    "DataProvider", "ProviderManager",
    "TencentProvider", "AKShareProvider", "EastMoneyProvider",
    "THSProvider", "BaoStockProvider",
]
```

- [ ] **Step 7: Commit**

```bash
git add backend/engine/data/provider/
git commit -m "feat(data): 5个 Provider 适配现有数据源"
```

