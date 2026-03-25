"""Agent backtest MCP wrapper tests."""
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
async def test_run_agent_backtest_returns_operator_friendly_markdown(monkeypatch):
    agent_backtest = _import_backend_module("mcpserver.agent_backtest")

    class FakeEngine:
        async def run_backtest(self, **kwargs):
            assert kwargs["portfolio_id"] == "live"
            return {
                "id": "run-1",
                "status": "completed",
                "days": [{"date": "2026-03-20"}],
                "trades": [{"id": "trade-1"}],
                "review_count": 4,
                "memory_delta": {"total": 1, "active": 1, "retired": 0},
            }

        async def get_run_summary(self, run_id: str):
            assert run_id == "run-1"
            return {
                "run_id": "run-1",
                "status": "completed",
                "trade_count": 1,
                "review_count": 4,
                "total_return": 0.023,
                "max_drawdown": 0.01,
                "buy_and_hold_return": 0.04,
                "memory_added": 1,
                "memory_updated": 0,
                "memory_retired": 0,
            }

    monkeypatch.setattr(agent_backtest, "_get_engine", lambda: FakeEngine())

    text = await agent_backtest.run_agent_backtest("live", "2026-03-18", "2026-03-20")

    assert "Agent Backtest" in text
    assert "run-1" in text
    assert "total_return" in text
    assert "buy_and_hold_return" in text


@pytest.mark.asyncio
async def test_get_agent_backtest_summary_returns_structured_json(monkeypatch):
    agent_backtest = _import_backend_module("mcpserver.agent_backtest")

    class FakeEngine:
        async def get_run_summary(self, run_id: str):
            assert run_id == "run-1"
            return {
                "run_id": "run-1",
                "status": "completed",
                "total_return": 0.023,
                "max_drawdown": 0.01,
                "trade_count": 3,
                "win_rate": 0.5,
                "review_count": 4,
                "memory_added": 1,
                "memory_updated": 0,
                "memory_retired": 0,
                "buy_and_hold_return": 0.04,
            }

    monkeypatch.setattr(agent_backtest, "_get_engine", lambda: FakeEngine())

    text = await agent_backtest.get_agent_backtest_summary("run-1")
    data = json.loads(text)

    assert data["run_id"] == "run-1"
    assert "total_return" in data
    assert "buy_and_hold_return" in data


@pytest.mark.asyncio
async def test_get_agent_backtest_day_returns_one_day_evidence(monkeypatch):
    agent_backtest = _import_backend_module("mcpserver.agent_backtest")

    class FakeEngine:
        db = object()

        async def list_run_days(self, run_id: str):
            assert run_id == "run-1"
            return [
                {
                    "trade_date": "2026-03-19",
                    "review_created": True,
                    "memory_delta": {"total": 0, "active": 0, "retired": 0},
                }
            ]

        async def get_run_summary(self, run_id: str):
            return {
                "run_id": "run-1",
                "backtest_portfolio_id": "bt:run-1",
            }

    async def fake_load_day_details(engine, day_row: dict):
        assert day_row["trade_date"] == "2026-03-19"
        return {
            "brain_run_id": "brain-1",
            "trades": [{"id": "trade-1", "stock_code": "600519"}],
        }

    monkeypatch.setattr(agent_backtest, "_get_engine", lambda: FakeEngine())
    monkeypatch.setattr(agent_backtest, "_load_day_details", fake_load_day_details)

    text = await agent_backtest.get_agent_backtest_day("run-1", "2026-03-19")

    assert "brain-1" in text
    assert "trade-1" in text
    assert "memory_delta" in text


@pytest.mark.asyncio
async def test_get_agent_backtest_day_prefers_brain_run_id_over_created_at_windows(monkeypatch):
    agent_backtest = _import_backend_module("mcpserver.agent_backtest")

    class FakeDB:
        async def execute_read(self, sql: str, params=None):
            if "FROM agent.trades" in sql and "source_run_id = ?" in sql:
                assert params == ["brain-1"]
                return [{"id": "trade-1", "stock_code": "600519", "stock_name": "贵州茅台", "action": "buy", "quantity": 100, "price": 100.0}]
            if "created_at" in sql:
                raise AssertionError("created_at window lookup should not be used")
            return []

    class FakeEngine:
        def __init__(self):
            self.db = FakeDB()

        async def list_run_days(self, run_id: str):
            return [
                {
                    "trade_date": "2026-03-19",
                    "brain_run_id": "brain-1",
                    "review_created": True,
                    "memory_delta": {"total": 0, "active": 0, "retired": 0},
                }
            ]

        async def get_run_summary(self, run_id: str):
            return {
                "run_id": "run-1",
                "backtest_portfolio_id": "bt:run-1",
            }

    monkeypatch.setattr(agent_backtest, "_get_engine", lambda: FakeEngine())

    text = await agent_backtest.get_agent_backtest_day("run-1", "2026-03-19")

    assert "brain-1" in text
    assert "trade-1" in text
