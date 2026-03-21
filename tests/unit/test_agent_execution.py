"""Execution ledger 协调器单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
from unittest.mock import patch


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
    return db, svc


def _make_decision(**overrides):
    decision = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "action": "buy",
        "price": 1800.0,
        "quantity": 100,
        "holding_type": "mid_term",
        "reasoning": "景气度改善",
        "take_profit": 2100.0,
        "stop_loss": 1700.0,
        "risk_note": "估值偏高",
        "invalidation": "基本面转弱",
    }
    decision.update(overrides)
    return decision


class TestExecutionCoordinator:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_create_plan_from_decision_writes_source_run_id(self):
        from engine.agent.execution import ExecutionCoordinator

        execution = ExecutionCoordinator("live", self.svc)
        plan = run(execution.create_plan_from_decision("run-1", _make_decision()))

        assert plan["source_run_id"] == "run-1"
        assert plan["source_type"] == "agent"
        assert plan["stock_code"] == "600519"

    def test_execute_plan_writes_trade_and_strategy_links(self):
        from engine.agent.execution import ExecutionCoordinator

        execution = ExecutionCoordinator("live", self.svc)
        plan = run(execution.create_plan_from_decision("run-1", _make_decision()))

        result = run(execution.execute_plan("run-1", plan["id"], _make_decision()))

        assert result["plan_id"] == plan["id"]
        assert result["trade_id"] is not None
        assert result["strategy_id"] is not None

        trade = run(self.svc.get_trades("live", limit=1))[0]
        assert trade["source_run_id"] == "run-1"
        assert trade["source_plan_id"] == plan["id"]
        assert trade["source_strategy_id"] == result["strategy_id"]
        assert trade["source_strategy_version"] == 1

        strategy = run(self.svc.get_strategy("live", result["position_id"]))[0]
        assert strategy["source_run_id"] == "run-1"

        plan_after = run(self.svc.get_plan(plan["id"]))
        assert plan_after["status"] == "executing"


class TestBrainExecutionDelegation:
    def test_execute_decisions_uses_execution_coordinator(self):
        from engine.agent.brain import AgentBrain

        class ForbiddenService:
            async def create_plan(self, *args, **kwargs):
                raise AssertionError("brain should not call create_plan directly")

            async def execute_trade(self, *args, **kwargs):
                raise AssertionError("brain should not call execute_trade directly")

            async def update_plan(self, *args, **kwargs):
                raise AssertionError("brain should not call update_plan directly")

        class FakeExecution:
            def __init__(self):
                self.created = []
                self.executed = []

            async def create_plan_from_decision(self, run_id, decision):
                self.created.append((run_id, decision["stock_code"]))
                return {"id": "plan-1"}

            async def execute_plan(self, run_id, plan_id, decision):
                self.executed.append((run_id, plan_id, decision["stock_code"]))
                return {"plan_id": plan_id, "trade_id": "trade-1", "skipped": False}

        brain = AgentBrain.__new__(AgentBrain)
        brain.portfolio_id = "live"
        brain.service = ForbiddenService()
        brain.execution = FakeExecution()

        plan_ids, trade_ids = run(brain._execute_decisions("run-1", [
            _make_decision(),
            _make_decision(action="hold", stock_code="601318", stock_name="中国平安"),
        ]))

        assert plan_ids == ["plan-1"]
        assert trade_ids == ["trade-1"]
        assert brain.execution.created == [("run-1", "600519")]
        assert brain.execution.executed == [("run-1", "plan-1", "600519")]
