"""Agent wake/data hunger schema and service tests."""
import sys
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.agent.models import BrainRun


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


class TestDataHungerModels:
    def test_brain_run_supports_digest_link_fields(self):
        run = BrainRun(
            id="run-1",
            portfolio_id="portfolio-1",
            started_at="2026-03-22T10:00:00",
            info_digest_ids=["digest-1"],
            triggered_signal_ids=["signal-1"],
        )

        assert run.info_digest_ids == ["digest-1"]
        assert run.triggered_signal_ids == ["signal-1"]


class TestWatchSignalService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("p1", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_create_and_list_watch_signals(self):
        from engine.agent.models import WatchSignalInput

        created = run(self.svc.create_watch_signal(
            "p1",
            WatchSignalInput(
                stock_code="600519",
                signal_description="白酒景气度回升",
                check_engine="info",
                keywords=["白酒", "回升"],
                if_triggered="考虑加仓",
            ),
        ))

        rows = run(self.svc.list_watch_signals("p1"))
        assert rows[0]["id"] == created["id"]
        assert rows[0]["portfolio_id"] == "p1"

    def test_update_watch_signal_status(self):
        from engine.agent.models import WatchSignalInput

        created = run(self.svc.create_watch_signal(
            "p1",
            WatchSignalInput(
                stock_code="600519",
                signal_description="白酒景气度回升",
                check_engine="info",
                keywords=["白酒", "回升"],
            ),
        ))

        updated = run(self.svc.update_watch_signal(created["id"], {"status": "triggered"}))
        assert updated["status"] == "triggered"


class TestWatchSignalRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "p1", "mode": "live", "initial_capital": 1000000.0},
        )

    def teardown_method(self):
        self.db.close()

    def test_watch_signal_routes(self):
        resp = self.client.post(
            "/api/v1/agent/watch-signals",
            json={
                "portfolio_id": "p1",
                "stock_code": "600519",
                "signal_description": "白酒景气度回升",
                "check_engine": "info",
                "keywords": ["白酒", "回升"],
                "if_triggered": "考虑加仓",
            },
        )
        assert resp.status_code == 200
        signal_id = resp.json()["id"]

        resp = self.client.get("/api/v1/agent/watch-signals?portfolio_id=p1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = self.client.patch(
            f"/api/v1/agent/watch-signals/{signal_id}",
            json={"status": "triggered"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"
