"""Agent strategy history / reflections read-model tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import json
import tempfile
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


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


def _create_reflection_tables(db):
    run(
        db.execute_write(
            """
            CREATE TABLE IF NOT EXISTS agent.daily_reviews (
                id VARCHAR PRIMARY KEY,
                review_date DATE NOT NULL,
                total_reviews INTEGER DEFAULT 0,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                holding_count INTEGER DEFAULT 0,
                total_pnl_pct DOUBLE DEFAULT 0.0,
                summary TEXT,
                created_at TIMESTAMP DEFAULT now()
            )
            """
        )
    )
    run(
        db.execute_write(
            """
            CREATE TABLE IF NOT EXISTS agent.weekly_reflections (
                id VARCHAR PRIMARY KEY,
                week_start DATE NOT NULL,
                week_end DATE NOT NULL,
                total_reviews INTEGER DEFAULT 0,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                holding_count INTEGER DEFAULT 0,
                win_rate DOUBLE DEFAULT 0.0,
                total_pnl_pct DOUBLE DEFAULT 0.0,
                summary TEXT,
                created_at TIMESTAMP DEFAULT now()
            )
            """
        )
    )


class TestStrategyHistoryReadModels:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))
        _create_reflection_tables(self.db)

    def teardown_method(self):
        self.db.close()

    def test_list_strategy_history_normalizes_completed_runs(self):
        run_1 = run(self.svc.create_brain_run("live", "manual"))
        run_2 = run(self.svc.create_brain_run("live", "scheduled"))
        other = run(self.svc.create_brain_run("other", "scheduled")) if False else None
        run(self.svc.create_portfolio("other", "training", 500000.0))
        other = run(self.svc.create_brain_run("other", "scheduled"))

        run(
            self.svc.update_brain_run(
                run_1["id"],
                {
                    "status": "completed",
                    "state_after": {
                        "market_view": {"bias": "bullish"},
                        "position_level": "medium",
                        "sector_preferences": ["白酒", "银行"],
                        "risk_alerts": ["估值过热"],
                    },
                    "execution_summary": {
                        "candidate_count": 12,
                        "analysis_count": 5,
                        "decision_count": 2,
                        "plan_count": 1,
                        "trade_count": 1,
                    },
                },
            )
        )
        run(
            self.svc.update_brain_run(
                run_2["id"],
                {
                    "status": "completed",
                    "state_after": {
                        "market_view": {"bias": "neutral"},
                        "position_level": "low",
                        "sector_preferences": [],
                        "risk_alerts": [],
                    },
                    "execution_summary": {
                        "candidate_count": 3,
                        "analysis_count": 2,
                        "decision_count": 0,
                        "plan_count": 0,
                        "trade_count": 0,
                    },
                },
            )
        )
        run(
            self.svc.update_brain_run(
                other["id"],
                {
                    "status": "completed",
                    "state_after": {"market_view": {"bias": "other"}},
                    "execution_summary": {"candidate_count": 99},
                },
            )
        )

        history = run(self.svc.list_strategy_history("live", limit=10))

        assert len(history) == 2
        assert history[0]["run_id"] == run_2["id"]
        assert history[0]["position_level"] == "low"
        assert history[0]["candidate_count"] == 3
        assert history[1]["run_id"] == run_1["id"]
        assert history[1]["market_view"] == {"bias": "bullish"}
        assert history[1]["sector_preferences"] == ["白酒", "银行"]
        assert history[1]["risk_alerts"] == ["估值过热"]
        assert history[1]["plan_count"] == 1
        assert isinstance(history[0]["occurred_at"], str)

    def test_list_strategy_history_raises_for_missing_portfolio(self):
        import pytest

        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.list_strategy_history("missing", limit=10))

    def test_list_reflections_returns_mixed_feed_newest_first(self):
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.daily_reviews
                    (id, review_date, total_reviews, win_count, loss_count,
                     holding_count, total_pnl_pct, summary,
                     info_review_summary, info_review_details, created_at)
                VALUES
                    ('daily-1', '2026-03-21', 3, 2, 1, 0, 0.0375,
                     '日复盘：执行较稳', '信息复盘：有效信号占优',
                     '{"digest_count":3,"useful_count":2}', '2026-03-21T16:10:00'),
                    ('daily-2', '2026-03-19', 2, 1, 1, 0, 0.0040,
                     '日复盘：震荡等待', null, null, '2026-03-19T16:10:00')
                """
            )
        )
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.weekly_reflections
                    (id, week_start, week_end, total_reviews, win_count, loss_count,
                     win_rate, total_pnl_pct, summary,
                     info_review_summary, info_review_details, created_at)
                VALUES
                    ('weekly-1', '2026-03-16', '2026-03-20', 8, 5, 3, 0.625, 0.052,
                     '周反思：仓位控制优于追涨', '周信息复盘：缺失来源集中在公告',
                     '{"digest_count":8,"misleading_count":2}', '2026-03-20T18:00:00')
                """
            )
        )

        reflections = run(self.svc.list_reflections(limit=10))

        assert [item["id"] for item in reflections] == ["daily-1", "weekly-1", "daily-2"]
        assert reflections[0]["kind"] == "daily"
        assert reflections[0]["date"] == "2026-03-21"
        assert reflections[0]["summary"] == "日复盘：执行较稳"
        assert reflections[0]["metrics"]["total_trades"] == 3
        assert reflections[0]["metrics"]["win_rate"] == pytest.approx(2 / 3)
        assert reflections[0]["metrics"]["avg_pnl_pct"] == pytest.approx(0.0125)
        assert reflections[0]["details"]["notes"] is None
        assert reflections[0]["details"]["info_review"]["summary"] == "信息复盘：有效信号占优"
        assert reflections[0]["details"]["info_review"]["details"]["digest_count"] == 3
        assert reflections[1]["kind"] == "weekly"
        assert reflections[1]["date"] == "2026-03-20"
        assert reflections[1]["details"]["week_start"] == "2026-03-16"
        assert reflections[1]["details"]["week_end"] == "2026-03-20"
        assert reflections[1]["details"]["info_review"]["summary"] == "周信息复盘：缺失来源集中在公告"
        assert reflections[1]["details"]["info_review"]["details"]["misleading_count"] == 2


class TestStrategyHistoryRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _make_app(self._tmp)
        self.client = TestClient(self.app)
        _create_reflection_tables(self.db)

    def teardown_method(self):
        self.db.close()

    def test_get_strategy_history_route(self):
        self.client.post("/api/v1/agent/portfolio", json={"id": "live", "mode": "live", "initial_capital": 1000000.0})
        with patch("engine.agent.routes.AgentDB.get_instance") as _:
            pass
        from engine.agent.db import AgentDB
        from engine.agent.service import AgentService
        from engine.agent.validator import TradeValidator
        svc = AgentService(db=AgentDB.get_instance(), validator=TradeValidator())
        run_record = run(svc.create_brain_run("live", "manual"))
        run(
            svc.update_brain_run(
                run_record["id"],
                {
                    "status": "completed",
                    "state_after": {"market_view": {"bias": "bullish"}, "position_level": "medium", "sector_preferences": [], "risk_alerts": []},
                    "execution_summary": {"candidate_count": 4, "analysis_count": 2, "decision_count": 1, "plan_count": 1, "trade_count": 1},
                },
            )
        )

        resp = self.client.get("/api/v1/agent/strategy/history?portfolio_id=live&limit=5")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["run_id"] == run_record["id"]
        assert body[0]["candidate_count"] == 4

    def test_get_strategy_history_route_404_for_missing_portfolio(self):
        resp = self.client.get("/api/v1/agent/strategy/history?portfolio_id=missing&limit=5")

        assert resp.status_code == 404

    def test_get_reflections_route(self):
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.daily_reviews
                    (id, review_date, total_reviews, win_count, loss_count,
                     holding_count, total_pnl_pct, summary,
                     info_review_summary, info_review_details, created_at)
                VALUES
                    ('daily-1', '2026-03-21', 3, 2, 1, 0, 0.0375,
                     '日复盘：执行较稳', '信息复盘：有效信号占优',
                     '{"digest_count":3,"useful_count":2}', '2026-03-21T16:10:00')
                """
            )
        )

        resp = self.client.get("/api/v1/agent/reflections?limit=5")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["kind"] == "daily"
        assert body[0]["summary"] == "日复盘：执行较稳"
        assert body[0]["details"]["info_review"]["summary"] == "信息复盘：有效信号占优"
