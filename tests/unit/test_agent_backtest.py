"""Agent backtest bootstrap unit tests."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import asyncio
import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


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
    return db, svc, db_path


class TestAgentBacktestBootstrap:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc, self.db_path = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0, "2026-03-18"))

    def teardown_method(self):
        self.db.close()

    def test_agent_db_creates_backtest_tables(self):
        conn = duckdb.connect(str(self.db_path))
        rows = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'agent'
            ORDER BY table_name
            """
        ).fetchall()
        conn.close()

        table_names = {row[0] for row in rows}
        assert "backtest_runs" in table_names
        assert "backtest_days" in table_names

    def test_start_run_creates_backtest_run_record(self):
        from engine.agent.backtest import AgentBacktestEngine

        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        run_record = run(
            engine.start_run(
                portfolio_id="live",
                start_date="2026-03-18",
                end_date="2026-03-21",
                execution_price_mode="next_open",
            )
        )

        rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.backtest_runs WHERE id = ?",
                [run_record["id"]],
            )
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "running"
        assert rows[0]["source_portfolio_id"] == "live"
        assert rows[0]["backtest_portfolio_id"] == run_record["backtest_portfolio_id"]

    def test_start_run_copies_source_portfolio_into_isolated_backtest_portfolio(self):
        from engine.agent.backtest import AgentBacktestEngine

        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        run_record = run(
            engine.start_run(
                portfolio_id="live",
                start_date="2026-03-18",
                end_date="2026-03-21",
                execution_price_mode="next_open",
            )
        )

        backtest_portfolio_id = run_record["backtest_portfolio_id"]
        backtest_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.portfolio_config WHERE id = ?",
                [backtest_portfolio_id],
            )
        )
        source_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.portfolio_config WHERE id = ?",
                ["live"],
            )
        )

        assert backtest_portfolio_id.startswith("bt:")
        assert len(backtest_rows) == 1
        assert len(source_rows) == 1
        assert backtest_rows[0]["mode"] == "training"
        assert backtest_rows[0]["initial_capital"] == source_rows[0]["initial_capital"]
        assert backtest_rows[0]["cash_balance"] == source_rows[0]["cash_balance"]
        assert backtest_rows[0]["sim_start_date"] == source_rows[0]["sim_start_date"]
        assert backtest_rows[0]["sim_current_date"] == source_rows[0]["sim_current_date"]

    def test_start_run_rolls_back_isolated_portfolio_when_run_insert_fails(self):
        from engine.agent.backtest import AgentBacktestEngine

        run_id = "fixed-run"
        backtest_portfolio_id = f"bt:{run_id}"
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.backtest_runs
                (
                    id,
                    source_portfolio_id,
                    backtest_portfolio_id,
                    start_date,
                    end_date,
                    execution_price_mode,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    "existing",
                    "bt:existing",
                    "2026-03-10",
                    "2026-03-11",
                    "next_open",
                    "running",
                ],
            )
        )

        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.uuid.uuid4", return_value=run_id):
            with pytest.raises(Exception):
                run(
                    engine.start_run(
                        portfolio_id="live",
                        start_date="2026-03-18",
                        end_date="2026-03-21",
                        execution_price_mode="next_open",
                    )
                )

        backtest_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.portfolio_config WHERE id = ?",
                [backtest_portfolio_id],
            )
        )
        assert backtest_rows == []
