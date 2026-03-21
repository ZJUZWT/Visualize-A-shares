"""Agent review/memory read model tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
from datetime import date, datetime, timedelta
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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


def _seed_review_record(db, *, review_id: str, run_id: str, trade_id: str, stock_code: str,
                        stock_name: str, action: str, pnl_pct: float, review_date: date,
                        review_type: str):
    run(
        db.execute_write(
            """
            INSERT INTO agent.review_records (
                id, brain_run_id, trade_id, stock_code, stock_name, action,
                decision_price, review_price, pnl_pct, holding_days, status,
                review_date, review_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                review_id,
                run_id,
                trade_id,
                stock_code,
                stock_name,
                action,
                100.0,
                110.0,
                pnl_pct,
                3,
                "win" if pnl_pct > 0 else "loss" if pnl_pct < 0 else "holding",
                review_date.isoformat(),
                review_type,
                datetime.now().isoformat(),
            ],
        )
    )


class TestReviewReadModelsService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        self.portfolio_id = "portfolio_1"
        run(self.svc.create_portfolio(self.portfolio_id, "live", 1000000))
        self.run_id = run(self.svc.create_brain_run(self.portfolio_id, "manual"))["id"]
        self.other_run_id = run(self.svc.create_brain_run("portfolio_2", "manual"))["id"]

    def teardown_method(self):
        self.db.close()

    def test_list_review_records_filters_by_portfolio_days_and_type(self):
        today = date.today()
        _seed_review_record(
            self.db,
            review_id="review-1",
            run_id=self.run_id,
            trade_id="trade-1",
            stock_code="600519",
            stock_name="贵州茅台",
            action="buy",
            pnl_pct=0.12,
            review_date=today,
            review_type="daily",
        )
        _seed_review_record(
            self.db,
            review_id="review-2",
            run_id=self.run_id,
            trade_id="trade-2",
            stock_code="601318",
            stock_name="中国平安",
            action="sell",
            pnl_pct=-0.05,
            review_date=today - timedelta(days=10),
            review_type="weekly",
        )
        _seed_review_record(
            self.db,
            review_id="review-3",
            run_id=self.other_run_id,
            trade_id="trade-3",
            stock_code="000001",
            stock_name="平安银行",
            action="buy",
            pnl_pct=0.2,
            review_date=today,
            review_type="daily",
        )

        rows = run(self.svc.list_review_records(self.portfolio_id, days=7, review_type="daily"))

        assert len(rows) == 1
        assert rows[0]["id"] == "review-1"
        assert rows[0]["portfolio_id"] == self.portfolio_id
        assert rows[0]["review_type"] == "daily"
        assert isinstance(rows[0]["review_date"], str)

    def test_get_review_stats_summarizes_filtered_records(self):
        today = date.today()
        _seed_review_record(
            self.db,
            review_id="review-1",
            run_id=self.run_id,
            trade_id="trade-1",
            stock_code="600519",
            stock_name="贵州茅台",
            action="buy",
            pnl_pct=0.12,
            review_date=today,
            review_type="daily",
        )
        _seed_review_record(
            self.db,
            review_id="review-2",
            run_id=self.run_id,
            trade_id="trade-2",
            stock_code="601318",
            stock_name="中国平安",
            action="sell",
            pnl_pct=-0.02,
            review_date=today - timedelta(days=1),
            review_type="daily",
        )

        stats = run(self.svc.get_review_stats(self.portfolio_id, days=7))

        assert stats["portfolio_id"] == self.portfolio_id
        assert stats["total_reviews"] == 2
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 1
        assert stats["holding_count"] == 0
        assert stats["win_rate"] == 0.5
        assert stats["total_pnl_pct"] == 0.1
        assert stats["avg_pnl_pct"] == 0.05
        assert stats["best_review"]["id"] == "review-1"
        assert stats["worst_review"]["id"] == "review-2"

    def test_list_weekly_summaries_honors_limit(self):
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.weekly_summaries (
                    id, week_start, week_end, total_trades, win_count, loss_count,
                    win_rate, total_pnl_pct, best_trade_id, worst_trade_id, insights, created_at
                )
                VALUES
                    ('weekly-1', '2026-03-16', '2026-03-20', 4, 3, 1, 0.75, 0.18, 'trade-1', 'trade-2', 'week 1', ?),
                    ('weekly-2', '2026-03-09', '2026-03-13', 5, 2, 3, 0.40, -0.06, 'trade-3', 'trade-4', 'week 2', ?)
                """,
                [datetime.now().isoformat(), datetime.now().isoformat()],
            )
        )

        rows = run(self.svc.list_weekly_summaries(limit=1))

        assert len(rows) == 1
        assert rows[0]["id"] == "weekly-1"
        assert rows[0]["week_start"] == "2026-03-16"

    def test_list_memories_supports_all_status(self):
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.agent_memories (
                    id, rule_text, category, source_run_id, status, confidence,
                    verify_count, verify_win, created_at, retired_at
                )
                VALUES
                    ('memory-1', '不要追高', 'timing', 'run-1', 'active', 0.8, 5, 4, ?, NULL),
                    ('memory-2', '跌破止损立即卖', 'risk', 'run-2', 'retired', 0.2, 5, 1, ?, ?)
                """,
                [datetime.now().isoformat(), datetime.now().isoformat(), datetime.now().isoformat()],
            )
        )

        rows = run(self.svc.list_memories(status="all"))

        assert len(rows) == 2
        assert {row["status"] for row in rows} == {"active", "retired"}
        assert isinstance(rows[0]["created_at"], str)


class TestReviewReadModelsRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

        from engine.agent.validator import TradeValidator
        from engine.agent.service import AgentService

        self.svc = AgentService(db=self.db, validator=TradeValidator())
        self.portfolio_id = "portfolio_1"
        run(self.svc.create_portfolio(self.portfolio_id, "live", 1000000))
        self.run_id = run(self.svc.create_brain_run(self.portfolio_id, "manual"))["id"]

        today = date.today()
        _seed_review_record(
            self.db,
            review_id="review-1",
            run_id=self.run_id,
            trade_id="trade-1",
            stock_code="600519",
            stock_name="贵州茅台",
            action="buy",
            pnl_pct=0.1,
            review_date=today,
            review_type="daily",
        )
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.weekly_summaries (
                    id, week_start, week_end, total_trades, win_count, loss_count,
                    win_rate, total_pnl_pct, best_trade_id, worst_trade_id, insights, created_at
                )
                VALUES ('weekly-1', '2026-03-16', '2026-03-20', 4, 3, 1, 0.75, 0.18, 'trade-1', 'trade-2', 'week 1', ?)
                """,
                [datetime.now().isoformat()],
            )
        )
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.agent_memories (
                    id, rule_text, category, source_run_id, status, confidence,
                    verify_count, verify_win, created_at, retired_at
                )
                VALUES
                    ('memory-1', '不要追高', 'timing', 'run-1', 'active', 0.8, 5, 4, ?, NULL),
                    ('memory-2', '跌破止损立即卖', 'risk', 'run-2', 'retired', 0.2, 5, 1, ?, ?)
                """,
                [datetime.now().isoformat(), datetime.now().isoformat(), datetime.now().isoformat()],
            )
        )

    def teardown_method(self):
        self.db.close()

    def test_get_reviews(self):
        resp = self.client.get(f"/api/v1/agent/reviews?portfolio_id={self.portfolio_id}&days=7&type=daily")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) == 1
        assert payload[0]["id"] == "review-1"

    def test_get_review_stats(self):
        resp = self.client.get(f"/api/v1/agent/reviews/stats?portfolio_id={self.portfolio_id}&days=7")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total_reviews"] == 1
        assert payload["win_rate"] == 1.0

    def test_get_weekly_reviews(self):
        resp = self.client.get("/api/v1/agent/reviews/weekly?limit=10")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) == 1
        assert payload[0]["id"] == "weekly-1"

    def test_get_memories_with_all_status(self):
        resp = self.client.get("/api/v1/agent/memories?status=all")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) == 2
        assert {item["status"] for item in payload} == {"active", "retired"}
