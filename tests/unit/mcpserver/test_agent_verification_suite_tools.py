"""Agent demo verification suite MCP wrapper tests."""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def _import_backend_module(module_name: str):
    for name in list(sys.modules):
        if name == "mcpserver" or name.startswith("mcpserver."):
            sys.modules.pop(name, None)
    return importlib.import_module(module_name)


import pytest


@pytest.mark.asyncio
async def test_run_demo_agent_verification_suite_returns_pass_json(monkeypatch):
    suite = _import_backend_module("mcpserver.agent_verification_suite")

    class FakeHarness:
        async def verify_demo_cycle(self, scenario_id: str, timeout_seconds: int = 30):
            assert scenario_id == "demo-evolution"
            assert timeout_seconds == 30
            return {
                "verification_status": "pass",
                "portfolio_id": "demo-evolution",
                "run_id": "verify-1",
                "failed_stage": None,
                "evolution_diff": {
                    "review_records_delta": 1,
                    "daily_reviews_delta": 1,
                    "weekly_reflections_delta": 1,
                    "weekly_summaries_delta": 1,
                    "memories_added": 1,
                    "memories_updated": 0,
                    "memories_retired": 0,
                },
                "review_result": {
                    "review_type": "weekly",
                    "summary_id": "summary-1",
                    "reflection_id": "reflection-1",
                },
                "seed_summary": {
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "week_start": "2042-01-05",
                    "as_of_date": "2042-01-10",
                },
            }

    class FakeEngine:
        async def run_backtest(self, **kwargs):
            assert kwargs["portfolio_id"] == "demo-evolution"
            assert kwargs["start_date"] == "2042-01-05"
            assert kwargs["end_date"] == "2042-01-10"
            assert kwargs["execution_price_mode"] == "next_open"
            return {"id": "bt-1", "status": "completed"}

        async def get_run_summary(self, run_id: str):
            assert run_id == "bt-1"
            return {
                "run_id": "bt-1",
                "status": "completed",
                "trade_count": 2,
                "review_count": 3,
                "memory_added": 1,
                "memory_updated": 0,
                "memory_retired": 0,
            }

    monkeypatch.setattr(suite, "_get_harness", lambda: FakeHarness())
    monkeypatch.setattr(suite, "_get_engine", lambda: FakeEngine())

    text = await suite.run_demo_agent_verification_suite()
    data = json.loads(text)

    assert data["mode"] == "default"
    assert data["overall_status"] == "pass"
    assert data["scenario_id"] == "demo-evolution"
    assert data["portfolio_id"] == "demo-evolution"
    assert data["demo_verification"]["run_id"] == "verify-1"
    assert data["backtest"]["summary"]["run_id"] == "bt-1"
    assert data["evidence"]["verification_run_id"] == "verify-1"
    assert data["evidence"]["backtest_run_id"] == "bt-1"


@pytest.mark.asyncio
async def test_run_demo_agent_verification_suite_warns_on_weak_backtest_signals(monkeypatch):
    suite = _import_backend_module("mcpserver.agent_verification_suite")

    class FakeHarness:
        async def verify_demo_cycle(self, scenario_id: str, timeout_seconds: int = 30):
            return {
                "verification_status": "pass",
                "portfolio_id": "demo-evolution",
                "run_id": "verify-1",
                "failed_stage": None,
                "evolution_diff": {
                    "review_records_delta": 1,
                    "daily_reviews_delta": 1,
                    "weekly_reflections_delta": 1,
                    "weekly_summaries_delta": 1,
                    "memories_added": 1,
                    "memories_updated": 0,
                    "memories_retired": 0,
                },
                "review_result": {},
                "seed_summary": {
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "week_start": "2042-01-05",
                    "as_of_date": "2042-01-10",
                },
            }

    class FakeEngine:
        async def run_backtest(self, **kwargs):
            return {"id": "bt-1", "status": "completed"}

        async def get_run_summary(self, run_id: str):
            return {
                "run_id": "bt-1",
                "status": "completed",
                "trade_count": 0,
                "review_count": 0,
                "memory_added": 0,
                "memory_updated": 0,
                "memory_retired": 0,
            }

    monkeypatch.setattr(suite, "_get_harness", lambda: FakeHarness())
    monkeypatch.setattr(suite, "_get_engine", lambda: FakeEngine())

    text = await suite.run_demo_agent_verification_suite()
    data = json.loads(text)

    assert data["overall_status"] == "warn"
    assert any("trade_count=0" in item for item in data["next_actions"])
    assert any("review_count=0" in item for item in data["next_actions"])


@pytest.mark.asyncio
async def test_run_demo_agent_verification_suite_smoke_mode_uses_smoke_defaults(monkeypatch):
    suite = _import_backend_module("mcpserver.agent_verification_suite")

    class FakeHarness:
        async def verify_demo_cycle(self, scenario_id: str, timeout_seconds: int = 30):
            return {
                "verification_status": "pass",
                "portfolio_id": "demo-evolution",
                "run_id": "verify-1",
                "failed_stage": None,
                "evolution_diff": {
                    "review_records_delta": 1,
                    "daily_reviews_delta": 1,
                    "weekly_reflections_delta": 1,
                    "weekly_summaries_delta": 1,
                    "memories_added": 1,
                    "memories_updated": 0,
                    "memories_retired": 0,
                },
                "review_result": {},
                "seed_summary": {
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "week_start": "2042-01-05",
                    "as_of_date": "2042-01-10",
                },
            }

    class FakeEngine:
        async def run_backtest(self, **kwargs):
            assert kwargs["start_date"] == "2026-03-18"
            assert kwargs["end_date"] == "2026-03-20"
            return {"id": "bt-1", "status": "completed"}

        async def get_run_summary(self, run_id: str):
            return {
                "run_id": "bt-1",
                "status": "completed",
                "trade_count": 1,
                "review_count": 2,
                "memory_added": 1,
                "memory_updated": 0,
                "memory_retired": 0,
            }

    monkeypatch.setattr(suite, "_get_harness", lambda: FakeHarness())
    monkeypatch.setattr(suite, "_get_engine", lambda: FakeEngine())

    text = await suite.run_demo_agent_verification_suite(smoke_mode=True)
    data = json.loads(text)

    assert data["mode"] == "smoke"
    assert data["backtest"]["start_date"] == "2026-03-18"
    assert data["backtest"]["end_date"] == "2026-03-20"


@pytest.mark.asyncio
async def test_run_demo_agent_verification_suite_fails_and_skips_backtest_when_demo_fails(monkeypatch):
    suite = _import_backend_module("mcpserver.agent_verification_suite")

    class FakeHarness:
        async def verify_demo_cycle(self, scenario_id: str, timeout_seconds: int = 30):
            return {
                "verification_status": "fail",
                "portfolio_id": "demo-evolution",
                "run_id": "verify-1",
                "failed_stage": "brain_execute",
                "evolution_diff": {},
                "review_result": {},
                "seed_summary": {
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "week_start": "2042-01-05",
                    "as_of_date": "2042-01-10",
                },
            }

    class FakeEngine:
        async def run_backtest(self, **kwargs):
            raise AssertionError("backtest should be skipped when demo verification fails")

    monkeypatch.setattr(suite, "_get_harness", lambda: FakeHarness())
    monkeypatch.setattr(suite, "_get_engine", lambda: FakeEngine())

    text = await suite.run_demo_agent_verification_suite()
    data = json.loads(text)

    assert data["overall_status"] == "fail"
    assert data["backtest"]["status"] == "skipped"
    assert data["evidence"]["verification_run_id"] == "verify-1"


@pytest.mark.asyncio
async def test_run_demo_agent_verification_suite_preserves_verification_evidence_when_backtest_fails(monkeypatch):
    suite = _import_backend_module("mcpserver.agent_verification_suite")

    class FakeHarness:
        async def verify_demo_cycle(self, scenario_id: str, timeout_seconds: int = 30):
            return {
                "verification_status": "pass",
                "portfolio_id": "demo-evolution",
                "run_id": "verify-1",
                "failed_stage": None,
                "evolution_diff": {
                    "review_records_delta": 1,
                    "daily_reviews_delta": 1,
                    "weekly_reflections_delta": 1,
                    "weekly_summaries_delta": 1,
                    "memories_added": 1,
                    "memories_updated": 0,
                    "memories_retired": 0,
                },
                "review_result": {},
                "seed_summary": {
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "week_start": "2042-01-05",
                    "as_of_date": "2042-01-10",
                },
            }

    class FakeEngine:
        async def run_backtest(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(suite, "_get_harness", lambda: FakeHarness())
    monkeypatch.setattr(suite, "_get_engine", lambda: FakeEngine())

    text = await suite.run_demo_agent_verification_suite()
    data = json.loads(text)

    assert data["overall_status"] == "fail"
    assert data["evidence"]["verification_run_id"] == "verify-1"
    assert data["backtest"]["status"] == "fail"
    assert "boom" in data["backtest"]["error"]
