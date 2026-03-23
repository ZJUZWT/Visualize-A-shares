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
            "checks": [
                {"name": "brain_run_completed", "status": "pass"},
                {"name": "has_candidates", "status": "warn", "detail": 0},
            ],
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
    assert "Checks" in text
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
