# Main Agent Phase 1A — 数据层实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Main Agent 构建数据地基 — AgentDB 单例、Pydantic 模型、TradeValidator、Service CRUD、FastAPI 路由，让 AI 能"持仓和交易"。

**Architecture:** 独立 `data/agent.duckdb` 数据库，AgentDB 单例持有长连接 + asyncio.Lock 写锁。6 张 DuckDB 表（portfolio_config, positions, trades, position_strategies, trade_groups, llm_calls）。Service 层封装业务逻辑，TradeValidator 校验 A 股规则。9 个 REST API 端点挂载在 `/api/v1/agent/`。

**Tech Stack:** Python 3.11+, DuckDB, FastAPI, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-main-agent-phase1a-design.md`

---

## File Structure

```
backend/
├── config.py                          ← 修改: 新增 AGENT_DB_PATH
├── main.py                            ← 修改: startup/shutdown 初始化 AgentDB, 挂载 routes
└── engine/agent/
    ├── __init__.py                    ← 新建: 空文件
    ├── db.py                          ← 新建: AgentDB 单例
    ├── models.py                      ← 新建: Pydantic 数据模型 + TradeInput
    ├── validator.py                   ← 新建: TradeValidator
    ├── service.py                     ← 新建: AgentService 业务逻辑
    └── routes.py                      ← 新建: FastAPI 路由

tests/unit/
└── test_agent_phase1a.py              ← 新建: 全部单元测试
```

---

## Chunk 1: 基础设施 (Task 1-3)

### Task 1: config.py — 新增 AGENT_DB_PATH

**Files:**
- Modify: `backend/config.py:10-11`

- [ ] **Step 1: 在 config.py 中新增 AGENT_DB_PATH**

在 `DB_PATH` 下方添加一行：

```python
AGENT_DB_PATH = DATA_DIR / "agent.duckdb"
```

- [ ] **Step 2: 验证 import 正常**

Run: `cd backend && .venv/bin/python -c "from config import AGENT_DB_PATH; print(AGENT_DB_PATH)"`
Expected: 输出 `…/data/agent.duckdb` 路径

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(agent): 新增 AGENT_DB_PATH 配置"
```

---

### Task 2: AgentDB 单例 (db.py)

**Files:**
- Create: `backend/engine/agent/__init__.py`
- Create: `backend/engine/agent/db.py`
- Test: `tests/unit/test_agent_phase1a.py`

- [ ] **Step 1: 创建空 __init__.py**

```python
# backend/engine/agent/__init__.py
```

- [ ] **Step 2: 写 AgentDB 的失败测试**

创建 `tests/unit/test_agent_phase1a.py`：

```python
"""Main Agent Phase 1A 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import duckdb
import pytest
from unittest.mock import patch

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══════════════════════════════════════════════════════
# Task 2: AgentDB
# ═══════════════════════════════════════════════════════

class TestAgentDB:
    """AgentDB 单例测试"""

    def setup_method(self):
        """每个测试前重置单例"""
        from engine.agent.db import AgentDB
        AgentDB._instance = None

    def test_init_instance_creates_tables(self, tmp_path):
        """init_instance 应创建所有 6 张表"""
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        # 验证 6 张表存在
        conn = duckdb.connect(str(db_path))
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='agent'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        conn.close()
        db.close()

        expected = {"portfolio_config", "positions", "trades", "position_strategies", "trade_groups", "llm_calls"}
        assert table_names == expected

    def test_get_instance_before_init_raises(self):
        """未初始化时 get_instance 应抛 RuntimeError"""
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        with pytest.raises(RuntimeError, match="not initialized"):
            AgentDB.get_instance()

    def test_singleton_returns_same_instance(self, tmp_path):
        """多次调用 init_instance 返回同一实例"""
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db1 = AgentDB.init_instance()
            db2 = AgentDB.init_instance()
        assert db1 is db2
        db1.close()

    def test_execute_read(self, tmp_path):
        """execute_read 应返回 list[dict]"""
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        rows = run(db.execute_read("SELECT 1 AS val"))
        assert rows == [{"val": 1}]
        db.close()

    def test_execute_write_and_read(self, tmp_path):
        """写入后应能读取"""
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        run(db.execute_write(
            "INSERT INTO agent.portfolio_config (id, mode, initial_capital, cash_balance) VALUES (?, ?, ?, ?)",
            ["live", "live", 1000000.0, 1000000.0]
        ))
        rows = run(db.execute_read("SELECT * FROM agent.portfolio_config WHERE id='live'"))
        assert len(rows) == 1
        assert rows[0]["id"] == "live"
        assert rows[0]["cash_balance"] == 1000000.0
        db.close()

    def test_execute_transaction_rollback(self, tmp_path):
        """事务中出错应回滚"""
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        with pytest.raises(Exception):
            run(db.execute_transaction([
                ("INSERT INTO agent.portfolio_config (id, mode, initial_capital, cash_balance) VALUES (?, ?, ?, ?)",
                 ["live", "live", 1000000.0, 1000000.0]),
                ("INSERT INTO agent.nonexistent_table VALUES (?)", ["boom"]),
            ]))

        # 回滚后应无数据
        rows = run(db.execute_read("SELECT * FROM agent.portfolio_config"))
        assert len(rows) == 0
        db.close()
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.agent'`

- [ ] **Step 4: 实现 AgentDB**

创建 `backend/engine/agent/db.py`：

```python
"""
AgentDB — Main Agent 数据库单例
独立 DuckDB 文件 (data/agent.duckdb)，长连接 + asyncio.Lock 写锁
"""
from __future__ import annotations

import asyncio

import duckdb
from loguru import logger

from config import AGENT_DB_PATH


class AgentDB:
    """Main Agent 数据库 — 单例长连接 + 写锁"""

    _instance: AgentDB | None = None
    _conn: duckdb.DuckDBPyConnection
    _write_lock: asyncio.Lock

    @classmethod
    def get_instance(cls) -> AgentDB:
        if cls._instance is None:
            raise RuntimeError("AgentDB not initialized. Call init_instance() first.")
        return cls._instance

    @classmethod
    def init_instance(cls) -> AgentDB:
        if cls._instance is not None:
            return cls._instance
        inst = cls.__new__(cls)
        inst._conn = duckdb.connect(str(AGENT_DB_PATH))
        inst._write_lock = asyncio.Lock()
        inst._init_tables()
        cls._instance = inst
        logger.info(f"AgentDB 初始化完成: {AGENT_DB_PATH}")
        return inst

    def _init_tables(self):
        """建表（幂等）"""
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS agent")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.portfolio_config (
                id VARCHAR PRIMARY KEY,
                mode VARCHAR NOT NULL DEFAULT 'live',
                initial_capital DOUBLE NOT NULL,
                cash_balance DOUBLE NOT NULL,
                sim_start_date DATE,
                sim_current_date DATE,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.positions (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                direction VARCHAR DEFAULT 'long',
                holding_type VARCHAR NOT NULL,
                entry_price DOUBLE NOT NULL,
                current_qty INTEGER NOT NULL,
                cost_basis DOUBLE NOT NULL,
                entry_date DATE NOT NULL,
                entry_reason TEXT NOT NULL,
                status VARCHAR DEFAULT 'open',
                closed_at TIMESTAMP,
                closed_reason TEXT,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.position_strategies (
                id VARCHAR PRIMARY KEY,
                position_id VARCHAR NOT NULL,
                holding_type VARCHAR NOT NULL,
                take_profit DOUBLE,
                stop_loss DOUBLE,
                reasoning TEXT NOT NULL,
                details JSON,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.trades (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                position_id VARCHAR NOT NULL,
                action VARCHAR NOT NULL,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                price DOUBLE NOT NULL,
                quantity INTEGER NOT NULL,
                amount DOUBLE NOT NULL,
                reason TEXT NOT NULL,
                thesis TEXT NOT NULL,
                data_basis JSON NOT NULL,
                risk_note TEXT NOT NULL,
                invalidation TEXT NOT NULL,
                triggered_by VARCHAR DEFAULT 'agent',
                review_result VARCHAR,
                review_note TEXT,
                review_date TIMESTAMP,
                pnl_at_review DOUBLE,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.trade_groups (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                position_id VARCHAR,
                group_type VARCHAR NOT NULL,
                trade_ids JSON NOT NULL,
                position_ids JSON,
                thesis TEXT NOT NULL,
                planned_duration VARCHAR,
                status VARCHAR DEFAULT 'executing',
                started_at TIMESTAMP DEFAULT now(),
                completed_at TIMESTAMP,
                review_eligible_after DATE,
                review_result VARCHAR,
                review_note TEXT,
                actual_pnl_pct DOUBLE,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.llm_calls (
                id VARCHAR PRIMARY KEY,
                caller VARCHAR NOT NULL,
                model VARCHAR,
                input_tokens INTEGER,
                output_tokens INTEGER,
                call_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT now()
            )
        """)

    async def execute_read(self, sql: str, params=None) -> list[dict]:
        return await asyncio.to_thread(self._sync_read, sql, params)

    def _sync_read(self, sql: str, params=None) -> list[dict]:
        if params:
            result = self._conn.execute(sql, params).fetchdf()
        else:
            result = self._conn.execute(sql).fetchdf()
        return result.to_dict("records")

    async def execute_write(self, sql: str, params=None):
        async with self._write_lock:
            await asyncio.to_thread(self._sync_write, sql, params)

    def _sync_write(self, sql: str, params=None):
        if params:
            self._conn.execute(sql, params)
        else:
            self._conn.execute(sql)

    async def execute_transaction(self, queries: list[tuple[str, list]]):
        async with self._write_lock:
            await asyncio.to_thread(self._sync_transaction, queries)

    def _sync_transaction(self, queries: list[tuple[str, list]]):
        self._conn.begin()
        try:
            for sql, params in queries:
                if params:
                    self._conn.execute(sql, params)
                else:
                    self._conn.execute(sql)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self):
        try:
            self._conn.execute("CHECKPOINT")
        except Exception:
            pass
        self._conn.close()
        AgentDB._instance = None
        logger.info("AgentDB 连接已关闭")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestAgentDB -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backend/engine/agent/__init__.py backend/engine/agent/db.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): AgentDB 单例 + 6 张 DuckDB 表 + 单元测试"
```

---

### Task 3: Pydantic 数据模型 (models.py)

**Files:**
- Create: `backend/engine/agent/models.py`
- Test: `tests/unit/test_agent_phase1a.py` (追加)

- [ ] **Step 1: 写模型的失败测试**

在 `tests/unit/test_agent_phase1a.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 3: Pydantic Models
# ═══════════════════════════════════════════════════════

class TestModels:
    """Pydantic 模型测试"""

    def test_position_defaults(self):
        from engine.agent.models import Position
        p = Position(
            id="pos-1", portfolio_id="live", stock_code="600519",
            stock_name="贵州茅台", holding_type="long_term",
            entry_price=1800.0, current_qty=100, cost_basis=180045.0,
            entry_date="2026-03-20", entry_reason="白酒龙头",
            created_at="2026-03-20T10:00:00",
        )
        assert p.direction == "long"
        assert p.status == "open"
        assert p.closed_at is None

    def test_position_invalid_holding_type(self):
        from engine.agent.models import Position
        with pytest.raises(Exception):
            Position(
                id="pos-1", portfolio_id="live", stock_code="600519",
                stock_name="贵州茅台", holding_type="day_trade",
                entry_price=1800.0, current_qty=100, cost_basis=180045.0,
                entry_date="2026-03-20", entry_reason="test",
                created_at="2026-03-20T10:00:00",
            )

    def test_trade_input_buy_requires_holding_type(self):
        """buy 操作时 holding_type 可以为 None（service 层校验），模型层不强制"""
        from engine.agent.models import TradeInput
        t = TradeInput(
            action="buy", stock_code="600519", price=1800.0, quantity=100,
            reason="test", thesis="test", data_basis=["数据1"],
            risk_note="风险", invalidation="失效条件",
        )
        assert t.holding_type is None

    def test_trade_input_valid(self):
        from engine.agent.models import TradeInput
        t = TradeInput(
            action="buy", stock_code="600519", price=1800.0, quantity=100,
            holding_type="long_term",
            reason="白酒龙头", thesis="消费复苏", data_basis=["营收增长20%"],
            risk_note="估值偏高", invalidation="Q2营收下滑",
        )
        assert t.action == "buy"
        assert t.triggered_by == "agent"

    def test_portfolio_config_defaults(self):
        from engine.agent.models import PortfolioConfig
        pc = PortfolioConfig(
            id="live", mode="live", initial_capital=1000000.0,
            cash_balance=1000000.0, created_at="2026-03-20T10:00:00",
        )
        assert pc.sim_start_date is None

    def test_trade_model(self):
        from engine.agent.models import Trade
        t = Trade(
            id="t-1", position_id="pos-1", portfolio_id="live",
            action="buy", stock_code="600519", stock_name="贵州茅台",
            price=1803.6, quantity=100, amount=180360.0,
            reason="白酒龙头", thesis="消费复苏",
            data_basis=["营收增长20%"], risk_note="估值偏高",
            invalidation="Q2营收下滑", created_at="2026-03-20T10:00:00",
        )
        assert t.review_result is None
        assert t.triggered_by == "agent"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestModels -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.agent.models'`

- [ ] **Step 3: 实现 models.py**

创建 `backend/engine/agent/models.py`：

```python
"""
Main Agent 数据模型
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


# ── 持仓 ──────────────────────────────────────────────

class Position(BaseModel):
    id: str
    portfolio_id: str
    stock_code: str
    stock_name: str
    direction: Literal["long"] = "long"
    holding_type: Literal["long_term", "mid_term", "short_term"]
    entry_price: float
    current_qty: int
    cost_basis: float
    entry_date: str
    entry_reason: str
    status: Literal["open", "closed"] = "open"
    closed_at: str | None = None
    closed_reason: str | None = None
    created_at: str


class PositionStrategy(BaseModel):
    id: str
    position_id: str
    holding_type: str
    take_profit: float | None = None
    stop_loss: float | None = None
    reasoning: str
    details: dict = {}
    version: int = 1
    created_at: str
    updated_at: str


# ── 交易 ──────────────────────────────────────────────

class Trade(BaseModel):
    id: str
    position_id: str
    portfolio_id: str
    action: Literal["buy", "sell", "add", "reduce"]
    stock_code: str
    stock_name: str
    price: float
    quantity: int
    amount: float
    reason: str
    thesis: str
    data_basis: list[str]
    risk_note: str
    invalidation: str
    triggered_by: Literal["manual", "agent"] = "agent"
    created_at: str
    review_result: str | None = None
    review_note: str | None = None
    review_date: str | None = None
    pnl_at_review: float | None = None


class TradeInput(BaseModel):
    """API 入参"""
    action: Literal["buy", "sell", "add", "reduce"]
    stock_code: str
    price: float
    quantity: int
    holding_type: Literal["long_term", "mid_term", "short_term"] | None = None
    reason: str
    thesis: str
    data_basis: list[str]
    risk_note: str
    invalidation: str
    triggered_by: Literal["manual", "agent"] = "agent"


# ── 操作组 ────────────────────────────────────────────

class TradeGroup(BaseModel):
    id: str
    portfolio_id: str
    position_id: str | None = None
    group_type: Literal[
        "build_position", "reduce_position", "close_position",
        "day_trade_session", "rebalance",
    ]
    trade_ids: list[str]
    position_ids: list[str] = []
    thesis: str
    planned_duration: str | None = None
    status: Literal["executing", "completed", "abandoned"] = "executing"
    started_at: str
    completed_at: str | None = None
    review_eligible_after: str | None = None
    review_result: str | None = None
    review_note: str | None = None
    actual_pnl_pct: float | None = None
    created_at: str


# ── 虚拟账户 ──────────────────────────────────────────

class PortfolioConfig(BaseModel):
    id: str
    mode: Literal["live", "training"]
    initial_capital: float
    cash_balance: float
    sim_start_date: str | None = None
    sim_current_date: str | None = None
    created_at: str


class Portfolio(BaseModel):
    """账户概览 — API 返回结构"""
    config: PortfolioConfig
    cash_balance: float
    total_asset: float
    total_pnl: float
    total_pnl_pct: float
    positions: list[Position]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestModels -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/models.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): Pydantic 数据模型 + 单元测试"
```

---

## Chunk 2: TradeValidator (Task 4)

### Task 4: TradeValidator — A股交易规则校验 (validator.py)

**Files:**
- Create: `backend/engine/agent/validator.py`
- Test: `tests/unit/test_agent_phase1a.py` (追加)

- [ ] **Step 1: 写 TradeValidator 的失败测试**

在 `tests/unit/test_agent_phase1a.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 4: TradeValidator
# ═══════════════════════════════════════════════════════

class TestTradeValidator:
    """A股交易规则校验测试"""

    def setup_method(self):
        from engine.agent.validator import TradeValidator
        self.v = TradeValidator()

    # ── 股票代码白名单 ──

    def test_allowed_main_board_sh(self):
        """沪市主板 600/601/603/605 允许"""
        for code in ["600519", "601318", "603288", "605499"]:
            ok, msg = self.v.validate_code(code, "贵州茅台")
            assert ok, f"{code} should be allowed: {msg}"

    def test_allowed_main_board_sz(self):
        """深市主板 000/001/002/003 允许"""
        for code in ["000001", "001289", "002594", "003816"]:
            ok, msg = self.v.validate_code(code, "平安银行")
            assert ok, f"{code} should be allowed: {msg}"

    def test_blocked_chinext(self):
        """创业板 300/301 禁止"""
        ok, msg = self.v.validate_code("300750", "宁德时代")
        assert not ok
        assert "创业板" in msg or "不允许" in msg

    def test_blocked_star(self):
        """科创板 688/689 禁止"""
        ok, msg = self.v.validate_code("688981", "中芯国际")
        assert not ok

    def test_blocked_bse(self):
        """北交所 8xx/4xx 禁止"""
        ok, msg = self.v.validate_code("830799", "艾融软件")
        assert not ok

    def test_blocked_st(self):
        """ST 股票禁止"""
        ok, msg = self.v.validate_code("600000", "ST浦发")
        assert not ok
        assert "ST" in msg

    def test_blocked_star_st(self):
        """*ST 股票禁止"""
        ok, msg = self.v.validate_code("600000", "*ST某某")
        assert not ok

    # ── 交易数量 ──

    def test_lot_size_valid(self):
        """100 的整数倍通过"""
        ok, msg = self.v.validate_quantity(100)
        assert ok
        ok, msg = self.v.validate_quantity(500)
        assert ok

    def test_lot_size_invalid(self):
        """非 100 整数倍拒绝"""
        ok, msg = self.v.validate_quantity(50)
        assert not ok
        ok, msg = self.v.validate_quantity(0)
        assert not ok

    # ── T+1 检查 ──

    def test_t_plus_1_same_day_sell_blocked(self):
        """当天买入不能卖出"""
        ok, msg = self.v.validate_t_plus_1(
            action="sell", entry_date="2026-03-20", trade_date="2026-03-20"
        )
        assert not ok
        assert "T+1" in msg

    def test_t_plus_1_next_day_sell_ok(self):
        """次日可以卖出"""
        ok, msg = self.v.validate_t_plus_1(
            action="sell", entry_date="2026-03-19", trade_date="2026-03-20"
        )
        assert ok

    def test_t_plus_1_buy_always_ok(self):
        """买入不受 T+1 限制"""
        ok, msg = self.v.validate_t_plus_1(
            action="buy", entry_date="2026-03-20", trade_date="2026-03-20"
        )
        assert ok

    # ── 涨跌停检查 ──

    def test_limit_up_cannot_buy(self):
        """涨停不能买入"""
        ok, msg = self.v.validate_limit(action="buy", pct_change=10.0)
        assert not ok
        assert "涨停" in msg

    def test_limit_down_cannot_sell(self):
        """跌停不能卖出"""
        ok, msg = self.v.validate_limit(action="sell", pct_change=-10.0)
        assert not ok
        assert "跌停" in msg

    def test_normal_price_ok(self):
        """正常涨跌幅可以交易"""
        ok, _ = self.v.validate_limit(action="buy", pct_change=5.0)
        assert ok
        ok, _ = self.v.validate_limit(action="sell", pct_change=-5.0)
        assert ok

    # ── 资金/持仓检查 ──

    def test_insufficient_cash(self):
        """资金不足拒绝买入"""
        ok, msg = self.v.validate_cash(
            action="buy", price=100.0, quantity=100, cash=5000.0
        )
        assert not ok
        assert "资金" in msg

    def test_sufficient_cash(self):
        """资金充足通过"""
        ok, _ = self.v.validate_cash(
            action="buy", price=100.0, quantity=100, cash=20000.0
        )
        assert ok

    def test_sell_no_cash_check(self):
        """卖出不检查资金"""
        ok, _ = self.v.validate_cash(
            action="sell", price=100.0, quantity=100, cash=0.0
        )
        assert ok

    def test_insufficient_position(self):
        """持仓不足拒绝卖出"""
        ok, msg = self.v.validate_position_qty(
            action="sell", current_qty=100, sell_qty=200
        )
        assert not ok
        assert "持仓" in msg

    def test_sufficient_position(self):
        """持仓充足通过"""
        ok, _ = self.v.validate_position_qty(
            action="sell", current_qty=200, sell_qty=100
        )
        assert ok

    # ── 滑点 & 手续费 ──

    def test_slippage_buy(self):
        """买入滑点 +0.2%"""
        price = self.v.apply_slippage("buy", 100.0)
        assert abs(price - 100.2) < 0.01

    def test_slippage_sell(self):
        """卖出滑点 -0.2%"""
        price = self.v.apply_slippage("sell", 100.0)
        assert abs(price - 99.8) < 0.01

    def test_fee_buy_sh(self):
        """沪市买入手续费: 佣金(万2.5) + 过户费(十万分之1)"""
        fee = self.v.calc_fee(action="buy", price=100.0, quantity=100, stock_code="600519")
        commission = 100.0 * 100 * 0.00025  # 2.5 元
        transfer = 100.0 * 100 * 0.00001    # 0.1 元
        # 佣金不足5元按5元
        expected = 5.0 + transfer
        assert abs(fee - expected) < 0.01

    def test_fee_sell_sh(self):
        """沪市卖出手续费: 佣金 + 印花税(千1) + 过户费"""
        fee = self.v.calc_fee(action="sell", price=100.0, quantity=1000, stock_code="601318")
        amount = 100.0 * 1000
        commission = amount * 0.00025  # 25 元
        stamp = amount * 0.001         # 100 元
        transfer = amount * 0.00001    # 1 元
        expected = commission + stamp + transfer
        assert abs(fee - expected) < 0.01

    def test_fee_sell_sz(self):
        """深市卖出: 无过户费"""
        fee = self.v.calc_fee(action="sell", price=50.0, quantity=1000, stock_code="000001")
        amount = 50.0 * 1000
        commission = amount * 0.00025  # 12.5 元
        stamp = amount * 0.001         # 50 元
        # 深市无过户费
        expected = commission + stamp
        assert abs(fee - expected) < 0.01

    def test_fee_min_commission(self):
        """佣金不足5元按5元"""
        fee = self.v.calc_fee(action="buy", price=10.0, quantity=100, stock_code="000001")
        # 10*100*0.00025 = 0.25 → 按5元
        assert fee >= 5.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestTradeValidator -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.agent.validator'`

- [ ] **Step 3: 实现 TradeValidator**

创建 `backend/engine/agent/validator.py`：

```python
"""
TradeValidator — A股虚拟盘交易规则校验
"""
from __future__ import annotations


class TradeValidator:
    """虚拟盘交易规则校验"""

    # 允许交易的股票代码前缀（沪深主板）
    ALLOWED_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")

    # 禁止交易的代码前缀
    BLOCKED_PREFIXES = ("300", "301", "688", "689", "8", "4")

    # 主板涨跌停幅度
    LIMIT_PCT = 10.0

    # 滑点
    SLIPPAGE_BUY = 0.002   # +0.2%
    SLIPPAGE_SELL = 0.002  # -0.2%

    # 手续费
    COMMISSION_RATE = 0.00025   # 万2.5
    MIN_COMMISSION = 5.0        # 最低佣金 5 元
    STAMP_TAX_RATE = 0.001      # 印花税 千1（仅卖出）
    TRANSFER_FEE_RATE = 0.00001 # 过户费 十万分之1（仅沪市）

    def validate_code(self, stock_code: str, stock_name: str) -> tuple[bool, str]:
        """校验股票代码白名单 + ST 检查"""
        # ST 检查
        if "ST" in stock_name.upper():
            return False, f"禁止交易 ST 股票: {stock_name}"

        # 黑名单优先
        for prefix in self.BLOCKED_PREFIXES:
            if stock_code.startswith(prefix):
                board = {
                    "300": "创业板", "301": "创业板",
                    "688": "科创板", "689": "科创板",
                    "8": "北交所", "4": "北交所/三板",
                }.get(prefix, "非主板")
                return False, f"不允许交易{board}股票: {stock_code}"

        # 白名单
        if not stock_code.startswith(self.ALLOWED_PREFIXES):
            return False, f"股票代码不在允许范围内: {stock_code}"

        return True, ""

    def validate_quantity(self, quantity: int) -> tuple[bool, str]:
        """校验交易数量（100 的整数倍，且 > 0）"""
        if quantity <= 0:
            return False, "交易数量必须大于 0"
        if quantity % 100 != 0:
            return False, f"交易数量必须是 100 的整数倍，当前: {quantity}"
        return True, ""

    def validate_t_plus_1(
        self, action: str, entry_date: str, trade_date: str
    ) -> tuple[bool, str]:
        """T+1 检查：sell/reduce 时持仓必须是昨天或更早买入的"""
        if action in ("buy", "add"):
            return True, ""
        if entry_date >= trade_date:
            return False, f"T+1 限制: 持仓买入日 {entry_date}，不能在 {trade_date} 卖出"
        return True, ""

    def validate_limit(
        self, action: str, pct_change: float
    ) -> tuple[bool, str]:
        """涨跌停检查"""
        if action in ("buy", "add") and pct_change >= self.LIMIT_PCT:
            return False, f"涨停({pct_change:.1f}%)不能买入"
        if action in ("sell", "reduce") and pct_change <= -self.LIMIT_PCT:
            return False, f"跌停({pct_change:.1f}%)不能卖出"
        return True, ""

    def validate_cash(
        self, action: str, price: float, quantity: int, cash: float
    ) -> tuple[bool, str]:
        """资金充足检查（仅买入）"""
        if action in ("sell", "reduce"):
            return True, ""
        needed = price * quantity
        if cash < needed:
            return False, f"资金不足: 需要 {needed:.2f}，可用 {cash:.2f}"
        return True, ""

    def validate_position_qty(
        self, action: str, current_qty: int, sell_qty: int
    ) -> tuple[bool, str]:
        """持仓充足检查（仅卖出）"""
        if action in ("buy", "add"):
            return True, ""
        if current_qty < sell_qty:
            return False, f"持仓不足: 持有 {current_qty}，卖出 {sell_qty}"
        return True, ""

    def apply_slippage(self, action: str, price: float) -> float:
        """计算含滑点的成交价"""
        if action in ("buy", "add"):
            return round(price * (1 + self.SLIPPAGE_BUY), 2)
        return round(price * (1 - self.SLIPPAGE_SELL), 2)

    def calc_fee(
        self, action: str, price: float, quantity: int, stock_code: str
    ) -> float:
        """计算手续费"""
        amount = price * quantity

        # 佣金（买卖双向）
        commission = max(amount * self.COMMISSION_RATE, self.MIN_COMMISSION)

        # 印花税（仅卖出）
        stamp = amount * self.STAMP_TAX_RATE if action in ("sell", "reduce") else 0.0

        # 过户费（仅沪市 6 开头）
        transfer = amount * self.TRANSFER_FEE_RATE if stock_code.startswith("6") else 0.0

        return round(commission + stamp + transfer, 2)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestTradeValidator -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/validator.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): TradeValidator A股交易规则校验 + 单元测试"
```

---

## Chunk 3: Service 层 (Task 5-7)

### Task 5: Service 层 — Portfolio CRUD (service.py)

**Files:**
- Create: `backend/engine/agent/service.py`
- Test: `tests/unit/test_agent_phase1a.py` (追加)

- [ ] **Step 1: 写 Portfolio CRUD 的失败测试**

在 `tests/unit/test_agent_phase1a.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 5: AgentService — Portfolio CRUD
# ═══════════════════════════════════════════════════════

class TestServicePortfolio:
    """AgentService 账户管理测试"""

    def setup_method(self):
        """每个测试创建独立 DB + Service"""
        import tempfile
        self._tmp = tempfile.mkdtemp()
        db_path = Path(self._tmp) / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            self.db = AgentDB.init_instance()
        from engine.agent.validator import TradeValidator
        from engine.agent.service import AgentService
        self.svc = AgentService(db=self.db, validator=TradeValidator())

    def teardown_method(self):
        self.db.close()

    def test_create_live_portfolio(self):
        result = run(self.svc.create_portfolio("live", "live", 1000000.0))
        assert result["id"] == "live"
        assert result["cash_balance"] == 1000000.0

    def test_create_training_portfolio(self):
        result = run(self.svc.create_portfolio(
            "train_01", "training", 500000.0, sim_start_date="2025-01-02"
        ))
        assert result["mode"] == "training"
        assert result["sim_start_date"] is not None

    def test_duplicate_portfolio_raises(self):
        run(self.svc.create_portfolio("live", "live", 1000000.0))
        with pytest.raises(ValueError, match="已存在"):
            run(self.svc.create_portfolio("live", "live", 1000000.0))

    def test_duplicate_live_raises(self):
        """只能有一个 live 账户"""
        run(self.svc.create_portfolio("live", "live", 1000000.0))
        with pytest.raises(ValueError, match="live"):
            run(self.svc.create_portfolio("live2", "live", 500000.0))

    def test_list_portfolios(self):
        run(self.svc.create_portfolio("live", "live", 1000000.0))
        run(self.svc.create_portfolio("train_01", "training", 500000.0))
        result = run(self.svc.list_portfolios())
        assert len(result) == 2

    def test_get_portfolio(self):
        run(self.svc.create_portfolio("live", "live", 1000000.0))
        result = run(self.svc.get_portfolio("live"))
        assert result["config"]["id"] == "live"
        assert result["cash_balance"] == 1000000.0
        assert result["total_asset"] == 1000000.0
        assert result["positions"] == []

    def test_get_nonexistent_portfolio(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_portfolio("nonexistent"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestServicePortfolio -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.agent.service'`

- [ ] **Step 3: 实现 AgentService — Portfolio CRUD 部分**

创建 `backend/engine/agent/service.py`：

```python
"""
AgentService — Main Agent 业务逻辑层
"""
from __future__ import annotations

import uuid
from datetime import datetime

from loguru import logger

from engine.agent.db import AgentDB
from engine.agent.models import TradeInput
from engine.agent.validator import TradeValidator


class AgentService:
    """Main Agent 业务逻辑"""

    def __init__(self, db: AgentDB, validator: TradeValidator):
        self.db = db
        self.validator = validator

    # ── Portfolio CRUD ────────────────────────────────

    async def create_portfolio(
        self,
        portfolio_id: str,
        mode: str,
        initial_capital: float,
        sim_start_date: str | None = None,
    ) -> dict:
        """创建虚拟账户"""
        # 检查重复
        existing = await self.db.execute_read(
            "SELECT id FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if existing:
            raise ValueError(f"账户 {portfolio_id} 已存在")

        # live 只能有一个
        if mode == "live":
            lives = await self.db.execute_read(
                "SELECT id FROM agent.portfolio_config WHERE mode = 'live'"
            )
            if lives:
                raise ValueError(f"live 账户已存在: {lives[0]['id']}，不能重复创建")

        now = datetime.now().isoformat()
        await self.db.execute_write(
            """INSERT INTO agent.portfolio_config
               (id, mode, initial_capital, cash_balance, sim_start_date, sim_current_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [portfolio_id, mode, initial_capital, initial_capital,
             sim_start_date, sim_start_date, now],
        )
        logger.info(f"创建账户: {portfolio_id} ({mode}), 初始资金: {initial_capital}")
        rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        return rows[0]

    async def list_portfolios(self) -> list[dict]:
        """列出所有账户"""
        return await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config ORDER BY created_at"
        )

    async def get_portfolio(self, portfolio_id: str) -> dict:
        """获取账户概览"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if not rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")
        config = rows[0]

        positions = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE portfolio_id = ? AND status = 'open'",
            [portfolio_id],
        )

        cash = config["cash_balance"]
        # TODO: Phase 1B — 调用 DataEngine 获取实时价格计算持仓市值
        position_value = sum(p["entry_price"] * p["current_qty"] for p in positions)
        total_asset = cash + position_value
        total_pnl = total_asset - config["initial_capital"]
        total_pnl_pct = (total_pnl / config["initial_capital"] * 100) if config["initial_capital"] > 0 else 0.0

        return {
            "config": config,
            "cash_balance": cash,
            "total_asset": round(total_asset, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "positions": positions,
        }

    async def get_positions(
        self, portfolio_id: str, status: str = "open"
    ) -> list[dict]:
        """持仓列表"""
        return await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE portfolio_id = ? AND status = ?",
            [portfolio_id, status],
        )

    async def get_position(self, portfolio_id: str, position_id: str) -> dict:
        """单个持仓详情（含策略 + 交易记录）"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
            [position_id, portfolio_id],
        )
        if not rows:
            raise ValueError(f"持仓 {position_id} 不存在")
        position = rows[0]

        strategies = await self.db.execute_read(
            "SELECT * FROM agent.position_strategies WHERE position_id = ? ORDER BY version DESC",
            [position_id],
        )
        trades = await self.db.execute_read(
            "SELECT * FROM agent.trades WHERE position_id = ? ORDER BY created_at DESC",
            [position_id],
        )
        position["strategies"] = strategies
        position["trades"] = trades
        return position

    async def get_trades(
        self, portfolio_id: str, position_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """交易记录"""
        if position_id:
            return await self.db.execute_read(
                "SELECT * FROM agent.trades WHERE portfolio_id = ? AND position_id = ? ORDER BY created_at DESC LIMIT ?",
                [portfolio_id, position_id, limit],
            )
        return await self.db.execute_read(
            "SELECT * FROM agent.trades WHERE portfolio_id = ? ORDER BY created_at DESC LIMIT ?",
            [portfolio_id, limit],
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestServicePortfolio -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): AgentService Portfolio CRUD + 单元测试"
```

### Task 6: Service 层 — execute_trade (service.py 追加)

**Files:**
- Modify: `backend/engine/agent/service.py`
- Test: `tests/unit/test_agent_phase1a.py` (追加)

- [ ] **Step 1: 写 execute_trade 的失败测试**

在 `tests/unit/test_agent_phase1a.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 6: AgentService — execute_trade
# ═══════════════════════════════════════════════════════

class TestServiceTrade:
    """AgentService 交易执行测试"""

    def setup_method(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        db_path = Path(self._tmp) / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            self.db = AgentDB.init_instance()
        from engine.agent.validator import TradeValidator
        from engine.agent.service import AgentService
        self.svc = AgentService(db=self.db, validator=TradeValidator())
        # 创建测试账户
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def _make_trade_input(self, **overrides):
        from engine.agent.models import TradeInput
        defaults = dict(
            action="buy", stock_code="600519", price=1800.0, quantity=100,
            holding_type="long_term",
            reason="白酒龙头", thesis="消费复苏",
            data_basis=["营收增长20%"], risk_note="估值偏高",
            invalidation="Q2营收下滑",
        )
        defaults.update(overrides)
        return TradeInput(**defaults)

    def test_buy_creates_position_and_trade(self):
        """买入应创建持仓和交易记录"""
        ti = self._make_trade_input()
        result = run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        assert result["trade"]["action"] == "buy"
        assert result["trade"]["position_id"] is not None
        assert result["position"]["current_qty"] == 100
        assert result["position"]["status"] == "open"
        # 现金应减少
        portfolio = run(self.svc.get_portfolio("live"))
        assert portfolio["cash_balance"] < 1000000.0

    def test_buy_slippage_applied(self):
        """买入价应含 +0.2% 滑点"""
        ti = self._make_trade_input(price=1000.0, quantity=100)
        result = run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        assert result["trade"]["price"] == 1002.0  # 1000 * 1.002

    def test_buy_fee_deducted(self):
        """手续费应从现金中扣除"""
        ti = self._make_trade_input(price=1000.0, quantity=100)
        result = run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        portfolio = run(self.svc.get_portfolio("live"))
        # 成交额 = 1002 * 100 = 100200
        # 佣金 = max(100200 * 0.00025, 5) = 25.05
        # 过户费 = 100200 * 0.00001 = 1.002 ≈ 1.0
        # 总扣款 = 100200 + 25.05 + 1.0 = 100226.05
        assert portfolio["cash_balance"] < 1000000.0 - 100200

    def test_buy_blocked_code(self):
        """创业板代码应被拒绝"""
        ti = self._make_trade_input(stock_code="300750")
        with pytest.raises(ValueError, match="不允许"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))

    def test_buy_invalid_lot_size(self):
        """非100整数倍应被拒绝"""
        ti = self._make_trade_input(quantity=50)
        with pytest.raises(ValueError, match="100"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))

    def test_buy_insufficient_cash(self):
        """资金不足应被拒绝"""
        ti = self._make_trade_input(price=50000.0, quantity=100)
        # 50000 * 100 = 5000000 > 1000000
        with pytest.raises(ValueError, match="资金"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))

    def test_add_position(self):
        """加仓应更新均价和数量"""
        ti_buy = self._make_trade_input(price=1000.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-20"))
        pos_id = r1["position"]["id"]

        ti_add = self._make_trade_input(
            action="add", price=1100.0, quantity=100,
            stock_code="600519",
        )
        r2 = run(self.svc.execute_trade(
            "live", ti_add, trade_date="2026-03-21", position_id=pos_id
        ))
        assert r2["position"]["current_qty"] == 200
        # 均价应在 1000-1100 之间（含滑点）
        assert 1000.0 < r2["position"]["entry_price"] < 1200.0

    def test_sell_reduces_qty(self):
        """卖出应减少持仓数量"""
        ti_buy = self._make_trade_input(price=100.0, quantity=200)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-19"))
        pos_id = r1["position"]["id"]

        ti_sell = self._make_trade_input(
            action="sell", price=110.0, quantity=100,
            stock_code="600519",
        )
        r2 = run(self.svc.execute_trade(
            "live", ti_sell, trade_date="2026-03-20", position_id=pos_id
        ))
        assert r2["position"]["current_qty"] == 100
        assert r2["position"]["status"] == "open"

    def test_sell_all_closes_position(self):
        """全部卖出应关闭持仓"""
        ti_buy = self._make_trade_input(price=100.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-19"))
        pos_id = r1["position"]["id"]

        ti_sell = self._make_trade_input(
            action="sell", price=110.0, quantity=100,
            stock_code="600519",
        )
        r2 = run(self.svc.execute_trade(
            "live", ti_sell, trade_date="2026-03-20", position_id=pos_id
        ))
        assert r2["position"]["current_qty"] == 0
        assert r2["position"]["status"] == "closed"

    def test_sell_t_plus_1_blocked(self):
        """当天买入当天卖出应被 T+1 拒绝"""
        ti_buy = self._make_trade_input(price=100.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-20"))
        pos_id = r1["position"]["id"]

        ti_sell = self._make_trade_input(
            action="sell", price=110.0, quantity=100,
            stock_code="600519",
        )
        with pytest.raises(ValueError, match="T\\+1"):
            run(self.svc.execute_trade(
                "live", ti_sell, trade_date="2026-03-20", position_id=pos_id
            ))

    def test_sell_cash_increases(self):
        """卖出后现金应增加"""
        ti_buy = self._make_trade_input(price=100.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-19"))
        pos_id = r1["position"]["id"]
        cash_after_buy = run(self.svc.get_portfolio("live"))["cash_balance"]

        ti_sell = self._make_trade_input(
            action="sell", price=110.0, quantity=100,
            stock_code="600519",
        )
        run(self.svc.execute_trade(
            "live", ti_sell, trade_date="2026-03-20", position_id=pos_id
        ))
        cash_after_sell = run(self.svc.get_portfolio("live"))["cash_balance"]
        assert cash_after_sell > cash_after_buy

    def test_buy_requires_holding_type(self):
        """buy 操作必须指定 holding_type"""
        ti = self._make_trade_input(holding_type=None)
        with pytest.raises(ValueError, match="holding_type"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestServiceTrade -v`
Expected: FAIL — `AttributeError: 'AgentService' object has no attribute 'execute_trade'`

- [ ] **Step 3: 在 service.py 中追加 execute_trade 方法**

在 `AgentService` 类末尾追加：

```python
    # ── Trade Execution ───────────────────────────────

    async def execute_trade(
        self,
        portfolio_id: str,
        trade_input: TradeInput,
        trade_date: str,
        position_id: str | None = None,
        stock_name: str | None = None,
    ) -> dict:
        """
        执行交易 — 核心方法

        Args:
            portfolio_id: 账户 ID
            trade_input: 交易入参
            trade_date: 交易日期 YYYY-MM-DD（live 模式传当天，training 传模拟日期）
            position_id: add/sell/reduce 时指定持仓 ID
            stock_name: 股票名称（可选，未传时用 stock_code 占位，Phase 1B 接 DataEngine）
        """
        action = trade_input.action
        code = trade_input.stock_code
        name = stock_name or code  # Phase 1B: DataEngine.get_profiles() 解析

        # ── 1. 校验股票代码 ──
        ok, msg = self.validator.validate_code(code, name)
        if not ok:
            raise ValueError(msg)

        # ── 2. 校验数量 ──
        ok, msg = self.validator.validate_quantity(trade_input.quantity)
        if not ok:
            raise ValueError(msg)

        # ── 3. 获取账户 ──
        portfolio_rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if not portfolio_rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")
        portfolio = portfolio_rows[0]
        cash = portfolio["cash_balance"]

        # ── 4. 计算成交价（含滑点）──
        exec_price = self.validator.apply_slippage(action, trade_input.price)
        amount = exec_price * trade_input.quantity
        fee = self.validator.calc_fee(action, exec_price, trade_input.quantity, code)

        # ── 5. 按操作类型处理 ──
        position = None
        if action == "buy":
            if not trade_input.holding_type:
                raise ValueError("buy 操作必须指定 holding_type")

            # 资金检查
            ok, msg = self.validator.validate_cash(action, exec_price, trade_input.quantity, cash)
            if not ok:
                raise ValueError(msg)

            # 创建持仓
            pos_id = str(uuid.uuid4())
            cost_basis = amount + fee
            now = datetime.now().isoformat()

            queries = [
                (
                    """INSERT INTO agent.positions
                       (id, portfolio_id, stock_code, stock_name, direction, holding_type,
                        entry_price, current_qty, cost_basis, entry_date, entry_reason, status, created_at)
                       VALUES (?, ?, ?, ?, 'long', ?, ?, ?, ?, ?, ?, 'open', ?)""",
                    [pos_id, portfolio_id, code, name, trade_input.holding_type,
                     exec_price, trade_input.quantity, cost_basis, trade_date,
                     trade_input.reason, now],
                ),
                self._insert_trade_sql(
                    portfolio_id, pos_id, trade_input, exec_price, amount, name, now
                ),
                (
                    "UPDATE agent.portfolio_config SET cash_balance = cash_balance - ? WHERE id = ?",
                    [cost_basis, portfolio_id],
                ),
            ]
            await self.db.execute_transaction(queries)
            position_id = pos_id

        elif action == "add":
            if not position_id:
                raise ValueError("add 操作必须指定 position_id")

            pos_rows = await self.db.execute_read(
                "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
                [position_id, portfolio_id],
            )
            if not pos_rows:
                raise ValueError(f"持仓 {position_id} 不存在")
            position = pos_rows[0]

            ok, msg = self.validator.validate_cash(action, exec_price, trade_input.quantity, cash)
            if not ok:
                raise ValueError(msg)

            # 重算均价
            old_qty = position["current_qty"]
            old_cost = position["cost_basis"]
            new_cost = amount + fee
            total_qty = old_qty + trade_input.quantity
            total_cost = old_cost + new_cost
            new_avg_price = total_cost / total_qty

            now = datetime.now().isoformat()
            queries = [
                (
                    """UPDATE agent.positions
                       SET entry_price = ?, current_qty = ?, cost_basis = ?
                       WHERE id = ?""",
                    [round(new_avg_price, 4), total_qty, round(total_cost, 2), position_id],
                ),
                self._insert_trade_sql(
                    portfolio_id, position_id, trade_input, exec_price, amount, name, now
                ),
                (
                    "UPDATE agent.portfolio_config SET cash_balance = cash_balance - ? WHERE id = ?",
                    [new_cost, portfolio_id],
                ),
            ]
            await self.db.execute_transaction(queries)

        elif action in ("sell", "reduce"):
            if not position_id:
                raise ValueError(f"{action} 操作必须指定 position_id")

            pos_rows = await self.db.execute_read(
                "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
                [position_id, portfolio_id],
            )
            if not pos_rows:
                raise ValueError(f"持仓 {position_id} 不存在")
            position = pos_rows[0]

            # T+1 检查
            ok, msg = self.validator.validate_t_plus_1(action, position["entry_date"], trade_date)
            if not ok:
                raise ValueError(msg)

            # 持仓充足检查
            ok, msg = self.validator.validate_position_qty(action, position["current_qty"], trade_input.quantity)
            if not ok:
                raise ValueError(msg)

            new_qty = position["current_qty"] - trade_input.quantity
            proceeds = amount - fee  # 卖出所得 = 成交额 - 手续费
            now = datetime.now().isoformat()

            queries = [
                self._insert_trade_sql(
                    portfolio_id, position_id, trade_input, exec_price, amount, name, now
                ),
                (
                    "UPDATE agent.portfolio_config SET cash_balance = cash_balance + ? WHERE id = ?",
                    [proceeds, portfolio_id],
                ),
            ]

            if new_qty == 0:
                queries.append((
                    "UPDATE agent.positions SET current_qty = 0, status = 'closed', closed_at = ?, closed_reason = ? WHERE id = ?",
                    [now, trade_input.reason, position_id],
                ))
            else:
                queries.append((
                    "UPDATE agent.positions SET current_qty = ? WHERE id = ?",
                    [new_qty, position_id],
                ))

            await self.db.execute_transaction(queries)

        # ── 6. 返回结果 ──
        pos_rows = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE id = ?", [position_id]
        )
        trade_rows = await self.db.execute_read(
            "SELECT * FROM agent.trades WHERE position_id = ? ORDER BY created_at DESC LIMIT 1",
            [position_id],
        )

        return {
            "position": pos_rows[0] if pos_rows else None,
            "trade": trade_rows[0] if trade_rows else None,
            "fee": fee,
            "exec_price": exec_price,
        }

    def _insert_trade_sql(
        self, portfolio_id, position_id, ti: TradeInput,
        exec_price, amount, stock_name, now,
    ) -> tuple[str, list]:
        """生成 INSERT trade 的 SQL + params"""
        import json
        trade_id = str(uuid.uuid4())
        return (
            """INSERT INTO agent.trades
               (id, portfolio_id, position_id, action, stock_code, stock_name,
                price, quantity, amount, reason, thesis, data_basis,
                risk_note, invalidation, triggered_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [trade_id, portfolio_id, position_id, ti.action, ti.stock_code,
             stock_name, exec_price, ti.quantity, round(amount, 2),
             ti.reason, ti.thesis, json.dumps(ti.data_basis, ensure_ascii=False),
             ti.risk_note, ti.invalidation, ti.triggered_by, now],
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestServiceTrade -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): execute_trade 交易执行 + 滑点/手续费/T+1 + 单元测试"
```

### Task 7: Service 层 — Strategy CRUD (service.py 追加)

**Files:**
- Modify: `backend/engine/agent/service.py`
- Test: `tests/unit/test_agent_phase1a.py` (追加)

- [ ] **Step 1: 写 Strategy CRUD 的失败测试**

在 `tests/unit/test_agent_phase1a.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 7: AgentService — Strategy CRUD
# ═══════════════════════════════════════════════════════

class TestServiceStrategy:
    """AgentService 策略管理测试"""

    def setup_method(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        db_path = Path(self._tmp) / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            self.db = AgentDB.init_instance()
        from engine.agent.validator import TradeValidator
        from engine.agent.service import AgentService
        from engine.agent.models import TradeInput
        self.svc = AgentService(db=self.db, validator=TradeValidator())
        # 创建账户 + 买入一个持仓
        run(self.svc.create_portfolio("live", "live", 1000000.0))
        ti = TradeInput(
            action="buy", stock_code="600519", price=1800.0, quantity=100,
            holding_type="long_term",
            reason="白酒龙头", thesis="消费复苏",
            data_basis=["营收增长20%"], risk_note="估值偏高",
            invalidation="Q2营收下滑",
        )
        result = run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        self.pos_id = result["position"]["id"]

    def teardown_method(self):
        self.db.close()

    def test_create_strategy(self):
        """创建策略"""
        result = run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2200.0,
            "stop_loss": 1600.0,
            "reasoning": "白酒龙头长期持有，止盈止损明确",
            "details": {"fundamental_anchor": "硅料产能出清"},
        }))
        assert result["position_id"] == self.pos_id
        assert result["version"] == 1
        assert result["take_profit"] == 2200.0

    def test_update_strategy_increments_version(self):
        """更新策略 version 自增"""
        run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2200.0,
            "stop_loss": 1600.0,
            "reasoning": "初始策略",
        }))
        result = run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2500.0,
            "stop_loss": 1500.0,
            "reasoning": "上调止盈",
        }))
        assert result["version"] == 2

    def test_get_strategy(self):
        """获取策略（含历史版本）"""
        run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2200.0, "stop_loss": 1600.0, "reasoning": "v1",
        }))
        run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2500.0, "stop_loss": 1500.0, "reasoning": "v2",
        }))
        result = run(self.svc.get_strategy("live", self.pos_id))
        assert len(result) == 2
        assert result[0]["version"] == 2  # 最新在前

    def test_create_strategy_nonexistent_position(self):
        """不存在的持仓应报错"""
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.create_strategy("live", "nonexistent", {
                "take_profit": 2200.0, "stop_loss": 1600.0, "reasoning": "test",
            }))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestServiceStrategy -v`
Expected: FAIL — `AttributeError: 'AgentService' object has no attribute 'create_strategy'`

- [ ] **Step 3: 在 service.py 中追加 Strategy 方法**

在 `AgentService` 类末尾追加：

```python
    # ── Strategy CRUD ─────────────────────────────────

    async def create_strategy(
        self, portfolio_id: str, position_id: str, strategy_input: dict
    ) -> dict:
        """创建/更新持仓策略（version 自增）"""
        # 验证持仓存在
        pos_rows = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
            [position_id, portfolio_id],
        )
        if not pos_rows:
            raise ValueError(f"持仓 {position_id} 不存在")
        position = pos_rows[0]

        # 查询当前最大 version
        existing = await self.db.execute_read(
            "SELECT MAX(version) as max_ver FROM agent.position_strategies WHERE position_id = ?",
            [position_id],
        )
        max_ver = existing[0]["max_ver"] if existing and existing[0]["max_ver"] is not None else 0
        new_version = max_ver + 1

        import json
        strategy_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        details = strategy_input.get("details", {})

        await self.db.execute_write(
            """INSERT INTO agent.position_strategies
               (id, position_id, holding_type, take_profit, stop_loss,
                reasoning, details, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [strategy_id, position_id, position["holding_type"],
             strategy_input.get("take_profit"), strategy_input.get("stop_loss"),
             strategy_input.get("reasoning", ""),
             json.dumps(details, ensure_ascii=False) if details else None,
             new_version, now, now],
        )

        rows = await self.db.execute_read(
            "SELECT * FROM agent.position_strategies WHERE id = ?", [strategy_id]
        )
        return rows[0]

    async def get_strategy(
        self, portfolio_id: str, position_id: str
    ) -> list[dict]:
        """获取持仓策略（含历史版本，最新在前）"""
        # 验证持仓存在
        pos_rows = await self.db.execute_read(
            "SELECT id FROM agent.positions WHERE id = ? AND portfolio_id = ?",
            [position_id, portfolio_id],
        )
        if not pos_rows:
            raise ValueError(f"持仓 {position_id} 不存在")

        return await self.db.execute_read(
            "SELECT * FROM agent.position_strategies WHERE position_id = ? ORDER BY version DESC",
            [position_id],
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestServiceStrategy -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): Strategy CRUD + version 自增 + 单元测试"
```

## Chunk 4: Routes + Integration (Task 8-9)

### Task 8: FastAPI 路由 (routes.py)

**Files:**
- Create: `backend/engine/agent/routes.py`
- Test: `tests/unit/test_agent_phase1a.py` (追加)

- [ ] **Step 1: 写路由的失败测试**

在 `tests/unit/test_agent_phase1a.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 8: FastAPI Routes
# ═══════════════════════════════════════════════════════
from fastapi import FastAPI
from fastapi.testclient import TestClient

def _create_test_app(tmp_path):
    """创建带 AgentDB 的测试 FastAPI app"""
    db_path = tmp_path / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        db = AgentDB.init_instance()

    from engine.agent.routes import create_agent_router
    app = FastAPI()
    router = create_agent_router()
    app.include_router(router, prefix="/api/v1/agent")
    return app, db


class TestRoutes:
    """FastAPI 路由测试"""

    def setup_method(self, tmp_path=None):
        import tempfile
        self._tmp_dir = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(Path(self._tmp_dir))
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    # ── Portfolio ──

    def test_create_portfolio(self):
        resp = self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == "live"

    def test_create_duplicate_portfolio_409(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        resp = self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        assert resp.status_code == 409

    def test_list_portfolios(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        resp = self.client.get("/api/v1/agent/portfolio")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_portfolio(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        resp = self.client.get("/api/v1/agent/portfolio/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cash_balance"] == 1000000.0
        assert data["total_asset"] == 1000000.0

    def test_get_nonexistent_portfolio_404(self):
        resp = self.client.get("/api/v1/agent/portfolio/nonexistent")
        assert resp.status_code == 404

    # ── Positions ──

    def test_get_positions_empty(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        resp = self.client.get("/api/v1/agent/portfolio/live/positions")
        assert resp.status_code == 200
        assert resp.json() == []

    # ── Trades ──

    def test_execute_trade_buy(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        resp = self.client.post("/api/v1/agent/portfolio/live/trades", json={
            "action": "buy", "stock_code": "600519", "price": 1800.0,
            "quantity": 100, "holding_type": "long_term",
            "reason": "白酒龙头", "thesis": "消费复苏",
            "data_basis": ["营收增长20%"], "risk_note": "估值偏高",
            "invalidation": "Q2营收下滑",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["trade"]["action"] == "buy"
        assert data["position"]["status"] == "open"

    def test_execute_trade_blocked_code_400(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        resp = self.client.post("/api/v1/agent/portfolio/live/trades", json={
            "action": "buy", "stock_code": "300750", "price": 200.0,
            "quantity": 100, "holding_type": "short_term",
            "reason": "test", "thesis": "test",
            "data_basis": ["test"], "risk_note": "test",
            "invalidation": "test",
        })
        assert resp.status_code == 400
        assert "不允许" in resp.json()["detail"]

    # ── Strategy ──

    def test_create_and_get_strategy(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "live", "mode": "live", "initial_capital": 1000000.0,
        })
        # 先买入
        buy_resp = self.client.post("/api/v1/agent/portfolio/live/trades", json={
            "action": "buy", "stock_code": "600519", "price": 1800.0,
            "quantity": 100, "holding_type": "long_term",
            "reason": "白酒龙头", "thesis": "消费复苏",
            "data_basis": ["营收增长20%"], "risk_note": "估值偏高",
            "invalidation": "Q2营收下滑",
        })
        pos_id = buy_resp.json()["position"]["id"]

        # 创建策略
        resp = self.client.post(
            f"/api/v1/agent/portfolio/live/positions/{pos_id}/strategy",
            json={
                "take_profit": 2200.0, "stop_loss": 1600.0,
                "reasoning": "长期持有策略",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

        # 获取策略
        resp = self.client.get(
            f"/api/v1/agent/portfolio/live/positions/{pos_id}/strategy"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestRoutes -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.agent.routes'`

- [ ] **Step 3: 实现 routes.py**

创建 `backend/engine/agent/routes.py`：

```python
"""
Main Agent FastAPI 路由
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from engine.agent.db import AgentDB
from engine.agent.models import TradeInput
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator


# ── 请求模型 ──────────────────────────────────────────

class CreatePortfolioRequest(BaseModel):
    id: str
    mode: str = "live"
    initial_capital: float
    sim_start_date: str | None = None


class CreateStrategyRequest(BaseModel):
    take_profit: float | None = None
    stop_loss: float | None = None
    reasoning: str = ""
    details: dict = {}


# ── 路由工厂 ──────────────────────────────────────────

def create_agent_router() -> APIRouter:
    router = APIRouter(tags=["agent"])

    def _get_service() -> AgentService:
        db = AgentDB.get_instance()
        return AgentService(db=db, validator=TradeValidator())

    # ── Portfolio ──

    @router.post("/portfolio")
    async def create_portfolio(req: CreatePortfolioRequest):
        svc = _get_service()
        try:
            result = await svc.create_portfolio(
                req.id, req.mode, req.initial_capital, req.sim_start_date
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.get("/portfolio")
    async def list_portfolios():
        svc = _get_service()
        return await svc.list_portfolios()

    @router.get("/portfolio/{portfolio_id}")
    async def get_portfolio(portfolio_id: str):
        svc = _get_service()
        try:
            return await svc.get_portfolio(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Positions ──

    @router.get("/portfolio/{portfolio_id}/positions")
    async def get_positions(
        portfolio_id: str,
        status: str = Query("open", regex="^(open|closed)$"),
    ):
        svc = _get_service()
        return await svc.get_positions(portfolio_id, status)

    @router.get("/portfolio/{portfolio_id}/positions/{position_id}")
    async def get_position(portfolio_id: str, position_id: str):
        svc = _get_service()
        try:
            return await svc.get_position(portfolio_id, position_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Trades ──

    @router.get("/portfolio/{portfolio_id}/trades")
    async def get_trades(
        portfolio_id: str,
        position_id: str | None = None,
        limit: int = Query(50, ge=1, le=500),
    ):
        svc = _get_service()
        return await svc.get_trades(portfolio_id, position_id, limit)

    @router.post("/portfolio/{portfolio_id}/trades")
    async def execute_trade(
        portfolio_id: str,
        trade_input: TradeInput,
        position_id: str | None = None,
        trade_date: str | None = None,
    ):
        svc = _get_service()
        if trade_date is None:
            trade_date = date.today().isoformat()
        try:
            return await svc.execute_trade(
                portfolio_id, trade_input, trade_date, position_id
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── Strategy ──

    @router.post("/portfolio/{portfolio_id}/positions/{position_id}/strategy")
    async def create_strategy(
        portfolio_id: str, position_id: str, req: CreateStrategyRequest,
    ):
        svc = _get_service()
        try:
            return await svc.create_strategy(
                portfolio_id, position_id, req.model_dump()
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/portfolio/{portfolio_id}/positions/{position_id}/strategy")
    async def get_strategy(portfolio_id: str, position_id: str):
        svc = _get_service()
        try:
            return await svc.get_strategy(portfolio_id, position_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return router
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py::TestRoutes -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/routes.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): FastAPI 路由 9 个端点 + 单元测试"
```

---

### Task 9: Integration — config.py + main.py

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/main.py`

- [ ] **Step 1: 读取 main.py 了解当前 startup/shutdown 结构**

Run: `head -80 backend/main.py`

- [ ] **Step 2: 在 main.py 中添加 AgentDB 初始化和路由挂载**

在 `main.py` 的 startup 事件中添加：

```python
from engine.agent.db import AgentDB
from engine.agent.routes import create_agent_router

# 在 startup 中:
AgentDB.init_instance()

# 在 shutdown 中:
AgentDB.get_instance().close()

# 挂载路由:
agent_router = create_agent_router()
app.include_router(agent_router, prefix="/api/v1/agent")
```

具体插入位置需要根据 main.py 现有结构调整。

- [ ] **Step 3: 验证后端能启动**

Run: `cd backend && timeout 5 .venv/bin/python -c "from engine.agent.db import AgentDB; from engine.agent.routes import create_agent_router; print('import ok')"`
Expected: `import ok`

- [ ] **Step 4: 运行全部 Phase 1A 测试**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && backend/.venv/bin/python -m pytest tests/unit/test_agent_phase1a.py -v`
Expected: 全部通过（约 40 个测试）

- [ ] **Step 5: 运行现有测试确保无回归**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && backend/.venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: 无新增失败

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/main.py
git commit -m "feat(agent): 集成 AgentDB 到 main.py startup/shutdown + 挂载路由"
```
