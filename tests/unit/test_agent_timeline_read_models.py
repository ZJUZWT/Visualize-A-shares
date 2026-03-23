"""Agent equity timeline / replay read model tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest
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
    svc.validator.SLIPPAGE_BUY = 0.0
    svc.validator.SLIPPAGE_SELL = 0.0
    svc.validator.COMMISSION_RATE = 0.0
    svc.validator.MIN_COMMISSION = 0.0
    svc.validator.STAMP_TAX_RATE = 0.0
    svc.validator.TRANSFER_FEE_RATE = 0.0
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


def _make_trade_input(**overrides):
    from engine.agent.models import TradeInput

    payload = {
        "action": "buy",
        "stock_code": "600519",
        "price": 100.0,
        "quantity": 200,
        "holding_type": "mid_term",
        "reason": "初始建仓",
        "thesis": "趋势改善，先建底仓",
        "data_basis": ["量价共振"],
        "risk_note": "若跌破平台则离场",
        "invalidation": "趋势转弱",
        "triggered_by": "agent",
    }
    payload.update(overrides)
    return TradeInput(**payload)


def _make_plan_input(**overrides):
    from engine.agent.models import TradePlanInput

    payload = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "current_price": 112.0,
        "direction": "sell",
        "entry_price": 110.0,
        "entry_method": "分批兑现",
        "position_pct": 0.1,
        "take_profit": 115.0,
        "take_profit_method": "接近阻力减仓",
        "stop_loss": 105.0,
        "stop_loss_method": "跌破均线撤退",
        "reasoning": "短期涨幅已兑现一部分，计划先减仓",
        "risk_note": "若继续放量上攻可能卖飞",
        "invalidation": "量价继续强化",
        "valid_until": "2026-03-21",
        "source_type": "agent",
        "source_conversation_id": None,
    }
    payload.update(overrides)
    return TradePlanInput(**payload)


def _make_zero_fee_validator():
    from engine.agent.validator import TradeValidator

    validator = TradeValidator()
    validator.SLIPPAGE_BUY = 0.0
    validator.SLIPPAGE_SELL = 0.0
    validator.COMMISSION_RATE = 0.0
    validator.MIN_COMMISSION = 0.0
    validator.STAMP_TAX_RATE = 0.0
    validator.TRANSFER_FEE_RATE = 0.0
    return validator


class FakeDataEngine:
    def __init__(self, history_by_code):
        self.history_by_code = history_by_code

    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        rows = []
        for row in self.history_by_code.get(code, []):
            if start <= row["date"] <= end:
                rows.append(row)
        return pd.DataFrame(rows)


def _update_timestamp(db, table: str, row_id: str, value: str):
    run(db.execute_write(f"UPDATE agent.{table} SET created_at = ? WHERE id = ?", [value, row_id]))


def _seed_replay_fixture(svc, db):
    run(svc.create_portfolio("live", "live", 1000000.0, "2026-03-18"))

    buy = run(svc.execute_trade("live", _make_trade_input(), "2026-03-18"))
    position_id = buy["position"]["id"]
    buy_trade_id = buy["trade"]["id"]
    _update_timestamp(db, "trades", buy_trade_id, "2026-03-18T10:00:00")

    reduce = run(
        svc.execute_trade(
            "live",
            _make_trade_input(
                action="reduce",
                price=110.0,
                quantity=100,
                holding_type=None,
                reason="兑现一半收益",
                thesis="减仓锁定阶段收益",
                data_basis=["接近短期目标位", "量能未继续放大"],
            ),
            "2026-03-20",
            position_id=position_id,
        )
    )
    reduce_trade_id = reduce["trade"]["id"]
    _update_timestamp(db, "trades", reduce_trade_id, "2026-03-20T14:30:00")

    run_record = run(svc.create_brain_run("live", "manual"))
    run(
        svc.update_brain_run(
            run_record["id"],
            {
                "status": "completed",
                "thinking_process": [
                    {"step": "scan", "summary": "短期冲高接近目标位"},
                    {"step": "decision", "summary": "先减仓一半"},
                ],
                "state_before": {"market_view": "bullish", "position_level": "medium"},
                "state_after": {"market_view": "bullish", "position_level": "light"},
                "execution_summary": {
                    "candidate_count": 3,
                    "analysis_count": 2,
                    "decision_count": 1,
                    "plan_count": 1,
                    "trade_count": 1,
                },
            },
        )
    )
    run(
        db.execute_write(
            "UPDATE agent.brain_runs SET started_at = ?, completed_at = ? WHERE id = ?",
            ["2026-03-20T13:55:00", "2026-03-20T14:05:00", run_record["id"]],
        )
    )

    plan = run(svc.create_plan(_make_plan_input(), source_run_id=run_record["id"]))
    run(
        db.execute_write(
            "UPDATE agent.trade_plans SET created_at = ?, updated_at = ? WHERE id = ?",
            ["2026-03-20T13:45:00", "2026-03-20T14:00:00", plan["id"]],
        )
    )

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
                "review-1",
                run_record["id"],
                reduce_trade_id,
                "600519",
                "贵州茅台",
                "reduce",
                110.0,
                115.0,
                0.0455,
                1,
                "win",
                "2026-03-20",
                "daily",
                "2026-03-20T16:00:00",
            ],
        )
    )

    run(
        db.execute_write(
            """
            INSERT INTO agent.daily_reviews (
                id, review_date, total_reviews, win_count, loss_count,
                holding_count, total_pnl_pct, summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "daily-1",
                "2026-03-20",
                1,
                1,
                0,
                0,
                0.0455,
                "日复盘：减仓节奏合理",
                "2026-03-20T16:10:00",
            ],
        )
    )

    return {
        "position_id": position_id,
        "buy_trade_id": buy_trade_id,
        "reduce_trade_id": reduce_trade_id,
        "run_id": run_record["id"],
        "plan_id": plan["id"],
    }


PRICE_HISTORY = {
    "600519": [
        {"date": "2026-03-18", "close": 100.0},
        {"date": "2026-03-20", "close": 112.0},
        {"date": "2026-03-21", "close": 115.0},
    ]
}


class TestAgentTimelineService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        self.fixture = _seed_replay_fixture(self.svc, self.db)

    def teardown_method(self):
        self.db.close()

    def test_get_equity_timeline_returns_mark_to_market_and_realized_only(self):
        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine(PRICE_HISTORY)):
            timeline = run(self.svc.get_equity_timeline("live"))

        assert set(timeline.keys()) == {
            "portfolio_id",
            "start_date",
            "end_date",
            "mark_to_market",
            "realized_only",
        }
        assert timeline["portfolio_id"] == "live"
        assert timeline["start_date"] == "2026-03-18"
        assert timeline["end_date"] == "2026-03-20"

        mtm_by_date = {item["date"]: item for item in timeline["mark_to_market"]}
        realized_by_date = {item["date"]: item for item in timeline["realized_only"]}
        assert mtm_by_date["2026-03-18"]["equity"] == 1000000.0
        assert mtm_by_date["2026-03-20"]["equity"] == 1002200.0
        assert mtm_by_date["2026-03-20"]["unrealized_pnl"] == 1200.0
        assert realized_by_date["2026-03-20"]["equity"] == 1001000.0
        assert mtm_by_date["2026-03-20"]["equity"] > realized_by_date["2026-03-20"]["equity"]

    def test_get_equity_timeline_falls_back_to_previous_close_when_day_missing(self):
        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine(PRICE_HISTORY)):
            timeline = run(self.svc.get_equity_timeline("live"))

        mtm_by_date = {item["date"]: item for item in timeline["mark_to_market"]}
        assert mtm_by_date["2026-03-19"]["position_value"] == 20000.0
        assert mtm_by_date["2026-03-19"]["equity"] == 1000000.0

    def test_get_equity_timeline_returns_flat_curve_for_portfolio_without_trades(self):
        run(self.svc.create_portfolio("training", "training", 500000.0, "2026-03-18"))

        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine({})):
            timeline = run(self.svc.get_equity_timeline("training"))

        assert timeline["mark_to_market"] == [
            {
                "date": "2026-03-18",
                "equity": 500000.0,
                "cash_balance": 500000.0,
                "position_value": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
            }
        ]
        assert timeline["realized_only"] == [
            {
                "date": "2026-03-18",
                "equity": 500000.0,
                "cash_balance": 500000.0,
                "position_cost_basis_open": 0.0,
                "realized_pnl": 0.0,
            }
        ]

    def test_get_replay_snapshot_aggregates_account_positions_and_ai_context(self):
        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine(PRICE_HISTORY)):
            replay = run(self.svc.get_replay_snapshot("live", "2026-03-20"))

        assert replay["portfolio_id"] == "live"
        assert replay["date"] == "2026-03-20"
        assert replay["account"]["cash_balance"] == 991000.0
        assert replay["account"]["total_asset_mark_to_market"] == 1002200.0
        assert replay["account"]["total_asset_realized_only"] == 1001000.0
        assert replay["account"]["realized_pnl"] == 1000.0
        assert replay["account"]["unrealized_pnl"] == 1200.0
        assert replay["positions"][0]["stock_code"] == "600519"
        assert replay["positions"][0]["current_qty"] == 100
        assert replay["brain_runs"][0]["id"] == self.fixture["run_id"]
        assert replay["plans"][0]["id"] == self.fixture["plan_id"]
        assert replay["trades"][0]["id"] == self.fixture["reduce_trade_id"]
        assert replay["reviews"][0]["id"] == "review-1"
        assert replay["reflections"][0]["id"] == "daily-1"
        assert replay["what_ai_knew"]["trade_theses"] == ["减仓锁定阶段收益"]
        assert replay["what_happened"]["next_day_move_pct"] == pytest.approx(2.68)

    def test_get_replay_snapshot_rejects_date_before_portfolio_start(self):
        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine(PRICE_HISTORY)):
            with pytest.raises(ValueError, match="早于组合起始"):
                run(self.svc.get_replay_snapshot("live", "2026-03-01"))


class TestAgentTimelineRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _make_app(self._tmp)
        self.client = TestClient(self.app)

        from engine.agent.service import AgentService
        from engine.agent.validator import TradeValidator

        self.svc = AgentService(db=self.db, validator=TradeValidator())
        self.svc.validator.SLIPPAGE_BUY = 0.0
        self.svc.validator.SLIPPAGE_SELL = 0.0
        self.svc.validator.COMMISSION_RATE = 0.0
        self.svc.validator.MIN_COMMISSION = 0.0
        self.svc.validator.STAMP_TAX_RATE = 0.0
        self.svc.validator.TRANSFER_FEE_RATE = 0.0
        _seed_replay_fixture(self.svc, self.db)

    def teardown_method(self):
        self.db.close()

    def test_get_equity_timeline_route(self):
        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine(PRICE_HISTORY)), patch(
            "engine.agent.routes.TradeValidator",
            return_value=_make_zero_fee_validator(),
        ):
            resp = self.client.get("/api/v1/agent/timeline/equity?portfolio_id=live")

        assert resp.status_code == 200
        body = resp.json()
        assert body["portfolio_id"] == "live"
        assert body["mark_to_market"][-1]["equity"] == 1002200.0
        assert body["realized_only"][-1]["equity"] == 1001000.0

    def test_get_replay_snapshot_route_404_for_missing_portfolio(self):
        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine(PRICE_HISTORY)), patch(
            "engine.agent.routes.TradeValidator",
            return_value=_make_zero_fee_validator(),
        ):
            resp = self.client.get("/api/v1/agent/timeline/replay?portfolio_id=missing&date=2026-03-20")

        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    def test_get_replay_snapshot_route_400_for_invalid_date(self):
        with patch("engine.agent.service.get_data_engine", return_value=FakeDataEngine(PRICE_HISTORY)), patch(
            "engine.agent.routes.TradeValidator",
            return_value=_make_zero_fee_validator(),
        ):
            resp = self.client.get("/api/v1/agent/timeline/replay?portfolio_id=live&date=2026-03-99")

        assert resp.status_code == 400
