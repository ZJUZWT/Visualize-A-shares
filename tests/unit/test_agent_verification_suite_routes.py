"""Agent verification suite route tests."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


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


class TestAgentVerificationSuiteRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def test_run_verification_suite_route_returns_structured_json(self):
        async def fake_run_demo_agent_verification_suite(**kwargs):
            assert kwargs["scenario_id"] == "demo-evolution"
            assert kwargs["smoke_mode"] is True
            return json.dumps(
                {
                    "mode": "smoke",
                    "overall_status": "warn",
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "seed_summary": {},
                    "demo_verification": {"verification_status": "pass", "run_id": "verify-1"},
                    "backtest": {"status": "completed", "run_id": "bt-1"},
                    "evidence": {"verification_run_id": "verify-1", "backtest_run_id": "bt-1"},
                    "next_actions": [],
                },
                ensure_ascii=False,
            )

        with patch(
            "engine.agent.routes._get_verification_suite_runner",
            return_value=fake_run_demo_agent_verification_suite,
        ):
            response = self.client.post(
                "/api/v1/agent/verification-suite/run",
                json={
                    "scenario_id": "demo-evolution",
                    "smoke_mode": True,
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "smoke"
        assert body["overall_status"] == "warn"
        assert body["evidence"]["verification_run_id"] == "verify-1"

    def test_run_verification_suite_route_maps_value_error_to_http_400(self):
        async def fake_run_demo_agent_verification_suite(**kwargs):
            raise ValueError("bad verification suite request")

        with patch(
            "engine.agent.routes._get_verification_suite_runner",
            return_value=fake_run_demo_agent_verification_suite,
        ):
            response = self.client.post(
                "/api/v1/agent/verification-suite/run",
                json={"scenario_id": "demo-evolution"},
            )

        assert response.status_code == 400
        assert "bad verification suite request" in response.json()["detail"]
