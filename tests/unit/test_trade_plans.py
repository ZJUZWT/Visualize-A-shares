"""交易计划备忘录单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
import duckdb
import pytest
from unittest.mock import patch

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══════════════════════════════════════════════════════
# Task 1: trade_plans 表 + 模型
# ═══════════════════════════════════════════════════════

class TestTradePlansTable:
    """trade_plans 表测试"""

    def test_table_exists(self, tmp_path):
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

        assert "trade_plans" in table_names


class TestTradePlanModels:
    """Pydantic 模型测试"""

    def test_trade_plan_input_valid(self):
        from engine.agent.models import TradePlanInput
        ti = TradePlanInput(
            stock_code="600519", stock_name="贵州茅台",
            current_price=1800.0, direction="buy",
            entry_price=1750.0, entry_method="分两批买入",
            position_pct=0.1,
            take_profit=2100.0, take_profit_method="到2000先减半，2100清仓",
            stop_loss=1650.0, stop_loss_method="跌破1650一次性清仓",
            reasoning="白酒消费复苏",
            risk_note="消费数据不及预期",
            invalidation="Q2营收下滑",
            valid_until="2026-04",
        )
        assert ti.direction == "buy"
        assert ti.source_type == "expert"

    def test_trade_plan_input_minimal(self):
        from engine.agent.models import TradePlanInput
        ti = TradePlanInput(
            stock_code="600519", stock_name="贵州茅台",
            direction="buy", reasoning="白酒龙头",
        )
        assert ti.entry_price is None
        assert ti.stop_loss is None

    def test_trade_plan_update(self):
        from engine.agent.models import TradePlanUpdate
        u = TradePlanUpdate(status="executing")
        assert u.status == "executing"

    def test_trade_plan_update_invalid_status(self):
        from engine.agent.models import TradePlanUpdate
        with pytest.raises(Exception):
            TradePlanUpdate(status="invalid_status")


# ═══════════════════════════════════════════════════════
# Task 2: Plans CRUD Service
# ═══════════════════════════════════════════════════════

def _make_service(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.validator import TradeValidator
    from engine.agent.service import AgentService
    svc = AgentService(db=db, validator=TradeValidator())
    return db, svc


def _make_plan_input(**overrides):
    from engine.agent.models import TradePlanInput
    defaults = dict(
        stock_code="600519", stock_name="贵州茅台",
        current_price=1800.0, direction="buy",
        entry_price=1750.0, entry_method="分两批买入",
        position_pct=0.1,
        take_profit=2100.0, take_profit_method="到2000先减半",
        stop_loss=1650.0, stop_loss_method="跌破1650清仓",
        reasoning="白酒消费复苏",
        risk_note="消费不及预期",
        invalidation="Q2营收下滑",
        valid_until="2026-04-05",
    )
    defaults.update(overrides)
    return TradePlanInput(**defaults)


class TestServicePlans:
    """AgentService 交易计划 CRUD 测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_create_plan(self):
        pi = _make_plan_input()
        result = run(self.svc.create_plan(pi))
        assert result["stock_code"] == "600519"
        assert result["status"] == "pending"
        assert result["id"] is not None

    def test_list_plans(self):
        run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.create_plan(_make_plan_input(stock_code="601318", stock_name="中国平安")))
        result = run(self.svc.list_plans())
        assert len(result) == 2

    def test_list_plans_filter_status(self):
        run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.create_plan(_make_plan_input(stock_code="601318", stock_name="中国平安")))
        plans = run(self.svc.list_plans())
        run(self.svc.update_plan(plans[0]["id"], {"status": "executing"}))
        result = run(self.svc.list_plans(status="pending"))
        assert len(result) == 1

    def test_list_plans_filter_stock_code(self):
        run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.create_plan(_make_plan_input(stock_code="601318", stock_name="中国平安")))
        result = run(self.svc.list_plans(stock_code="600519"))
        assert len(result) == 1

    def test_get_plan(self):
        created = run(self.svc.create_plan(_make_plan_input()))
        result = run(self.svc.get_plan(created["id"]))
        assert result["stock_code"] == "600519"
        assert result["reasoning"] == "白酒消费复苏"

    def test_get_plan_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_plan("nonexistent"))

    def test_update_plan_status(self):
        created = run(self.svc.create_plan(_make_plan_input()))
        result = run(self.svc.update_plan(created["id"], {"status": "executing"}))
        assert result["status"] == "executing"

    def test_delete_plan(self):
        created = run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.delete_plan(created["id"]))
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_plan(created["id"]))

    def test_delete_plan_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.delete_plan("nonexistent"))


# ═══════════════════════════════════════════════════════
# Task 3: FastAPI Routes
# ═══════════════════════════════════════════════════════
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_test_app(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.routes import create_agent_router
    app = FastAPI()
    app.include_router(create_agent_router(), prefix="/api/v1/agent")
    return app, db


class TestPlansRoutes:
    """Plans API 路由测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def _create_plan(self, **overrides):
        defaults = {
            "stock_code": "600519", "stock_name": "贵州茅台",
            "current_price": 1800.0, "direction": "buy",
            "entry_price": 1750.0, "reasoning": "白酒消费复苏",
            "stop_loss": 1650.0,
        }
        defaults.update(overrides)
        return self.client.post("/api/v1/agent/plans", json=defaults)

    def test_create_plan(self):
        resp = self._create_plan()
        assert resp.status_code == 200
        assert resp.json()["stock_code"] == "600519"
        assert resp.json()["status"] == "pending"

    def test_list_plans(self):
        self._create_plan()
        self._create_plan(stock_code="601318", stock_name="中国平安")
        resp = self.client.get("/api/v1/agent/plans")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_plans_filter_status(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        self.client.patch(f"/api/v1/agent/plans/{plan_id}", json={"status": "executing"})
        self._create_plan(stock_code="601318", stock_name="中国平安")
        resp = self.client.get("/api/v1/agent/plans?status=pending")
        assert len(resp.json()) == 1

    def test_get_plan(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        resp = self.client.get(f"/api/v1/agent/plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["stock_code"] == "600519"

    def test_get_plan_404(self):
        resp = self.client.get("/api/v1/agent/plans/nonexistent")
        assert resp.status_code == 404

    def test_update_plan(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        resp = self.client.patch(f"/api/v1/agent/plans/{plan_id}", json={"status": "executing"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "executing"

    def test_delete_plan(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        resp = self.client.delete(f"/api/v1/agent/plans/{plan_id}")
        assert resp.status_code == 200
        resp = self.client.get(f"/api/v1/agent/plans/{plan_id}")
        assert resp.status_code == 404

    def test_delete_plan_404(self):
        resp = self.client.delete("/api/v1/agent/plans/nonexistent")
        assert resp.status_code == 404
