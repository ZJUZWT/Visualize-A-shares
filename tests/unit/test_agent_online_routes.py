"""Agent online verification route tests."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


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


class TestAgentOnlineRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def test_snapshot_route_returns_structured_json(self):
        async def fake_inspect_snapshot(portfolio_id: str, run_id: str | None = None):
            assert portfolio_id == "live"
            assert run_id is None
            return {
                "portfolio_id": "live",
                "state": {"market_view": {"stance": "neutral"}},
                "latest_run": {"id": "run-1"},
                "ledger": {"asset_summary": {"total_asset": 1000000}},
                "review_stats": {"total_reviews": 2},
                "memories": [],
            }

        with patch(
            "engine.agent.routes._get_verification_harness",
            return_value=SimpleNamespace(inspect_snapshot=fake_inspect_snapshot),
        ):
            response = self.client.get(
                "/api/v1/agent/verification/snapshot",
                params={"portfolio_id": "live"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["portfolio_id"] == "live"
        assert body["latest_run"]["id"] == "run-1"

    def test_prepare_demo_route_returns_seed_summary(self):
        async def fake_prepare_demo_portfolio(scenario_id: str = "demo-evolution"):
            assert scenario_id == "demo-evolution"
            return {
                "scenario_id": "demo-evolution",
                "portfolio_id": "demo-evolution",
                "as_of_date": "2042-01-10",
            }

        with patch(
            "engine.agent.routes._get_verification_harness",
            return_value=SimpleNamespace(prepare_demo_portfolio=fake_prepare_demo_portfolio),
        ):
            response = self.client.post(
                "/api/v1/agent/demo/prepare",
                json={"scenario_id": "demo-evolution"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["portfolio_id"] == "demo-evolution"

    def test_verify_demo_route_returns_structured_json(self):
        async def fake_verify_demo_cycle(scenario_id: str = "demo-evolution", timeout_seconds: int = 30):
            assert scenario_id == "demo-evolution"
            assert timeout_seconds == 15
            return {
                "verification_status": "pass",
                "portfolio_id": "demo-evolution",
                "run_id": "run-demo",
                "seed_summary": {"scenario_id": "demo-evolution"},
            }

        with patch(
            "engine.agent.routes._get_verification_harness",
            return_value=SimpleNamespace(verify_demo_cycle=fake_verify_demo_cycle),
        ):
            response = self.client.post(
                "/api/v1/agent/demo/verify",
                json={"scenario_id": "demo-evolution", "timeout_seconds": 15},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["verification_status"] == "pass"
        assert body["run_id"] == "run-demo"

    def test_verify_cycle_route_maps_value_error_to_http_400(self):
        async def fake_verify_cycle(**kwargs):
            raise ValueError("bad verification request")

        with patch(
            "engine.agent.routes._get_verification_harness",
            return_value=SimpleNamespace(verify_cycle=fake_verify_cycle),
        ):
            response = self.client.post(
                "/api/v1/agent/verification/run",
                json={"portfolio_id": "live"},
            )

        assert response.status_code == 400
        assert "bad verification request" in response.json()["detail"]

    def test_verification_request_defaults_use_stable_timeout_budget(self):
        from engine.agent.routes import RunAgentVerificationRequest

        assert RunAgentVerificationRequest.model_fields["timeout_seconds"].default == 45
