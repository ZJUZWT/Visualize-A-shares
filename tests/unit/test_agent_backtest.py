"""Agent backtest bootstrap unit tests."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import asyncio
import duckdb
import pandas as pd
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

    validator = TradeValidator()
    validator.SLIPPAGE_BUY = 0.0
    validator.SLIPPAGE_SELL = 0.0
    validator.COMMISSION_RATE = 0.0
    validator.MIN_COMMISSION = 0.0
    validator.STAMP_TAX_RATE = 0.0
    validator.TRANSFER_FEE_RATE = 0.0
    svc = AgentService(db=db, validator=validator)
    return db, svc, db_path


class FakeDataEngine:
    def __init__(self, history_by_code):
        self.history_by_code = history_by_code

    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        rows = []
        for row in self.history_by_code.get(code, []):
            if start <= row["date"] <= end:
                rows.append(row)
        return pd.DataFrame(rows)


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


class TestAgentBacktestRun:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc, self.db_path = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0, "2026-03-18"))

    def teardown_method(self):
        self.db.close()

    @staticmethod
    def _history_by_code():
        return {
            "600519": [
                {"date": "2026-03-18", "open": 99.0, "close": 100.0},
                {"date": "2026-03-19", "open": 101.0, "close": 102.0},
                {"date": "2026-03-20", "open": 103.0, "close": 104.0},
            ]
        }

    @staticmethod
    def _history_with_non_trading_gap():
        return {
            "600519": [
                {"date": "2026-03-18", "open": 99.0, "close": 100.0},
                {"date": "2026-03-20", "open": 103.0, "close": 104.0},
            ]
        }

    def test_run_backtest_writes_daily_rows_for_each_trade_day(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.models import WatchlistInput

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                portfolio = await self_ref.svc.get_portfolio(self.portfolio_id)
                trade_day = portfolio["config"]["sim_current_date"]
                decisions = []
                if trade_day == "2026-03-18":
                    decisions.append(
                        {
                            "action": "buy",
                            "stock_code": "600519",
                            "stock_name": "贵州茅台",
                            "quantity": 100,
                            "holding_type": "mid_term",
                            "reasoning": "首日建仓",
                            "risk_note": "test risk",
                            "invalidation": "test invalidation",
                        }
                    )
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "decisions": decisions,
                    },
                )

        run(
            self.svc.add_watchlist(
                WatchlistInput(stock_code="600519", stock_name="贵州茅台")
            )
        )
        self_ref = self
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            result = run(
                engine.run_backtest(
                    portfolio_id="live",
                    start_date="2026-03-18",
                    end_date="2026-03-20",
                )
            )

        rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.backtest_days WHERE run_id = ? ORDER BY trade_date",
                [result["id"]],
            )
        )
        assert result["status"] == "completed"
        assert len(result["days"]) == 3
        assert len(rows) == 3
        assert [row["trade_date"] for row in rows] == [
            "2026-03-18",
            "2026-03-19",
            "2026-03-20",
        ]

    def test_same_close_execution_uses_same_day_close(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.models import WatchlistInput

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "decisions": [
                            {
                                "action": "buy",
                                "stock_code": "600519",
                                "stock_name": "贵州茅台",
                                "quantity": 100,
                                "holding_type": "mid_term",
                                "reasoning": "same close",
                                "risk_note": "test risk",
                                "invalidation": "test invalidation",
                            }
                        ],
                    },
                )

        run(
            self.svc.add_watchlist(
                WatchlistInput(stock_code="600519", stock_name="贵州茅台")
            )
        )
        self_ref = self
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            result = run(
                engine.run_backtest(
                    portfolio_id="live",
                    start_date="2026-03-18",
                    end_date="2026-03-18",
                    execution_price_mode="same_close",
                )
            )

        assert len(result["trades"]) == 1
        assert result["trades"][0]["price"] == 100.0

    def test_next_open_execution_uses_next_day_open(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.models import WatchlistInput

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "decisions": [
                            {
                                "action": "buy",
                                "stock_code": "600519",
                                "stock_name": "贵州茅台",
                                "quantity": 100,
                                "holding_type": "mid_term",
                                "reasoning": "next open",
                                "risk_note": "test risk",
                                "invalidation": "test invalidation",
                            }
                        ],
                    },
                )

        run(
            self.svc.add_watchlist(
                WatchlistInput(stock_code="600519", stock_name="贵州茅台")
            )
        )
        self_ref = self
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            result = run(
                engine.run_backtest(
                    portfolio_id="live",
                    start_date="2026-03-18",
                    end_date="2026-03-18",
                    execution_price_mode="next_open",
                )
            )

        assert len(result["trades"]) == 1
        assert result["trades"][0]["price"] == 101.0

    def test_run_backtest_skips_non_trading_calendar_days(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.models import WatchlistInput

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "decisions": [],
                    },
                )

        run(
            self.svc.add_watchlist(
                WatchlistInput(stock_code="600519", stock_name="贵州茅台")
            )
        )

        self_ref = self
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_with_non_trading_gap()),
        ):
            result = run(
                engine.run_backtest(
                    portfolio_id="live",
                    start_date="2026-03-18",
                    end_date="2026-03-20",
                )
            )

        rows = run(
            self.db.execute_read(
                "SELECT trade_date FROM agent.backtest_days WHERE run_id = ? ORDER BY trade_date",
                [result["id"]],
            )
        )
        assert [row["trade_date"] for row in rows] == [
            "2026-03-18",
            "2026-03-20",
        ]
        assert [item["date"] for item in result["days"]] == [
            "2026-03-18",
            "2026-03-20",
        ]

    def test_run_backtest_without_source_symbols_uses_no_calendar_fallback(self):
        from engine.agent.backtest import AgentBacktestEngine

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "decisions": [],
                    },
                )

        self_ref = self
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            result = run(
                engine.run_backtest(
                    portfolio_id="live",
                    start_date="2026-03-18",
                    end_date="2026-03-20",
                )
            )

        rows = run(
            self.db.execute_read(
                "SELECT trade_date FROM agent.backtest_days WHERE run_id = ? ORDER BY trade_date",
                [result["id"]],
            )
        )
        assert rows == []
        assert result["days"] == []
