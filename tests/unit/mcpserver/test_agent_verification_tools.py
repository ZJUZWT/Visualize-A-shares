"""Agent verification MCP wrapper tests."""
import importlib
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
async def test_verify_agent_cycle_tool_formats_result(monkeypatch):
    agent_verification = _import_backend_module("mcpserver.agent_verification")

    async def fake_verify_cycle(**kwargs):
        assert kwargs["portfolio_id"] == "live"
        return {
            "verification_status": "warn",
            "portfolio_id": "live",
            "run_id": "run-1",
            "brain_run_status": "completed",
            "failed_stage": None,
            "stages": [
                {"name": "snapshot_before", "status": "pass"},
                {"name": "brain_execute", "status": "pass"},
                {"name": "evolution_diff", "status": "warn", "detail": {"signals": []}},
            ],
            "checks": [
                {"name": "brain_run_completed", "status": "pass"},
                {"name": "has_candidates", "status": "warn", "detail": 0},
            ],
            "evolution_diff": {
                "brain_runs_delta": 1,
                "review_records_delta": 0,
                "memories_added": 0,
                "memories_updated": 0,
                "memories_retired": 0,
                "reflections_added": 0,
                "weekly_summaries_delta": 0,
                "strategy_history_changed": False,
                "signals": [],
            },
            "evidence": {
                "brain_run": {"execution_summary": {"candidate_count": 0, "trade_count": 0}},
                "review": {"status": "completed", "records_created": 0},
            },
            "next_actions": ["inspect_market_inputs"],
        }

    class FakeHarness:
        async def verify_cycle(self, **kwargs):
            return await fake_verify_cycle(**kwargs)

    monkeypatch.setattr(agent_verification, "_get_harness", lambda: FakeHarness())

    text = await agent_verification.verify_agent_cycle("live")

    assert "warn" in text.lower()
    assert "run-1" in text
    assert "Stages" in text
    assert "Checks" in text
    assert "Evolution Diff" in text
    assert "brain_runs_delta" in text
    assert "Next Actions" in text


@pytest.mark.asyncio
async def test_verify_agent_cycle_recreates_harness_per_call(monkeypatch):
    agent_verification = _import_backend_module("mcpserver.agent_verification")

    class FakeHarness:
        instances = 0

        def __init__(self):
            FakeHarness.instances += 1

        async def verify_cycle(self, **kwargs):
            return {
                "verification_status": "pass",
                "portfolio_id": kwargs["portfolio_id"],
                "run_id": "run-static",
                "brain_run_status": "completed",
                "failed_stage": None,
                "checks": [],
                "evidence": {},
                "next_actions": [],
            }

    monkeypatch.setattr(agent_verification, "AgentVerificationHarness", FakeHarness)

    await agent_verification.verify_agent_cycle("live")
    await agent_verification.verify_agent_cycle("live")

    assert FakeHarness.instances == 2


@pytest.mark.asyncio
async def test_inspect_agent_snapshot_tool_formats_sections(monkeypatch):
    agent_verification = _import_backend_module("mcpserver.agent_verification")

    async def fake_inspect_snapshot(**kwargs):
        assert kwargs["portfolio_id"] == "live"
        return {
            "portfolio_id": "live",
            "state": {"market_view": "neutral", "position_level": 0.3},
            "latest_run": {
                "id": "run-2",
                "status": "completed",
                "execution_summary": {"candidate_count": 2, "trade_count": 1},
            },
            "ledger": {
                "asset_summary": {
                    "open_position_count": 1,
                    "recent_trade_count": 1,
                    "pending_plan_count": 0,
                    "executing_plan_count": 0,
                }
            },
            "review_stats": {"total_reviews": 3, "win_rate": 0.6667},
            "memories": [{"rule_text": "不要追高", "confidence": 0.8}],
        }

    class FakeHarness:
        async def inspect_snapshot(self, **kwargs):
            return await fake_inspect_snapshot(**kwargs)

    monkeypatch.setattr(agent_verification, "_get_harness", lambda: FakeHarness())

    text = await agent_verification.inspect_agent_snapshot("live")

    assert "State" in text
    assert "Latest Run" in text
    assert "Ledger" in text
    assert "Review Stats" in text
    assert "Memories" in text
    assert "run-2" in text


@pytest.mark.asyncio
async def test_prepare_demo_agent_portfolio_formats_seed_summary(monkeypatch):
    agent_verification = _import_backend_module("mcpserver.agent_verification")

    class FakeHarness:
        async def prepare_demo_portfolio(self, scenario_id: str):
            assert scenario_id == "demo-evolution"
            return {
                "scenario_id": "demo-evolution",
                "portfolio_id": "demo-evolution",
                "as_of_date": "2042-01-10",
                "week_start": "2042-01-05",
                "seed_run_id": "demo-seed:demo-evolution",
                "seeded_counts": {
                    "watchlist_items": 2,
                    "baseline_review_records": 2,
                    "baseline_memories": 1,
                },
            }

    monkeypatch.setattr(agent_verification, "_get_harness", lambda: FakeHarness())

    text = await agent_verification.prepare_demo_agent_portfolio("demo-evolution")

    assert "Demo Seed" in text
    assert "demo-evolution" in text
    assert "watchlist_items" in text


@pytest.mark.asyncio
async def test_verify_demo_agent_cycle_formats_seed_and_verification(monkeypatch):
    agent_verification = _import_backend_module("mcpserver.agent_verification")

    class FakeHarness:
        async def verify_demo_cycle(self, scenario_id: str, timeout_seconds: int = 30):
            assert scenario_id == "demo-evolution"
            assert timeout_seconds == 30
            return {
                "verification_status": "pass",
                "portfolio_id": "demo-evolution",
                "run_id": "run-demo",
                "brain_run_status": "completed",
                "failed_stage": None,
                "stages": [{"name": "brain_execute", "status": "pass"}],
                "checks": [{"name": "brain_run_completed", "status": "pass"}],
                "evolution_diff": {
                    "review_records_delta": 1,
                    "memories_retired": 1,
                    "weekly_summaries_delta": 1,
                    "signals": ["review_records_delta", "memories_retired"],
                },
                "evidence": {},
                "next_actions": [],
                "seed_summary": {
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "as_of_date": "2042-01-10",
                    "week_start": "2042-01-05",
                    "seeded_counts": {"baseline_review_records": 2},
                },
            }

    monkeypatch.setattr(agent_verification, "_get_harness", lambda: FakeHarness())

    text = await agent_verification.verify_demo_agent_cycle("demo-evolution")

    assert "Demo Seed" in text
    assert "run-demo" in text
    assert "Evolution Diff" in text
