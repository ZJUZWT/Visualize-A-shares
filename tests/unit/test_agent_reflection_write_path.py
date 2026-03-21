"""Agent reflection write path tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
from datetime import date
import tempfile

import duckdb
from unittest.mock import patch


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_db(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()
    return db, db_path


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


class TestReflectionWriteTables:
    def test_daily_and_weekly_reflection_tables_exist(self, tmp_path):
        db, db_path = _make_db(tmp_path)

        conn = duckdb.connect(str(db_path))
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='agent'"
        ).fetchall()
        conn.close()
        db.close()

        table_names = {row[0] for row in tables}
        assert "daily_reviews" in table_names
        assert "weekly_reflections" in table_names


class TestReflectionWriteModels:
    def test_daily_review_model_defaults(self):
        from engine.agent.models import DailyReview

        record = DailyReview(
            id="daily-1",
            review_date="2026-03-22",
            created_at="2026-03-22T16:00:00",
        )

        assert record.total_reviews == 0
        assert record.win_count == 0
        assert record.loss_count == 0
        assert record.holding_count == 0
        assert record.total_pnl_pct == 0.0
        assert record.summary is None

    def test_weekly_reflection_model_defaults(self):
        from engine.agent.models import WeeklyReflection

        record = WeeklyReflection(
            id="weekly-reflection-1",
            week_start="2026-03-16",
            week_end="2026-03-20",
            created_at="2026-03-22T16:00:00",
        )

        assert record.total_reviews == 0
        assert record.win_rate == 0.0
        assert record.summary is None


class TestReflectionWritePath:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_daily_review_writes_journal_and_trade_backfill_idempotently(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        trade = run(
            self.svc.execute_trade(
                "live",
                self._make_trade_input(),
                date.today().isoformat(),
                source_run_id="run-1",
            )
        )["trade"]
        run_record = run(self.svc.create_brain_run("live", "manual"))
        run(
            self.svc.update_brain_run(
                run_record["id"],
                {"status": "completed", "trade_ids": [trade["id"]]},
            )
        )

        engine = ReviewEngine(db=self.db, memory_mgr=MemoryManager(self.db))

        first = run(engine.daily_review())
        second = run(engine.daily_review())

        daily_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.daily_reviews WHERE review_date = ?",
                [date.today().isoformat()],
            )
        )
        trade_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.trades WHERE id = ?",
                [trade["id"]],
            )
        )

        assert first["status"] == "completed"
        assert first["records_created"] == 1
        assert second["records_created"] == 0
        assert len(daily_rows) == 1
        assert daily_rows[0]["total_reviews"] == 1
        assert trade_rows[0]["review_result"] == "holding"
        assert trade_rows[0]["review_date"] is not None
        assert trade_rows[0]["review_note"] is not None
        assert trade_rows[0]["pnl_at_review"] == 0.0

    def test_weekly_review_writes_reflection_idempotently(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        run(
            self.db.execute_write(
                """
                INSERT INTO agent.review_records (
                    id, brain_run_id, trade_id, stock_code, stock_name, action,
                    decision_price, review_price, pnl_pct, holding_days,
                    status, review_date, review_type
                )
                VALUES
                    ('review-1', 'run-1', 'trade-1', '600519', '贵州茅台', 'buy',
                     1800.0, 1764.0, -0.02, 3, 'loss', '2026-03-16', 'daily'),
                    ('review-2', 'run-2', 'trade-2', '601318', '中国平安', 'buy',
                     50.0, 49.0, -0.02, 2, 'loss', '2026-03-18', 'daily'),
                    ('review-3', 'run-3', 'trade-3', '000858', '五粮液', 'buy',
                     140.0, 142.8, 0.02, 2, 'win', '2026-03-19', 'daily')
                """
            )
        )

        engine = ReviewEngine(db=self.db, memory_mgr=MemoryManager(self.db))

        first = run(engine.weekly_review(as_of_date="2026-03-20"))
        second = run(engine.weekly_review(as_of_date="2026-03-20"))

        rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.weekly_reflections WHERE week_start = '2026-03-16'"
            )
        )

        assert first["status"] == "completed"
        assert len(rows) == 1
        assert rows[0]["total_reviews"] == 3
        assert rows[0]["loss_count"] == 2
        assert rows[0]["win_count"] == 1
        assert second["reflection_id"] == rows[0]["id"]

    @staticmethod
    def _make_trade_input():
        from engine.agent.models import TradeInput

        return TradeInput(
            action="buy",
            stock_code="600519",
            price=1800.0,
            quantity=100,
            holding_type="mid_term",
            reason="景气修复",
            thesis="基本面改善",
            data_basis=["营收修复"],
            risk_note="估值偏高",
            invalidation="景气转弱",
            triggered_by="agent",
        )
