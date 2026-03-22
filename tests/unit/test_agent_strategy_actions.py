"""Agent strategy action contract and idempotency tests."""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


LEGACY_STRATEGY_ACTIONS_SQL = """
CREATE TABLE IF NOT EXISTS agent.strategy_actions (
    id VARCHAR PRIMARY KEY,
    portfolio_id VARCHAR NOT NULL,
    session_id VARCHAR NOT NULL,
    message_id VARCHAR NOT NULL,
    stock_code VARCHAR NOT NULL,
    stock_name VARCHAR,
    decision VARCHAR NOT NULL,
    trade_action VARCHAR,
    reason TEXT,
    source_run_id VARCHAR,
    plan_id VARCHAR,
    trade_id VARCHAR,
    position_id VARCHAR,
    strategy_id VARCHAR,
    strategy_version INTEGER,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE (session_id, message_id, stock_code)
)
"""


def build_strategy_key(plan: dict) -> str:
    def numeric_part(value):
        if value is None:
            return ""
        return f"{float(value):.4f}"

    return "|".join(
        [
            str(plan["stock_code"]).strip().upper(),
            str(plan["direction"]),
            numeric_part(plan.get("entry_price")),
            numeric_part(plan.get("take_profit")),
            numeric_part(plan.get("stop_loss")),
            str(plan.get("valid_until") or "").strip(),
        ]
    )


def _plan_payload(**overrides):
    payload = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "direction": "buy",
        "current_price": 100.0,
        "entry_price": 100.0,
        "entry_method": "分批",
        "position_pct": 0.1,
        "take_profit": 120.0,
        "take_profit_method": "120 附近分批止盈",
        "stop_loss": 90.0,
        "stop_loss_method": "90 附近止损",
        "reasoning": "龙头企稳，准备执行",
        "risk_note": "消费恢复不及预期",
        "invalidation": "跌破 90",
        "valid_until": "2026-04-01",
    }
    payload.update(overrides)
    return payload


def _adopt_request(**overrides):
    plan = overrides.pop("plan", _plan_payload())
    payload = {
        "portfolio_id": "live",
        "session_id": "session-1",
        "message_id": "message-1",
        "strategy_key": build_strategy_key(plan),
        "plan": plan,
        "source_run_id": "run-1",
    }
    payload.update(overrides)
    return payload


def _reject_request(**overrides):
    plan = overrides.pop("plan", _plan_payload())
    payload = {
        "portfolio_id": "live",
        "session_id": "session-1",
        "message_id": "message-1",
        "strategy_key": build_strategy_key(plan),
        "plan": plan,
        "reason": "位置太高，先等回调",
        "source_run_id": "run-1",
    }
    payload.update(overrides)
    return payload


def _make_db(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()

    run(db.execute_write(LEGACY_STRATEGY_ACTIONS_SQL))
    return db


def _make_service(tmp_dir):
    db = _make_db(tmp_dir)

    from engine.agent.memory import MemoryManager
    from engine.agent.service import AgentService
    from engine.agent.strategy_actions import StrategyActionService
    from engine.agent.validator import TradeValidator

    service = StrategyActionService(
        db=db,
        agent_service=AgentService(db=db, validator=TradeValidator()),
        memory_mgr=MemoryManager(db),
    )
    return db, service


def _make_test_app(tmp_dir):
    db = _make_db(tmp_dir)
    from engine.agent.strategy_action_routes import create_strategy_action_router

    app = FastAPI()
    app.include_router(create_strategy_action_router(), prefix="/api/v1/agent")
    return app, db


class TestStrategyActionService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.service = _make_service(self._tmp)
        run(self.service.agent_service.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_adopt_uses_canonical_plan_payload_and_returns_rehydration_fields(self):
        result = run(self.service.adopt_strategy(_adopt_request()))

        assert result["session_id"] == "session-1"
        assert result["message_id"] == "message-1"
        assert result["strategy_key"] == build_strategy_key(_plan_payload())
        assert result["decision"] == "adopted"
        assert result["status"] == "adopted"
        assert result["plan_id"] is not None
        assert result["trade_id"] is not None
        assert result["position_id"] is not None
        assert result["strategy_id"] is not None

    def test_reject_uses_same_contract_and_writes_memory_feedback(self):
        result = run(self.service.reject_strategy(_reject_request()))
        memories = run(self.service.memory_mgr.list_rules())

        assert result["strategy_key"] == build_strategy_key(_plan_payload())
        assert result["decision"] == "rejected"
        assert result["status"] == "rejected"
        assert result["reason"] == "位置太高，先等回调"
        assert len(memories) == 1
        assert memories[0]["category"] == "strategy_feedback"

    def test_list_actions_rehydrates_strategy_key_when_stored_value_missing(self):
        action = run(self.service.adopt_strategy(_adopt_request()))

        run(
            self.db.execute_write(
                """
                UPDATE agent.strategy_actions
                SET strategy_key = NULL
                WHERE id = ?
                """,
                [action["id"]],
            )
        )

        actions = run(self.service.list_actions("session-1"))

        assert actions[0]["strategy_key"] == build_strategy_key(_plan_payload())
        assert actions[0]["status"] == "adopted"

    def test_adopt_is_idempotent_for_same_message_and_strategy_key(self):
        first = run(self.service.adopt_strategy(_adopt_request()))
        second = run(self.service.adopt_strategy(_adopt_request()))

        actions = run(self.service.list_actions("session-1"))
        trades = run(self.db.execute_read("SELECT * FROM agent.trades"))

        assert second["id"] == first["id"]
        assert len(actions) == 1
        assert len(trades) == 1

    def test_same_session_message_and_stock_but_different_strategy_key_creates_two_actions(self):
        first_plan = _plan_payload(entry_price=100.0, take_profit=120.0, stop_loss=90.0)
        second_plan = _plan_payload(entry_price=101.0, take_profit=125.0, stop_loss=92.0)

        first = run(self.service.adopt_strategy(_adopt_request(plan=first_plan)))
        second = run(self.service.adopt_strategy(_adopt_request(plan=second_plan)))

        actions = run(self.service.list_actions("session-1"))

        assert second["id"] != first["id"]
        assert len(actions) == 2
        assert {item["strategy_key"] for item in actions} == {
            build_strategy_key(first_plan),
            build_strategy_key(second_plan),
        }


class TestStrategyActionRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _make_test_app(self._tmp)
        self.client = TestClient(self.app)

        from engine.agent.service import AgentService
        from engine.agent.validator import TradeValidator

        self.agent_service = AgentService(db=self.db, validator=TradeValidator())
        run(self.agent_service.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_strategy_action_routes_support_canonical_payloads(self):
        adopt_response = self.client.post("/api/v1/agent/adopt-strategy", json=_adopt_request())
        reject_response = self.client.post(
            "/api/v1/agent/reject-strategy",
            json=_reject_request(
                message_id="message-2",
                plan=_plan_payload(stock_code="000001", stock_name="平安银行"),
            ),
        )
        list_response = self.client.get(
            "/api/v1/agent/strategy-actions",
            params={"session_id": "session-1"},
        )

        assert adopt_response.status_code == 200
        assert adopt_response.json()["status"] == "adopted"
        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"
        assert list_response.status_code == 200
        assert {item["strategy_key"] for item in list_response.json()} == {
            build_strategy_key(_plan_payload()),
            build_strategy_key(_plan_payload(stock_code="000001", stock_name="平安银行")),
        }

    def test_strategy_actions_route_returns_stable_rehydration_shape(self):
        self.client.post("/api/v1/agent/adopt-strategy", json=_adopt_request())

        response = self.client.get(
            "/api/v1/agent/strategy-actions",
            params={"session_id": "session-1"},
        )

        body = response.json()[0]

        assert response.status_code == 200
        assert set(body) >= {
            "id",
            "session_id",
            "message_id",
            "strategy_key",
            "decision",
            "status",
            "plan_id",
            "trade_id",
            "position_id",
            "strategy_id",
            "strategy_version",
        }

    def test_reject_route_accepts_null_reason_without_memory_crash(self):
        response = self.client.post(
            "/api/v1/agent/reject-strategy",
            json=_reject_request(reason=None),
        )
        memories = run(self.db.execute_read("SELECT * FROM agent.agent_memories"))

        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        assert memories == []

    def test_adopt_sell_without_position_returns_400(self):
        sell_plan = _plan_payload(direction="sell", position_pct=1.0)
        response = self.client.post(
            "/api/v1/agent/adopt-strategy",
            json=_adopt_request(
                plan=sell_plan,
                strategy_key=build_strategy_key(sell_plan),
            ),
        )

        assert response.status_code == 400
        assert "持仓" in response.json()["detail"]


class TestStrategyActionSchemaUpgrade:
    def test_service_backfills_missing_columns_on_legacy_table(self):
        tmp_dir = tempfile.mkdtemp()
        db, service = _make_service(tmp_dir)
        run(service.agent_service.create_portfolio("live", "live", 1000000.0))

        action = run(service.adopt_strategy(_adopt_request()))
        columns = {
            row["column_name"]
            for row in run(
                db.execute_read(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'agent' AND table_name = 'strategy_actions'
                    """
                )
            )
        }

        assert action["strategy_key"] == build_strategy_key(_plan_payload())
        assert {"strategy_key", "status", "plan_snapshot"} <= columns

        db.close()
