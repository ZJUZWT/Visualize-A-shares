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
        from engine.agent.db import AgentDB
        AgentDB._instance = None

    def test_init_instance_creates_tables(self, tmp_path):
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        conn = duckdb.connect(str(db_path))
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='agent'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        conn.close()
        db.close()

        expected = {"portfolio_config", "positions", "trades", "position_strategies", "trade_groups", "llm_calls", "trade_plans", "watchlist", "agent_state", "brain_runs", "brain_config"}
        assert table_names == expected

    def test_get_instance_before_init_raises(self):
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        with pytest.raises(RuntimeError, match="not initialized"):
            AgentDB.get_instance()

    def test_singleton_returns_same_instance(self, tmp_path):
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db1 = AgentDB.init_instance()
            db2 = AgentDB.init_instance()
        assert db1 is db2
        db1.close()

    def test_execute_read(self, tmp_path):
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        rows = run(db.execute_read("SELECT 1 AS val"))
        assert rows == [{"val": 1}]
        db.close()

    def test_execute_write_and_read(self, tmp_path):
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

        rows = run(db.execute_read("SELECT * FROM agent.portfolio_config"))
        assert len(rows) == 0
        db.close()


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
        assert t.source_run_id is None
        assert t.source_plan_id is None
        assert t.source_strategy_id is None
        assert t.source_strategy_version is None


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
        for code in ["600519", "601318", "603288", "605499"]:
            ok, msg = self.v.validate_code(code, "贵州茅台")
            assert ok, f"{code} should be allowed: {msg}"

    def test_allowed_main_board_sz(self):
        for code in ["000001", "001289", "002594", "003816"]:
            ok, msg = self.v.validate_code(code, "平安银行")
            assert ok, f"{code} should be allowed: {msg}"

    def test_blocked_chinext(self):
        ok, msg = self.v.validate_code("300750", "宁德时代")
        assert not ok
        assert "创业板" in msg or "不允许" in msg

    def test_blocked_star(self):
        ok, msg = self.v.validate_code("688981", "中芯国际")
        assert not ok

    def test_blocked_bse(self):
        ok, msg = self.v.validate_code("830799", "艾融软件")
        assert not ok

    def test_blocked_st(self):
        ok, msg = self.v.validate_code("600000", "ST浦发")
        assert not ok
        assert "ST" in msg

    def test_blocked_star_st(self):
        ok, msg = self.v.validate_code("600000", "*ST某某")
        assert not ok

    # ── 交易数量 ──

    def test_lot_size_valid(self):
        ok, _ = self.v.validate_quantity(100)
        assert ok
        ok, _ = self.v.validate_quantity(500)
        assert ok

    def test_lot_size_invalid(self):
        ok, _ = self.v.validate_quantity(50)
        assert not ok
        ok, _ = self.v.validate_quantity(0)
        assert not ok

    # ── T+1 检查 ──

    def test_t_plus_1_same_day_sell_blocked(self):
        ok, msg = self.v.validate_t_plus_1(action="sell", entry_date="2026-03-20", trade_date="2026-03-20")
        assert not ok
        assert "T+1" in msg

    def test_t_plus_1_next_day_sell_ok(self):
        ok, _ = self.v.validate_t_plus_1(action="sell", entry_date="2026-03-19", trade_date="2026-03-20")
        assert ok

    def test_t_plus_1_buy_always_ok(self):
        ok, _ = self.v.validate_t_plus_1(action="buy", entry_date="2026-03-20", trade_date="2026-03-20")
        assert ok

    # ── 涨跌停检查 ──

    def test_limit_up_cannot_buy(self):
        ok, msg = self.v.validate_limit(action="buy", pct_change=10.0)
        assert not ok
        assert "涨停" in msg

    def test_limit_down_cannot_sell(self):
        ok, msg = self.v.validate_limit(action="sell", pct_change=-10.0)
        assert not ok
        assert "跌停" in msg

    def test_normal_price_ok(self):
        ok, _ = self.v.validate_limit(action="buy", pct_change=5.0)
        assert ok
        ok, _ = self.v.validate_limit(action="sell", pct_change=-5.0)
        assert ok

    # ── 资金/持仓检查 ──

    def test_insufficient_cash(self):
        ok, msg = self.v.validate_cash(action="buy", price=100.0, quantity=100, cash=5000.0)
        assert not ok
        assert "资金" in msg

    def test_sufficient_cash(self):
        ok, _ = self.v.validate_cash(action="buy", price=100.0, quantity=100, cash=20000.0)
        assert ok

    def test_sell_no_cash_check(self):
        ok, _ = self.v.validate_cash(action="sell", price=100.0, quantity=100, cash=0.0)
        assert ok

    def test_insufficient_position(self):
        ok, msg = self.v.validate_position_qty(action="sell", current_qty=100, sell_qty=200)
        assert not ok
        assert "持仓" in msg

    def test_sufficient_position(self):
        ok, _ = self.v.validate_position_qty(action="sell", current_qty=200, sell_qty=100)
        assert ok

    # ── 滑点 & 手续费 ──

    def test_slippage_buy(self):
        price = self.v.apply_slippage("buy", 100.0)
        assert abs(price - 100.2) < 0.01

    def test_slippage_sell(self):
        price = self.v.apply_slippage("sell", 100.0)
        assert abs(price - 99.8) < 0.01

    def test_fee_buy_sh(self):
        fee = self.v.calc_fee(action="buy", price=100.0, quantity=100, stock_code="600519")
        transfer = 100.0 * 100 * 0.00001
        expected = 5.0 + transfer  # 佣金不足5元按5元
        assert abs(fee - expected) < 0.01

    def test_fee_sell_sh(self):
        fee = self.v.calc_fee(action="sell", price=100.0, quantity=1000, stock_code="601318")
        amount = 100.0 * 1000
        commission = amount * 0.00025
        stamp = amount * 0.001
        transfer = amount * 0.00001
        expected = commission + stamp + transfer
        assert abs(fee - expected) < 0.01

    def test_fee_sell_sz(self):
        fee = self.v.calc_fee(action="sell", price=50.0, quantity=1000, stock_code="000001")
        amount = 50.0 * 1000
        commission = amount * 0.00025
        stamp = amount * 0.001
        expected = commission + stamp
        assert abs(fee - expected) < 0.01

    def test_fee_min_commission(self):
        fee = self.v.calc_fee(action="buy", price=10.0, quantity=100, stock_code="000001")
        assert fee >= 5.0


# ═══════════════════════════════════════════════════════
# Task 5: AgentService — Portfolio CRUD
# ═══════════════════════════════════════════════════════

import tempfile

def _make_service(tmp_dir):
    """创建独立 DB + Service 的工具函数"""
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.validator import TradeValidator
    from engine.agent.service import AgentService
    svc = AgentService(db=db, validator=TradeValidator())
    return db, svc


class TestServicePortfolio:
    """AgentService 账户管理测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

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


# ═══════════════════════════════════════════════════════
# Task 6: AgentService — execute_trade
# ═══════════════════════════════════════════════════════

def _make_trade_input(**overrides):
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


class TestServiceTrade:
    """AgentService 交易执行测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_buy_creates_position_and_trade(self):
        ti = _make_trade_input()
        result = run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        assert result["trade"]["action"] == "buy"
        assert result["trade"]["position_id"] is not None
        assert result["position"]["current_qty"] == 100
        assert result["position"]["status"] == "open"
        portfolio = run(self.svc.get_portfolio("live"))
        assert portfolio["cash_balance"] < 1000000.0

    def test_buy_slippage_applied(self):
        ti = _make_trade_input(price=1000.0, quantity=100)
        result = run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        assert result["trade"]["price"] == 1002.0

    def test_buy_fee_deducted(self):
        ti = _make_trade_input(price=1000.0, quantity=100)
        run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        portfolio = run(self.svc.get_portfolio("live"))
        assert portfolio["cash_balance"] < 1000000.0 - 100200

    def test_buy_blocked_code(self):
        ti = _make_trade_input(stock_code="300750")
        with pytest.raises(ValueError, match="不允许"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))

    def test_buy_invalid_lot_size(self):
        ti = _make_trade_input(quantity=50)
        with pytest.raises(ValueError, match="100"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))

    def test_buy_insufficient_cash(self):
        ti = _make_trade_input(price=50000.0, quantity=100)
        with pytest.raises(ValueError, match="资金"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))

    def test_add_position(self):
        ti_buy = _make_trade_input(price=1000.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-20"))
        pos_id = r1["position"]["id"]

        ti_add = _make_trade_input(action="add", price=1100.0, quantity=100)
        r2 = run(self.svc.execute_trade("live", ti_add, trade_date="2026-03-21", position_id=pos_id))
        assert r2["position"]["current_qty"] == 200
        assert 1000.0 < r2["position"]["entry_price"] < 1200.0

    def test_sell_reduces_qty(self):
        ti_buy = _make_trade_input(price=100.0, quantity=200)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-19"))
        pos_id = r1["position"]["id"]

        ti_sell = _make_trade_input(action="sell", price=110.0, quantity=100)
        r2 = run(self.svc.execute_trade("live", ti_sell, trade_date="2026-03-20", position_id=pos_id))
        assert r2["position"]["current_qty"] == 100
        assert r2["position"]["status"] == "open"

    def test_sell_all_closes_position(self):
        ti_buy = _make_trade_input(price=100.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-19"))
        pos_id = r1["position"]["id"]

        ti_sell = _make_trade_input(action="sell", price=110.0, quantity=100)
        r2 = run(self.svc.execute_trade("live", ti_sell, trade_date="2026-03-20", position_id=pos_id))
        assert r2["position"]["current_qty"] == 0
        assert r2["position"]["status"] == "closed"

    def test_sell_t_plus_1_blocked(self):
        ti_buy = _make_trade_input(price=100.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-20"))
        pos_id = r1["position"]["id"]

        ti_sell = _make_trade_input(action="sell", price=110.0, quantity=100)
        with pytest.raises(ValueError, match="T\\+1"):
            run(self.svc.execute_trade("live", ti_sell, trade_date="2026-03-20", position_id=pos_id))

    def test_sell_cash_increases(self):
        ti_buy = _make_trade_input(price=100.0, quantity=100)
        r1 = run(self.svc.execute_trade("live", ti_buy, trade_date="2026-03-19"))
        pos_id = r1["position"]["id"]
        cash_after_buy = run(self.svc.get_portfolio("live"))["cash_balance"]

        ti_sell = _make_trade_input(action="sell", price=110.0, quantity=100)
        run(self.svc.execute_trade("live", ti_sell, trade_date="2026-03-20", position_id=pos_id))
        cash_after_sell = run(self.svc.get_portfolio("live"))["cash_balance"]
        assert cash_after_sell > cash_after_buy

    def test_buy_requires_holding_type(self):
        ti = _make_trade_input(holding_type=None)
        with pytest.raises(ValueError, match="holding_type"):
            run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))


# ═══════════════════════════════════════════════════════
# Task 7: AgentService — Strategy CRUD
# ═══════════════════════════════════════════════════════

class TestServiceStrategy:
    """AgentService 策略管理测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))
        ti = _make_trade_input(price=1800.0, quantity=100)
        result = run(self.svc.execute_trade("live", ti, trade_date="2026-03-20"))
        self.pos_id = result["position"]["id"]

    def teardown_method(self):
        self.db.close()

    def test_create_strategy(self):
        result = run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2200.0, "stop_loss": 1600.0,
            "reasoning": "白酒龙头长期持有",
            "details": {"fundamental_anchor": "硅料产能出清"},
        }))
        assert result["position_id"] == self.pos_id
        assert result["version"] == 1
        assert result["take_profit"] == 2200.0

    def test_update_strategy_increments_version(self):
        run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2200.0, "stop_loss": 1600.0, "reasoning": "初始策略",
        }))
        result = run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2500.0, "stop_loss": 1500.0, "reasoning": "上调止盈",
        }))
        assert result["version"] == 2

    def test_get_strategy(self):
        run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2200.0, "stop_loss": 1600.0, "reasoning": "v1",
        }))
        run(self.svc.create_strategy("live", self.pos_id, {
            "take_profit": 2500.0, "stop_loss": 1500.0, "reasoning": "v2",
        }))
        result = run(self.svc.get_strategy("live", self.pos_id))
        assert len(result) == 2
        assert result[0]["version"] == 2

    def test_create_strategy_nonexistent_position(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.create_strategy("live", "nonexistent", {
                "take_profit": 2200.0, "stop_loss": 1600.0, "reasoning": "test",
            }))


# ═══════════════════════════════════════════════════════
# Task 8: FastAPI Routes
# ═══════════════════════════════════════════════════════
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_test_app(tmp_dir):
    """创建带 AgentDB 的测试 FastAPI app"""
    db_path = Path(tmp_dir) / "test_agent.duckdb"
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

    def setup_method(self):
        self._tmp_dir = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp_dir)
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
        buy_resp = self.client.post("/api/v1/agent/portfolio/live/trades", json={
            "action": "buy", "stock_code": "600519", "price": 1800.0,
            "quantity": 100, "holding_type": "long_term",
            "reason": "白酒龙头", "thesis": "消费复苏",
            "data_basis": ["营收增长20%"], "risk_note": "估值偏高",
            "invalidation": "Q2营收下滑",
        })
        pos_id = buy_resp.json()["position"]["id"]

        resp = self.client.post(
            f"/api/v1/agent/portfolio/live/positions/{pos_id}/strategy",
            json={"take_profit": 2200.0, "stop_loss": 1600.0, "reasoning": "长期持有策略"},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

        resp = self.client.get(f"/api/v1/agent/portfolio/live/positions/{pos_id}/strategy")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
