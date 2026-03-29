"""Agent backtest bootstrap unit tests."""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import asyncio
import duckdb
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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


class FakeDataEngine:
    def __init__(self, history_by_code):
        self.history_by_code = history_by_code
        self.requested_ranges = []

    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        self.requested_ranges.append(
            {
                "code": code,
                "start": start,
                "end": end,
            }
        )
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

    @staticmethod
    def _history_with_unrelated_watchlist_symbol():
        return {
            "600519": [
                {"date": "2026-03-18", "open": 99.0, "close": 100.0},
                {"date": "2026-03-20", "open": 103.0, "close": 104.0},
            ],
            "000001": [
                {"date": "2026-03-19", "open": 10.0, "close": 10.2},
            ],
        }

    def _seed_source_trade(self):
        from engine.agent.models import TradeInput

        run(
            self.svc.execute_trade(
                "live",
                TradeInput(
                    action="buy",
                    stock_code="600519",
                    stock_name="贵州茅台",
                    price=100.0,
                    quantity=100,
                    holding_type="mid_term",
                    reason="source seed",
                    thesis="source seed",
                    data_basis=["seed"],
                    risk_note="seed",
                    invalidation="seed",
                    triggered_by="manual",
                ),
                "2026-03-17",
            )
        )

    def test_start_run_copies_source_context_needed_for_agent_execution(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.models import WatchlistInput

        self._seed_source_trade()
        source_position = run(self.svc.get_positions("live", "open"))[0]
        run(
            self.svc.create_strategy(
                "live",
                source_position["id"],
                {
                    "take_profit": 120.0,
                    "stop_loss": 95.0,
                    "reasoning": "source strategy",
                    "details": {"source": "test"},
                },
            )
        )
        run(
            self.svc.add_watchlist(
                WatchlistInput(
                    stock_code="600519",
                    stock_name="贵州茅台",
                    reason="source watch",
                ),
                portfolio_id="live",
            )
        )
        run(
            self.svc.update_agent_state(
                "live",
                {
                    "market_view": {"stance": "risk-on"},
                    "position_level": 0.35,
                    "sector_preferences": ["consumer"],
                    "risk_alerts": ["unit-test"],
                },
            )
        )

        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        run_record = run(
            engine.start_run(
                portfolio_id="live",
                start_date="2026-03-18",
                end_date="2026-03-20",
            )
        )

        backtest_portfolio_id = run_record["backtest_portfolio_id"]
        backtest_positions = run(self.svc.get_positions(backtest_portfolio_id, "open"))
        backtest_watchlist = run(self.svc.list_watchlist(portfolio_id=backtest_portfolio_id))
        backtest_state = run(self.svc.get_agent_state(backtest_portfolio_id))
        backtest_strategies = run(
            self.svc.get_strategy(backtest_portfolio_id, backtest_positions[0]["id"])
        )

        assert len(backtest_positions) == 1
        assert backtest_positions[0]["stock_code"] == "600519"
        assert len(backtest_watchlist) == 1
        assert backtest_watchlist[0]["stock_code"] == "600519"
        assert backtest_state["market_view"] == {"stance": "risk-on"}
        assert float(backtest_state["position_level"]) == 0.35
        assert len(backtest_strategies) == 1
        assert backtest_strategies[0]["take_profit"] == 120.0

    def test_run_backtest_writes_daily_rows_for_each_trade_day(self):
        from engine.agent.backtest import AgentBacktestEngine

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

        self._seed_source_trade()
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

        self._seed_source_trade()
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

        self._seed_source_trade()
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
                            "reasoning": "summary isolation",
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

        self._seed_source_trade()

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

    def test_run_backtest_uses_watchlist_symbols_when_source_has_no_positions_or_trades(self):
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
                WatchlistInput(
                    stock_code="600519",
                    stock_name="贵州茅台",
                    reason="watchlist-only backtest",
                ),
                portfolio_id="live",
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
                "SELECT trade_date FROM agent.backtest_days WHERE run_id = ? ORDER BY trade_date",
                [result["id"]],
            )
        )
        assert [row["trade_date"] for row in rows] == [
            "2026-03-18",
            "2026-03-19",
            "2026-03-20",
        ]
        assert [item["date"] for item in result["days"]] == [
            "2026-03-18",
            "2026-03-19",
            "2026-03-20",
        ]

    def test_run_backtest_brain_run_tracks_executed_plan_and_trade_ids(self):
        from engine.agent.backtest import AgentBacktestEngine

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
                                "reasoning": "sync ids",
                                "risk_note": "test risk",
                                "invalidation": "test invalidation",
                            }
                        ],
                        "execution_summary": {"trade_count": 0, "plan_count": 0},
                    },
                )

        self._seed_source_trade()
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

        run_rows = run(
            self.db.execute_read(
                "SELECT backtest_portfolio_id FROM agent.backtest_runs WHERE id = ?",
                [result["id"]],
            )
        )
        backtest_portfolio_id = run_rows[0]["backtest_portfolio_id"]
        brain_runs = run(self.svc.list_brain_runs(backtest_portfolio_id, limit=10))
        brain_run = brain_runs[0]
        assert len(brain_run.get("plan_ids") or []) == 1
        assert len(brain_run.get("trade_ids") or []) == 1
        assert brain_run["trade_ids"][0] == result["trades"][0]["id"]
        summary = brain_run.get("execution_summary") or {}
        assert summary.get("plan_count") == 1
        assert summary.get("trade_count") == 1

    def test_run_backtest_ignores_unrelated_global_watchlist_symbols(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.models import WatchlistInput

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {"status": "completed", "decisions": []},
                )

        self._seed_source_trade()
        run(
            self.svc.add_watchlist(
                WatchlistInput(stock_code="000001", stock_name="平安银行")
            )
        )
        self_ref = self
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_with_unrelated_watchlist_symbol()),
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

    def test_backtest_freezes_market_context_at_trade_date(self):
        from engine.agent.backtest import AgentBacktestEngine

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                from engine.data import get_data_engine

                portfolio = await self_ref.svc.get_portfolio(self.portfolio_id)
                trade_day = portfolio["config"]["sim_current_date"]
                get_data_engine().get_daily_history("300750", "2026-01-01", "2099-12-31")
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "decisions": [],
                        "thinking_process": {
                            "observed_trade_day": trade_day,
                        },
                    },
                )

        self._seed_source_trade()
        self_ref = self
        fake_engine = FakeDataEngine(
            {
                **self._history_by_code(),
                "300750": [
                    {"date": "2026-03-18", "open": 50.0, "close": 51.0},
                    {"date": "2026-03-19", "open": 52.0, "close": 53.0},
                    {"date": "2026-03-20", "open": 54.0, "close": 55.0},
                ],
            }
        )
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=fake_engine,
        ), patch(
            "engine.data.get_data_engine",
            return_value=fake_engine,
        ):
            run(
                engine.run_backtest(
                    portfolio_id="live",
                    start_date="2026-03-18",
                    end_date="2026-03-20",
                )
            )

        freeze_requests = [
            request for request in fake_engine.requested_ranges
            if request["code"] == "300750"
        ]
        assert len(freeze_requests) == 3
        assert [request["end"] for request in freeze_requests] == [
            "2026-03-18",
            "2026-03-19",
            "2026-03-20",
        ]

    def test_historical_market_context_clamps_real_agent_analysis_quant_path(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.brain import AgentBrain

        class FakeQuantEngine:
            @staticmethod
            def compute_indicators(daily):
                return {"bars": len(daily)}

        fake_engine = FakeDataEngine(
            {
                "300750": [
                    {"date": "2026-03-18", "open": 50.0, "close": 51.0},
                    {"date": "2026-03-19", "open": 52.0, "close": 53.0},
                    {"date": "2026-03-20", "open": 54.0, "close": 55.0},
                ],
            }
        )
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.get_data_engine", return_value=fake_engine), patch(
            "engine.quant.get_quant_engine",
            return_value=FakeQuantEngine(),
        ), patch(
            "engine.cluster.get_cluster_engine",
            return_value=object(),
        ), patch(
            "llm.LLMProviderFactory.create",
            return_value=object(),
        ):
            brain = AgentBrain("live")
            with engine._with_historical_market_context("2026-03-20"):
                analysis = run(brain._analyze_single("300750"))

        quant_requests = [
            request for request in fake_engine.requested_ranges
            if request["code"] == "300750"
        ]
        indicators = json.loads(analysis["indicators"])
        assert indicators["as_of_date"] == "2026-03-20"
        assert quant_requests[-1]["end"] == "2026-03-20"

    def test_historical_market_context_quant_screen_uses_snapshot_as_of(self):
        from engine.agent.backtest import AgentBacktestEngine
        from engine.agent.brain import AgentBrain
        from engine.quant.predictor import PredictionResult

        class FakeDataEngineWithSnapshotAsOf:
            def __init__(self):
                self.snapshot_as_of_requests = []

            def get_snapshot(self):
                return pd.DataFrame([{"code": "FUTURE", "pct_chg": 99.0}])

            def get_snapshot_as_of(self, as_of_date: str):
                self.snapshot_as_of_requests.append(as_of_date)
                return pd.DataFrame(
                    [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "date": as_of_date,
                            "price": 1805.0,
                            "pct_chg": 0.8,
                            "volume": 12345,
                            "amount": 2.2e7,
                            "turnover_rate": 0.3,
                        }
                    ]
                )

        class FakeQuantEngine:
            def __init__(self):
                self.last_snapshot = None

            def predict(self, snapshot_df, cluster_labels=None, daily_df_map=None):
                self.last_snapshot = snapshot_df.copy()
                return PredictionResult(predictions={"600519": 0.9123}, total_count=len(snapshot_df))

        fake_engine = FakeDataEngineWithSnapshotAsOf()
        fake_quant = FakeQuantEngine()
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        brain = AgentBrain("live")

        with patch("engine.agent.backtest.get_data_engine", return_value=fake_engine), patch(
            "engine.quant.get_quant_engine",
            return_value=fake_quant,
        ):
            with engine._with_historical_market_context("2026-03-20"):
                candidates = run(brain._quant_screen(20))

        assert fake_engine.snapshot_as_of_requests == ["2026-03-20"]
        assert list(fake_quant.last_snapshot["code"]) == ["600519"]
        assert candidates == [
            {
                "stock_code": "600519",
                "score": 0.9123,
                "stock_name": "贵州茅台",
            }
        ]

    def test_backtest_records_review_and_memory_deltas(self):
        from engine.agent.backtest import AgentBacktestEngine

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
                            "reasoning": "review evolution",
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

        self._seed_source_trade()
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.agent_memories (
                    id, rule_text, category, source_run_id, status, confidence, verify_count, verify_win
                )
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                [
                    "rule-retire",
                    "低胜率规则待淘汰",
                    "risk",
                    "seed-run",
                    0.4,
                    3,
                    1,
                ],
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
                    execution_price_mode="same_close",
                )
            )

        daily_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.daily_reviews ORDER BY review_date",
            )
        )
        weekly_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.weekly_summaries ORDER BY week_start",
            )
        )
        backtest_day_rows = run(
            self.db.execute_read(
                """
                SELECT trade_date, review_created, memory_delta
                FROM agent.backtest_days
                WHERE run_id = ?
                ORDER BY trade_date
                """,
                [result["id"]],
            )
        )

        assert len(daily_rows) == 3
        assert len(weekly_rows) == 1
        assert [row["trade_date"] for row in backtest_day_rows] == [
            "2026-03-18",
            "2026-03-19",
            "2026-03-20",
        ]
        assert all(row["review_created"] for row in backtest_day_rows)
        assert backtest_day_rows[-1]["memory_delta"] == {
            "active": 0,
            "retired": 0,
            "total": 0,
        }

    def test_backtest_runs_weekly_review_only_on_week_anchor_days(self):
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

        self._seed_source_trade()
        self_ref = self
        engine = AgentBacktestEngine(db=self.db, service=self.svc)
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            run(
                engine.run_backtest(
                    portfolio_id="live",
                    start_date="2026-03-18",
                    end_date="2026-03-19",
                    execution_price_mode="same_close",
                )
            )

        daily_rows = run(
            self.db.execute_read(
                "SELECT review_date FROM agent.daily_reviews ORDER BY review_date",
            )
        )
        weekly_rows = run(
            self.db.execute_read(
                "SELECT week_start, week_end FROM agent.weekly_summaries ORDER BY week_start",
            )
        )
        assert [row["review_date"] for row in daily_rows] == [
            "2026-03-18",
            "2026-03-19",
        ]
        assert weekly_rows == []

    def test_get_run_summary_avoids_service_level_market_data_loader(self):
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

        self._seed_source_trade()
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
                    execution_price_mode="same_close",
                )
            )

        with patch(
            "engine.agent.service.get_data_engine",
            side_effect=AssertionError("service-level data loader should not be used"),
            create=True,
        ), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            summary = run(engine.get_run_summary(result["id"]))

        assert summary["run_id"] == result["id"]


class TestAgentBacktestRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

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

    def _create_portfolio_and_seed_trade(self):
        from engine.agent.validator import TradeValidator
        from engine.agent.service import AgentService
        from engine.agent.models import TradeInput

        validator = TradeValidator()
        validator.SLIPPAGE_BUY = 0.0
        validator.SLIPPAGE_SELL = 0.0
        validator.COMMISSION_RATE = 0.0
        validator.MIN_COMMISSION = 0.0
        validator.STAMP_TAX_RATE = 0.0
        validator.TRANSFER_FEE_RATE = 0.0
        svc = AgentService(db=self.db, validator=validator)
        run(svc.create_portfolio("live", "live", 1000000.0, "2026-03-18"))
        run(
            svc.execute_trade(
                "live",
                TradeInput(
                    action="buy",
                    stock_code="600519",
                    stock_name="贵州茅台",
                    price=100.0,
                    quantity=100,
                    holding_type="mid_term",
                    reason="source seed",
                    thesis="source seed",
                    data_basis=["seed"],
                    risk_note="seed",
                    invalidation="seed",
                    triggered_by="manual",
                ),
                "2026-03-17",
            )
        )

    def test_backtest_summary_route_returns_metrics_and_days_route_returns_sorted_rows(self):
        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                from engine.agent.validator import TradeValidator
                from engine.agent.service import AgentService
                svc = AgentService(db=self_ref.db, validator=TradeValidator())
                portfolio = await svc.get_portfolio(self.portfolio_id)
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
                            "reasoning": "route test",
                            "risk_note": "test risk",
                            "invalidation": "test invalidation",
                        }
                    )
                await svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "decisions": decisions,
                    },
                )

        self._create_portfolio_and_seed_trade()
        self_ref = self
        with patch("engine.agent.backtest.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            create_resp = self.client.post(
                "/api/v1/agent/backtest/run",
                json={
                    "portfolio_id": "live",
                    "start_date": "2026-03-18",
                    "end_date": "2026-03-20",
                    "execution_price_mode": "same_close",
                },
            )

        assert create_resp.status_code == 200
        create_payload = create_resp.json()
        assert set(create_payload.keys()) >= {"run_id", "status"}
        run_id = create_payload["run_id"]

        with patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ), patch(
            "engine.data.get_data_engine",
            return_value=FakeDataEngine(self._history_by_code()),
        ):
            summary_resp = self.client.get(f"/api/v1/agent/backtest/run/{run_id}")
            days_resp = self.client.get(f"/api/v1/agent/backtest/run/{run_id}/days")

        assert summary_resp.status_code == 200
        summary = summary_resp.json()
        assert summary["run_id"] == run_id
        assert summary["trade_count"] == 1
        assert summary["review_count"] == 4
        assert "total_return" in summary
        assert "max_drawdown" in summary
        assert "win_rate" in summary
        assert "memory_added" in summary
        assert "memory_updated" in summary
        assert "memory_retired" in summary
        assert "buy_and_hold_return" in summary

        assert days_resp.status_code == 200
        days = days_resp.json()
        assert [row["trade_date"] for row in days] == [
            "2026-03-18",
            "2026-03-19",
            "2026-03-20",
        ]

    def test_backtest_summary_route_returns_404_for_missing_run(self):
        resp = self.client.get("/api/v1/agent/backtest/run/missing-run")
        assert resp.status_code == 404

    def test_backtest_run_route_returns_404_for_missing_portfolio(self):
        resp = self.client.post(
            "/api/v1/agent/backtest/run",
            json={
                "portfolio_id": "missing",
                "start_date": "2026-03-18",
                "end_date": "2026-03-20",
            },
        )
        assert resp.status_code == 404

    def test_backtest_run_route_returns_400_for_invalid_date_range(self):
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "live", "mode": "live", "initial_capital": 1000000.0, "sim_start_date": "2026-03-18"},
        )
        resp = self.client.post(
            "/api/v1/agent/backtest/run",
            json={
                "portfolio_id": "live",
                "start_date": "2026-03-20",
                "end_date": "2026-03-18",
            },
        )
        assert resp.status_code == 400


class TestBacktestServiceIsolation:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc, _ = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_service_price_history_loader_uses_dynamic_engine_binding(self):
        class FakeDataEngine:
            def get_daily_history(self, code: str, start: str, end: str):
                return pd.DataFrame(
                    [
                        {"date": "2026-03-18", "close": 100.0},
                        {"date": "2026-03-19", "close": 101.0},
                    ]
                )

        with patch(
            "engine.agent.service.get_data_engine",
            side_effect=AssertionError("stale service binding should not be used"),
            create=True,
        ), patch(
            "engine.data.get_data_engine",
            return_value=FakeDataEngine(),
        ):
            history = run(
                self.svc._load_price_history(
                    ["600519"],
                    date.fromisoformat("2026-03-18"),
                    date.fromisoformat("2026-03-19"),
                )
            )

        assert history["600519"]["2026-03-18"] == 100.0

    def test_service_price_history_loader_prefers_local_store_without_network_refresh(self):
        class FakeStore:
            def get_daily(self, code: str, start: str, end: str):
                assert code == "600519"
                assert start == "2026-03-18"
                assert end == "2026-03-19"
                return pd.DataFrame(
                    [
                        {"date": "2026-03-18", "close": 100.0},
                        {"date": "2026-03-19", "close": 101.0},
                    ]
                )

        class FakeDataEngine:
            def __init__(self):
                self.store = FakeStore()

            def get_daily_history(self, code: str, start: str, end: str):
                raise AssertionError("timeline loader should not trigger network refresh when local store already has data")

        with patch(
            "engine.data.get_data_engine",
            return_value=FakeDataEngine(),
        ):
            history = run(
                self.svc._load_price_history(
                    ["600519"],
                    date.fromisoformat("2026-03-18"),
                    date.fromisoformat("2026-03-19"),
                )
            )

        assert history["600519"]["2026-03-18"] == 100.0
        assert history["600519"]["2026-03-19"] == 101.0

    def test_backtest_history_rows_prefers_local_store_without_network_refresh(self):
        from engine.agent.backtest import AgentBacktestEngine

        class FakeStore:
            def get_daily(self, code: str, start: str, end: str):
                assert code == "600519"
                assert start == "2026-03-18"
                assert end == "2026-03-19"
                return pd.DataFrame(
                    [
                        {"date": "2026-03-18", "open": 99.0, "close": 100.0},
                        {"date": "2026-03-19", "open": 100.0, "close": 101.0},
                    ]
                )

        class FakeDataEngine:
            def __init__(self):
                self.store = FakeStore()

            def get_daily_history(self, code: str, start: str, end: str):
                raise AssertionError("backtest history lookup should not trigger network refresh when local store already has data")

        engine = AgentBacktestEngine(db=self.db, service=self.svc)

        with patch(
            "engine.agent.backtest.get_data_engine",
            return_value=FakeDataEngine(),
        ):
            rows = run(
                engine._get_history_rows(
                    "600519",
                    date.fromisoformat("2026-03-18"),
                    date.fromisoformat("2026-03-19"),
                )
            )

        assert rows == [
            {"date": "2026-03-18", "open": 99.0, "close": 100.0},
            {"date": "2026-03-19", "open": 100.0, "close": 101.0},
        ]
