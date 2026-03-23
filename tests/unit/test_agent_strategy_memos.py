import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_service(tmp_dir: str):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()

    from engine.agent.service import AgentService
    from engine.agent.validator import TradeValidator

    service = AgentService(db=db, validator=TradeValidator())
    return db, service


def _create_test_app(tmp_dir: str):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()

    from engine.agent.routes import create_agent_router

    app = FastAPI()
    app.include_router(create_agent_router(), prefix="/api/v1/agent")
    return app, db


class TestStrategyMemoModels:
    def test_strategy_memo_input_accepts_full_plan_snapshot(self):
        from engine.agent.models import StrategyMemoInput

        memo = StrategyMemoInput(
            portfolio_id="live",
            source_agent="expert",
            source_session_id="session-1",
            source_message_id="message-1",
            strategy_key="buy|600519|mid_term|1",
            stock_code="600519",
            stock_name="贵州茅台",
            plan_snapshot={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "direction": "buy",
                "entry_price": 1500.0,
                "take_profit": 1650.0,
                "stop_loss": 1420.0,
                "reasoning": "估值回归后继续修复",
            },
            note="观察后再决定",
            status="saved",
        )

        assert memo.plan_snapshot["direction"] == "buy"
        assert memo.status == "saved"

    def test_strategy_memo_status_only_allows_expected_values(self):
        from engine.agent.models import StrategyMemoInput, StrategyMemoUpdate

        with pytest.raises(ValidationError):
            StrategyMemoInput(
                portfolio_id="live",
                strategy_key="buy|600519|mid_term|1",
                stock_code="600519",
                plan_snapshot={"stock_code": "600519"},
                status="accepted",
            )

        updated = StrategyMemoUpdate(status="archived")
        assert updated.status == "archived"

        with pytest.raises(ValidationError):
            StrategyMemoUpdate(status="done")


class TestStrategyMemoDBConstraints:
    def test_strategy_memo_table_rejects_invalid_status(self, tmp_path):
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB

            AgentDB._instance = None
            db = AgentDB.init_instance()

        with pytest.raises(Exception):
            run(
                db.execute_write(
                    """
                    INSERT INTO agent.strategy_memos (
                        id, portfolio_id, strategy_key, stock_code, plan_snapshot, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        "memo-invalid-status",
                        "live",
                        "buy|600519|mid_term|1",
                        "600519",
                        '{"stock_code":"600519","direction":"buy"}',
                        "accepted",
                    ],
                )
            )

        rows = run(
            db.execute_read(
                "SELECT id FROM agent.strategy_memos WHERE id = ?",
                ["memo-invalid-status"],
            )
        )
        assert rows == []
        db.close()


class TestStrategyMemoService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def _payload(self, **overrides):
        payload = {
            "portfolio_id": "live",
            "source_agent": "expert",
            "source_session_id": "session-1",
            "source_message_id": "message-1",
            "strategy_key": "buy|600519|mid_term|1",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "plan_snapshot": {
                "stock_code": "600519",
                "direction": "buy",
                "entry_price": 1500.0,
                "take_profit": 1650.0,
                "stop_loss": 1420.0,
            },
            "note": "memo",
            "status": "saved",
        }
        payload.update(overrides)
        return payload

    def test_create_strategy_memo(self):
        created = run(self.svc.create_strategy_memo(self._payload()))
        assert created["portfolio_id"] == "live"
        assert created["strategy_key"] == "buy|600519|mid_term|1"
        assert created["plan_snapshot"]["stock_code"] == "600519"

    def test_create_strategy_memo_is_idempotent_for_same_message_and_strategy(self):
        first = run(self.svc.create_strategy_memo(self._payload()))
        second = run(self.svc.create_strategy_memo(self._payload()))
        assert second["id"] == first["id"]

    def test_list_strategy_memos_filters_status(self):
        run(self.svc.create_strategy_memo(self._payload(strategy_key="k-1", source_message_id="m-1")))
        run(self.svc.create_strategy_memo(self._payload(strategy_key="k-2", source_message_id="m-2", status="ignored")))
        saved = run(self.svc.list_strategy_memos("live", status="saved"))
        ignored = run(self.svc.list_strategy_memos("live", status="ignored"))
        assert len(saved) == 1
        assert saved[0]["status"] == "saved"
        assert len(ignored) == 1
        assert ignored[0]["status"] == "ignored"

    def test_update_strategy_memo_ignore_and_archive(self):
        memo = run(self.svc.create_strategy_memo(self._payload()))
        ignored = run(self.svc.update_strategy_memo(memo["id"], {"status": "ignored"}))
        archived = run(self.svc.update_strategy_memo(memo["id"], {"status": "archived"}))
        assert ignored["status"] == "ignored"
        assert archived["status"] == "archived"

    def test_delete_strategy_memo(self):
        memo = run(self.svc.create_strategy_memo(self._payload()))
        run(self.svc.delete_strategy_memo(memo["id"]))
        rows = run(self.svc.list_strategy_memos("live"))
        assert rows == []

    def test_strategy_memo_actions_do_not_write_ledger_tables(self):
        memo = run(self.svc.create_strategy_memo(self._payload()))
        run(self.svc.update_strategy_memo(memo["id"], {"status": "ignored"}))
        trades = run(self.db.execute_read("SELECT * FROM agent.trades"))
        plans = run(self.db.execute_read("SELECT * FROM agent.trade_plans"))
        positions = run(self.db.execute_read("SELECT * FROM agent.positions"))
        assert trades == []
        assert plans == []
        assert positions == []

    def test_create_strategy_memo_with_invalid_dict_payload_raises_value_error(self):
        invalid_payload = self._payload()
        invalid_payload.pop("strategy_key")
        with pytest.raises(ValueError):
            run(self.svc.create_strategy_memo(invalid_payload))


class TestStrategyMemoRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "live", "mode": "live", "initial_capital": 1000000.0},
        )

    def teardown_method(self):
        self.db.close()

    def _payload(self, **overrides):
        payload = {
            "portfolio_id": "live",
            "source_agent": "expert",
            "source_session_id": "session-1",
            "source_message_id": "message-1",
            "strategy_key": "buy|600519|mid_term|1",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "plan_snapshot": {
                "stock_code": "600519",
                "direction": "buy",
                "entry_price": 1500.0,
                "take_profit": 1650.0,
                "stop_loss": 1420.0,
            },
            "note": "memo",
            "status": "saved",
        }
        payload.update(overrides)
        return payload

    def test_strategy_memo_routes_crud(self):
        created = self.client.post(
            "/api/v1/agent/strategy-memos",
            json=self._payload(),
        )
        assert created.status_code == 200
        memo_id = created.json()["id"]

        listed = self.client.get("/api/v1/agent/strategy-memos?portfolio_id=live&status=saved")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        ignored = self.client.patch(
            f"/api/v1/agent/strategy-memos/{memo_id}",
            json={"status": "ignored"},
        )
        assert ignored.status_code == 200
        assert ignored.json()["status"] == "ignored"

        archived = self.client.patch(
            f"/api/v1/agent/strategy-memos/{memo_id}",
            json={"status": "archived"},
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"

        deleted = self.client.delete(f"/api/v1/agent/strategy-memos/{memo_id}")
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True

    def test_strategy_memo_route_is_idempotent_and_does_not_create_ledger_rows(self):
        first = self.client.post(
            "/api/v1/agent/strategy-memos",
            json=self._payload(),
        )
        second = self.client.post(
            "/api/v1/agent/strategy-memos",
            json=self._payload(),
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]

        trades = self.client.get("/api/v1/agent/portfolio/live/trades")
        assert trades.status_code == 200
        assert trades.json() == []
        plans = self.client.get("/api/v1/agent/plans")
        assert plans.status_code == 200
        assert plans.json() == []
        positions = self.client.get("/api/v1/agent/portfolio/live/positions")
        assert positions.status_code == 200
        assert positions.json() == []

    def test_strategy_memo_routes_invalid_status_returns_400(self):
        created = self.client.post(
            "/api/v1/agent/strategy-memos",
            json=self._payload(),
        )
        memo_id = created.json()["id"]
        updated = self.client.patch(
            f"/api/v1/agent/strategy-memos/{memo_id}",
            json={"status": "invalid-status"},
        )
        assert updated.status_code == 400

        listed = self.client.get("/api/v1/agent/strategy-memos?portfolio_id=live&status=invalid-status")
        assert listed.status_code == 400

    def test_strategy_memo_routes_missing_resource_returns_404(self):
        missing = self.client.patch(
            "/api/v1/agent/strategy-memos/not-exist",
            json={"status": "ignored"},
        )
        assert missing.status_code == 404
