"""Agent read model 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_service(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.service import AgentService
    from engine.agent.validator import TradeValidator

    svc = AgentService(db=db, validator=TradeValidator())
    return db, svc


def _make_app(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.routes import create_agent_router

    app = FastAPI()
    app.include_router(create_agent_router(), prefix="/api/v1/agent")
    return app, db


def _make_plan_input(**overrides):
    from engine.agent.models import TradePlanInput

    payload = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "current_price": 1800.0,
        "direction": "buy",
        "entry_price": 1788.0,
        "entry_method": "回调买入",
        "position_pct": 0.15,
        "take_profit": 1950.0,
        "take_profit_method": "分批止盈",
        "stop_loss": 1700.0,
        "stop_loss_method": "跌破前低",
        "reasoning": "景气修复",
        "risk_note": "估值偏高",
        "invalidation": "基本面转弱",
        "valid_until": "2026-03-31",
        "source_type": "agent",
        "source_conversation_id": None,
    }
    payload.update(overrides)
    return TradePlanInput(**payload)


def _make_trade_input(**overrides):
    from engine.agent.models import TradeInput

    payload = {
        "action": "buy",
        "stock_code": "600519",
        "price": 1800.0,
        "quantity": 100,
        "holding_type": "mid_term",
        "reason": "景气修复",
        "thesis": "基本面改善",
        "data_basis": ["营收修复"],
        "risk_note": "估值偏高",
        "invalidation": "景气拐点失效",
        "triggered_by": "agent",
    }
    payload.update(overrides)
    return TradeInput(**payload)


class TestLedgerOverviewService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_get_ledger_overview_returns_stable_read_model(self):
        other_portfolio = run(self.svc.create_portfolio("training", "training", 500000.0))
        live_pending_run = run(self.svc.create_brain_run("live"))
        live_executing_run = run(self.svc.create_brain_run("live"))
        other_run = run(self.svc.create_brain_run(other_portfolio["id"]))

        pending_plan = run(
            self.svc.create_plan(
                _make_plan_input(),
                source_run_id=live_pending_run["id"],
            )
        )
        executing_plan = run(
            self.svc.create_plan(
                _make_plan_input(stock_code="601318", stock_name="中国平安"),
                source_run_id=live_executing_run["id"],
            )
        )
        unrelated_plan = run(
            self.svc.create_plan(
                _make_plan_input(stock_code="000001", stock_name="平安银行"),
                source_run_id=other_run["id"],
            )
        )
        run(self.svc.update_plan(executing_plan["id"], {"status": "executing"}))
        trade_result = run(
            self.svc.execute_trade(
                "live",
                _make_trade_input(),
                "2026-03-20",
                source_run_id="run-trade",
                source_plan_id=executing_plan["id"],
                source_strategy_id="strategy-1",
                source_strategy_version=1,
            )
        )

        overview = run(self.svc.get_ledger_overview("live"))

        assert set(overview.keys()) == {
            "portfolio_id",
            "asset_summary",
            "open_positions",
            "recent_trades",
            "active_plans",
        }
        assert overview["portfolio_id"] == "live"

        asset_summary = overview["asset_summary"]
        assert set(asset_summary.keys()) == {
            "initial_capital",
            "cash_balance",
            "position_value",
            "total_asset",
            "total_pnl",
            "total_pnl_pct",
            "open_position_count",
            "recent_trade_count",
            "pending_plan_count",
            "executing_plan_count",
        }
        assert asset_summary["initial_capital"] == 1000000.0
        assert asset_summary["open_position_count"] == 1
        assert asset_summary["recent_trade_count"] == 1
        assert asset_summary["pending_plan_count"] == 1
        assert asset_summary["executing_plan_count"] == 1

        position = overview["open_positions"][0]
        assert set(position.keys()) == {
            "id",
            "stock_code",
            "stock_name",
            "holding_type",
            "current_qty",
            "entry_price",
            "cost_basis",
            "entry_date",
            "status",
            "market_value",
            "unrealized_pnl",
            "unrealized_pnl_pct",
        }
        assert position["stock_code"] == "600519"

        trade = overview["recent_trades"][0]
        assert set(trade.keys()) == {
            "id",
            "position_id",
            "action",
            "stock_code",
            "stock_name",
            "price",
            "quantity",
            "amount",
            "reason",
            "thesis",
            "triggered_by",
            "created_at",
            "source_run_id",
            "source_plan_id",
            "source_strategy_id",
            "source_strategy_version",
        }
        assert trade["id"] == trade_result["trade"]["id"]
        assert trade["source_plan_id"] == executing_plan["id"]

        active_plans = overview["active_plans"]
        assert set(active_plans.keys()) == {"pending", "executing"}
        assert len(active_plans["pending"]) == 1
        assert len(active_plans["executing"]) == 1
        assert active_plans["pending"][0]["id"] == pending_plan["id"]
        assert active_plans["executing"][0]["id"] == executing_plan["id"]
        assert all(plan["id"] != unrelated_plan["id"] for plan in active_plans["pending"])

    def test_get_ledger_overview_raises_for_missing_portfolio(self):
        import pytest

        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_ledger_overview("missing"))


class TestLedgerOverviewRoute:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _make_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def test_get_ledger_overview_route(self):
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "live", "mode": "live", "initial_capital": 1000000.0},
        )
        self.client.post(
            "/api/v1/agent/plans",
            json={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "current_price": 1800.0,
                "direction": "buy",
                "entry_price": 1788.0,
                "entry_method": "回调买入",
                "position_pct": 0.15,
                "take_profit": 1950.0,
                "take_profit_method": "分批止盈",
                "stop_loss": 1700.0,
                "stop_loss_method": "跌破前低",
                "reasoning": "景气修复",
                "risk_note": "估值偏高",
                "invalidation": "基本面转弱",
                "valid_until": "2026-03-31",
                "source_type": "agent",
            },
        )
        self.client.post(
            "/api/v1/agent/portfolio/live/trades",
            json={
                "action": "buy",
                "stock_code": "600519",
                "price": 1800.0,
                "quantity": 100,
                "holding_type": "mid_term",
                "reason": "景气修复",
                "thesis": "基本面改善",
                "data_basis": ["营收修复"],
                "risk_note": "估值偏高",
                "invalidation": "景气拐点失效",
                "triggered_by": "agent",
            },
        )

        resp = self.client.get("/api/v1/agent/ledger/overview?portfolio_id=live")

        assert resp.status_code == 200
        body = resp.json()
        assert body["portfolio_id"] == "live"
        assert "asset_summary" in body
        assert "open_positions" in body
        assert "recent_trades" in body
        assert "active_plans" in body

    def test_get_ledger_overview_route_404_for_missing_portfolio(self):
        resp = self.client.get("/api/v1/agent/ledger/overview?portfolio_id=missing")

        assert resp.status_code == 404
