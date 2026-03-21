"""Agent Brain 单元测试"""
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
# Task 1: 表 + 模型
# ═══════════════════════════════════════════════════════

class TestBrainTables:
    def test_tables_exist(self, tmp_path):
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

        assert "watchlist" in table_names
        assert "agent_state" in table_names
        assert "brain_runs" in table_names
        assert "brain_config" in table_names

    def test_schema_columns_exist(self, tmp_path):
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        conn = duckdb.connect(str(db_path))

        def columns_for(table_name: str) -> set[str]:
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'agent' AND table_name = ?
                """,
                [table_name],
            ).fetchall()
            return {row[0] for row in rows}

        assert "thinking_process" in columns_for("brain_runs")
        assert "source_run_id" in columns_for("trade_plans")
        assert "source_run_id" in columns_for("position_strategies")
        trade_columns = columns_for("trades")
        assert "source_run_id" in trade_columns
        assert "source_plan_id" in trade_columns
        assert "source_strategy_id" in trade_columns
        assert "source_strategy_version" in trade_columns

        conn.close()
        db.close()


class TestBrainModels:
    def test_watchlist_input(self):
        from engine.agent.models import WatchlistInput
        w = WatchlistInput(stock_code="600519", stock_name="贵州茅台", reason="白酒龙头")
        assert w.stock_code == "600519"

    def test_brain_config_defaults(self):
        from engine.agent.models import BrainConfig
        c = BrainConfig()
        assert c.enable_debate is False
        assert c.max_candidates == 30
        assert c.quant_top_n == 20
        assert c.max_position_count == 10
        assert c.single_position_pct == 0.15
        assert c.schedule_time == "15:30"

    def test_brain_run_model(self):
        from engine.agent.models import BrainRun
        r = BrainRun(
            id="test", portfolio_id="p1",
            started_at="2026-03-21T15:30:00",
        )
        assert r.status == "running"
        assert r.candidates is None
        assert r.thinking_process is None

    def test_agent_state_model(self):
        from engine.agent.models import AgentState
        state = AgentState(
            portfolio_id="p1",
            created_at="2026-03-22T10:00:00",
            updated_at="2026-03-22T10:00:00",
        )
        assert state.market_view is None
        assert state.position_level is None
        assert state.source_run_id is None

    def test_trade_plan_model_has_source_run_id(self):
        from engine.agent.models import TradePlan
        plan = TradePlan(
            id="plan-1",
            stock_code="600519",
            stock_name="贵州茅台",
            direction="buy",
            reasoning="test",
            created_at="2026-03-22T10:00:00",
            updated_at="2026-03-22T10:00:00",
        )
        assert plan.source_run_id is None

    def test_position_strategy_model_has_source_run_id(self):
        from engine.agent.models import PositionStrategy
        strategy = PositionStrategy(
            id="strategy-1",
            position_id="pos-1",
            holding_type="long_term",
            reasoning="长期持有",
            created_at="2026-03-22T10:00:00",
            updated_at="2026-03-22T10:00:00",
        )
        assert strategy.source_run_id is None


# ═══════════════════════════════════════════════════════
# Task 2: Watchlist + BrainRuns CRUD
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


class TestServiceWatchlist:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_add_watchlist(self):
        from engine.agent.models import WatchlistInput
        result = run(self.svc.add_watchlist(WatchlistInput(
            stock_code="600519", stock_name="贵州茅台", reason="白酒龙头"
        )))
        assert result["stock_code"] == "600519"
        assert result["added_by"] == "manual"

    def test_list_watchlist(self):
        from engine.agent.models import WatchlistInput
        run(self.svc.add_watchlist(WatchlistInput(stock_code="600519", stock_name="贵州茅台")))
        run(self.svc.add_watchlist(WatchlistInput(stock_code="601318", stock_name="中国平安")))
        result = run(self.svc.list_watchlist())
        assert len(result) == 2

    def test_remove_watchlist(self):
        from engine.agent.models import WatchlistInput
        item = run(self.svc.add_watchlist(WatchlistInput(stock_code="600519", stock_name="贵州茅台")))
        run(self.svc.remove_watchlist(item["id"]))
        result = run(self.svc.list_watchlist())
        assert len(result) == 0

    def test_remove_watchlist_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.remove_watchlist("nonexistent"))


class TestServiceBrainRuns:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_create_brain_run(self):
        result = run(self.svc.create_brain_run("portfolio_1", "manual"))
        assert result["status"] == "running"
        assert result["portfolio_id"] == "portfolio_1"
        assert result["run_type"] == "manual"

    def test_update_brain_run(self):
        created = run(self.svc.create_brain_run("portfolio_1"))
        run(self.svc.update_brain_run(created["id"], {
            "status": "completed",
            "decisions": [{"action": "buy", "stock_code": "600519"}],
        }))
        result = run(self.svc.get_brain_run(created["id"]))
        assert result["status"] == "completed"

    def test_list_brain_runs(self):
        run(self.svc.create_brain_run("portfolio_1"))
        run(self.svc.create_brain_run("portfolio_1"))
        result = run(self.svc.list_brain_runs("portfolio_1"))
        assert len(result) == 2

    def test_get_brain_run_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_brain_run("nonexistent"))

    def test_get_brain_config(self):
        result = run(self.svc.get_brain_config())
        assert result["enable_debate"] is False
        assert result["max_candidates"] == 30

    def test_update_brain_config(self):
        run(self.svc.update_brain_config({"enable_debate": True, "max_candidates": 50}))
        result = run(self.svc.get_brain_config())
        assert result["enable_debate"] is True
        assert result["max_candidates"] == 50


class TestServiceAgentState:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("portfolio_1", "live", 1000000))

    def teardown_method(self):
        self.db.close()

    def test_get_agent_state_creates_default_snapshot(self):
        result = run(self.svc.get_agent_state("portfolio_1"))
        assert result["portfolio_id"] == "portfolio_1"
        assert result["market_view"] is None
        assert result["position_level"] is None
        assert result["sector_preferences"] is None
        assert result["risk_alerts"] is None
        assert result["source_run_id"] is None

    def test_update_agent_state_fields(self):
        result = run(self.svc.update_agent_state(
            "portfolio_1",
            {
                "market_view": {"bias": "bullish"},
                "position_level": "medium",
                "sector_preferences": ["白酒", "银行"],
                "risk_alerts": ["估值偏高"],
            },
            source_run_id="run-1",
        ))
        assert result["market_view"] == {"bias": "bullish"}
        assert result["position_level"] == "medium"
        assert result["sector_preferences"] == ["白酒", "银行"]
        assert result["risk_alerts"] == ["估值偏高"]
        assert result["source_run_id"] == "run-1"


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


class TestWatchlistRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def test_add_watchlist(self):
        resp = self.client.post("/api/v1/agent/watchlist", json={
            "stock_code": "600519", "stock_name": "贵州茅台", "reason": "白酒龙头"
        })
        assert resp.status_code == 200
        assert resp.json()["stock_code"] == "600519"

    def test_list_watchlist(self):
        self.client.post("/api/v1/agent/watchlist", json={"stock_code": "600519", "stock_name": "贵州茅台"})
        resp = self.client.get("/api/v1/agent/watchlist")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_delete_watchlist(self):
        r = self.client.post("/api/v1/agent/watchlist", json={"stock_code": "600519", "stock_name": "贵州茅台"})
        item_id = r.json()["id"]
        resp = self.client.delete(f"/api/v1/agent/watchlist/{item_id}")
        assert resp.status_code == 200
        resp = self.client.get("/api/v1/agent/watchlist")
        assert len(resp.json()) == 0

    def test_delete_watchlist_404(self):
        resp = self.client.delete("/api/v1/agent/watchlist/nonexistent")
        assert resp.status_code == 404


class TestBrainRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def test_get_brain_config(self):
        resp = self.client.get("/api/v1/agent/brain/config")
        assert resp.status_code == 200
        assert resp.json()["enable_debate"] is False

    def test_update_brain_config(self):
        resp = self.client.patch("/api/v1/agent/brain/config", json={"enable_debate": True})
        assert resp.status_code == 200
        resp = self.client.get("/api/v1/agent/brain/config")
        assert resp.json()["enable_debate"] is True

    def test_list_brain_runs_empty(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "p1", "mode": "live", "initial_capital": 1000000
        })
        resp = self.client.get("/api/v1/agent/brain/runs?portfolio_id=p1")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_get_agent_state(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "p1", "mode": "live", "initial_capital": 1000000
        })
        resp = self.client.get("/api/v1/agent/state?portfolio_id=p1")
        assert resp.status_code == 200
        assert resp.json()["portfolio_id"] == "p1"
        assert resp.json()["market_view"] is None

    def test_patch_agent_state(self):
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "p1", "mode": "live", "initial_capital": 1000000
        })
        resp = self.client.patch(
            "/api/v1/agent/state?portfolio_id=p1",
            json={
                "market_view": {"bias": "neutral"},
                "position_level": "low",
                "sector_preferences": ["家电"],
                "risk_alerts": ["波动放大"],
                "source_run_id": "run-2",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["market_view"] == {"bias": "neutral"}
        assert resp.json()["position_level"] == "low"
        assert resp.json()["sector_preferences"] == ["家电"]
        assert resp.json()["risk_alerts"] == ["波动放大"]
        assert resp.json()["source_run_id"] == "run-2"


# ═══════════════════════════════════════════════════════
# Task 4: Brain — 标的筛选
# ═══════════════════════════════════════════════════════

class TestBrainCandidates:
    def test_merge_candidates(self):
        from engine.agent.brain import AgentBrain
        brain = AgentBrain.__new__(AgentBrain)
        watchlist = [
            {"stock_code": "600519", "stock_name": "贵州茅台"},
            {"stock_code": "601318", "stock_name": "中国平安"},
        ]
        quant_top = [
            {"stock_code": "600519", "score": 0.85},
            {"stock_code": "000858", "score": 0.80},
        ]
        positions = [
            {"stock_code": "601888", "stock_name": "中国中免"},
        ]
        result = brain._merge_candidates(watchlist, quant_top, positions, max_n=30)
        codes = [c["stock_code"] for c in result]
        assert "600519" in codes
        assert "601318" in codes
        assert "000858" in codes
        assert "601888" in codes
        assert codes.count("600519") == 1
