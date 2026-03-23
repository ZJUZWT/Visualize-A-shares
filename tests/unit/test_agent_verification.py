"""Agent verification harness unit tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
import uuid
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


class TestAgentVerificationHarness:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    @staticmethod
    def _make_trade_input():
        from engine.agent.models import TradeInput

        return TradeInput(
            action="buy",
            stock_code="600519",
            stock_name="贵州茅台",
            price=1800.0,
            quantity=100,
            holding_type="mid_term",
            reason="test",
            thesis="test thesis",
            data_basis=["unit-test"],
            risk_note="test risk",
            invalidation="test invalidation",
            triggered_by="manual",
        )

    def test_verify_cycle_returns_pass_when_run_completes(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [{"stock_code": "600519"}],
                        "analysis_results": [{"stock_code": "600519"}],
                        "decisions": [{"stock_code": "600519", "action": "hold"}],
                        "plan_ids": [],
                        "trade_ids": [],
                        "state_before": {"position_level": 0.2},
                        "state_after": {"position_level": 0.2},
                        "execution_summary": {
                            "candidate_count": 1,
                            "analysis_count": 1,
                            "decision_count": 1,
                            "plan_count": 0,
                            "trade_count": 0,
                        },
                    },
                )

        class FakeReviewEngine:
            def __init__(self, db, memory_mgr):
                pass

            async def daily_review(self, as_of_date=None):
                return {"status": "completed", "records_created": 0}

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.verification.ReviewEngine", FakeReviewEngine
        ):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live"))

        assert result["verification_status"] == "pass"
        assert result["brain_run_status"] == "completed"
        assert result["failed_stage"] is None
        assert any(check["name"] == "brain_run_completed" for check in result["checks"])

    def test_verify_cycle_returns_warn_when_no_candidates(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [],
                        "analysis_results": [],
                        "decisions": [],
                        "plan_ids": [],
                        "trade_ids": [],
                        "state_before": {"position_level": 0.2},
                        "state_after": {"position_level": 0.2},
                        "execution_summary": {
                            "candidate_count": 0,
                            "analysis_count": 0,
                            "decision_count": 0,
                            "plan_count": 0,
                            "trade_count": 0,
                        },
                    },
                )

        class FakeReviewEngine:
            def __init__(self, db, memory_mgr):
                pass

            async def daily_review(self, as_of_date=None):
                return {"status": "completed", "records_created": 0}

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.verification.ReviewEngine", FakeReviewEngine
        ):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live"))

        assert result["verification_status"] == "warn"
        assert result["brain_run_status"] == "completed"
        assert any(check["name"] == "has_candidates" and check["status"] == "warn" for check in result["checks"])

    def test_verify_cycle_returns_fail_when_brain_failed(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "failed",
                        "error_message": "boom",
                    },
                )

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=False))

        assert result["verification_status"] == "fail"
        assert result["brain_run_status"] == "failed"
        assert result["failed_stage"] == "brain_execute"

    def test_inspect_snapshot_aggregates_core_views(self):
        from engine.agent.verification import AgentVerificationHarness

        run(
            self.svc.update_agent_state(
                "live",
                {
                    "position_level": 0.35,
                    "market_view": {"stance": "neutral"},
                },
            )
        )
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.agent_memories (
                    id, rule_text, category, source_run_id, status, confidence,
                    verify_count, verify_win, created_at, retired_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW(), NULL)
                """,
                ["memory-1", "不要追高", "timing", "run-0", "active", 0.8, 3, 2],
            )
        )
        run_id = run(self.svc.create_brain_run("live", "manual"))["id"]
        run(
            self.svc.update_brain_run(
                run_id,
                {
                    "status": "completed",
                    "state_before": {"position_level": 0.2},
                    "state_after": {"position_level": 0.35},
                    "execution_summary": {"candidate_count": 1, "decision_count": 1},
                    "plan_ids": [],
                    "trade_ids": [],
                },
            )
        )

        harness = AgentVerificationHarness(service=self.svc, db=self.db)
        snapshot = run(harness.inspect_snapshot("live"))

        assert snapshot["portfolio_id"] == "live"
        assert snapshot["state"]["position_level"] == 0.35
        assert snapshot["latest_run"]["id"] == run_id
        assert "asset_summary" in snapshot["ledger"]
        assert "total_reviews" in snapshot["review_stats"]
        assert len(snapshot["memories"]) == 1

    def test_verify_cycle_fails_on_timeout(self):
        from engine.agent.verification import AgentVerificationHarness

        class SlowAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await asyncio.sleep(0.05)

        with patch("engine.agent.verification.AgentBrain", SlowAgentBrain):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=False, timeout_seconds=0.001))

        assert result["verification_status"] == "fail"
        assert result["failed_stage"] == "brain_execute"
        assert result["brain_run_status"] == "running"

    def test_verify_cycle_fails_when_state_after_missing(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [{"stock_code": "600519"}],
                        "analysis_results": [{"stock_code": "600519"}],
                        "decisions": [{"stock_code": "600519", "action": "hold"}],
                        "plan_ids": [],
                        "trade_ids": [],
                        "state_before": {"position_level": 0.2},
                        "execution_summary": {
                            "candidate_count": 1,
                            "analysis_count": 1,
                            "decision_count": 1,
                            "plan_count": 0,
                            "trade_count": 0,
                        },
                    },
                )

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=False))

        assert result["verification_status"] == "fail"
        assert result["failed_stage"] == "invariant_check"
        assert any(
            check["name"] == "state_after_present" and check["status"] == "fail"
            for check in result["checks"]
        )

    def test_verify_cycle_fails_when_trade_ids_do_not_match_db(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [{"stock_code": "600519"}],
                        "analysis_results": [{"stock_code": "600519"}],
                        "decisions": [{"stock_code": "600519", "action": "buy"}],
                        "plan_ids": [],
                        "trade_ids": [str(uuid.uuid4())],
                        "state_before": {"position_level": 0.2},
                        "state_after": {"position_level": 0.35},
                        "execution_summary": {
                            "candidate_count": 1,
                            "analysis_count": 1,
                            "decision_count": 1,
                            "plan_count": 0,
                            "trade_count": 1,
                        },
                    },
                )

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=False))

        assert result["verification_status"] == "fail"
        assert result["failed_stage"] == "invariant_check"
        assert any(
            check["name"] == "trade_ids_consistent" and check["status"] == "fail"
            for check in result["checks"]
        )

    def test_verify_cycle_fails_when_review_errors(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [{"stock_code": "600519"}],
                        "analysis_results": [{"stock_code": "600519"}],
                        "decisions": [{"stock_code": "600519", "action": "hold"}],
                        "plan_ids": [],
                        "trade_ids": [],
                        "state_before": {"position_level": 0.2},
                        "state_after": {"position_level": 0.2},
                        "execution_summary": {
                            "candidate_count": 1,
                            "analysis_count": 1,
                            "decision_count": 1,
                            "plan_count": 0,
                            "trade_count": 0,
                        },
                    },
                )

        class FailingReviewEngine:
            def __init__(self, db, memory_mgr):
                pass

            async def daily_review(self, as_of_date=None):
                raise RuntimeError("review boom")

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.verification.ReviewEngine", FailingReviewEngine
        ):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=True))

        assert result["verification_status"] == "fail"
        assert result["failed_stage"] == "review_daily"
        assert any(
            check["name"] == "daily_review_completed" and check["status"] == "fail"
            for check in result["checks"]
        )

    def test_verify_cycle_plan_ids_consistency_ignores_order(self):
        from engine.agent.models import TradePlanInput
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                plan_a = await self_ref.svc.create_plan(
                    TradePlanInput(
                        stock_code="600519",
                        stock_name="贵州茅台",
                        direction="buy",
                        reasoning="a",
                        source_type="agent",
                    ),
                    source_run_id=run_id,
                )
                plan_b = await self_ref.svc.create_plan(
                    TradePlanInput(
                        stock_code="601318",
                        stock_name="中国平安",
                        direction="buy",
                        reasoning="b",
                        source_type="agent",
                    ),
                    source_run_id=run_id,
                )
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [{"stock_code": "600519"}],
                        "analysis_results": [{"stock_code": "600519"}],
                        "decisions": [{"stock_code": "600519", "action": "buy"}],
                        "plan_ids": [plan_b["id"], plan_a["id"]],
                        "trade_ids": [],
                        "state_before": {"position_level": 0.2},
                        "state_after": {"position_level": 0.3},
                        "execution_summary": {
                            "candidate_count": 1,
                            "analysis_count": 1,
                            "decision_count": 1,
                            "plan_count": 2,
                            "trade_count": 0,
                        },
                    },
                )

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=False))

        assert result["verification_status"] == "pass"
        assert any(
            check["name"] == "plan_ids_consistent" and check["status"] == "pass"
            for check in result["checks"]
        )

    def test_verify_cycle_skips_review_when_invariants_fail(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [{"stock_code": "600519"}],
                        "analysis_results": [{"stock_code": "600519"}],
                        "decisions": [{"stock_code": "600519", "action": "hold"}],
                        "plan_ids": [],
                        "trade_ids": [],
                        "state_before": {"position_level": 0.2},
                        # force invariant failure before review
                        "execution_summary": {
                            "candidate_count": 1,
                            "analysis_count": 1,
                            "decision_count": 1,
                            "plan_count": 0,
                            "trade_count": 0,
                        },
                    },
                )

        class ShouldNotRunReviewEngine:
            called = False

            def __init__(self, db, memory_mgr):
                pass

            async def daily_review(self, as_of_date=None):
                ShouldNotRunReviewEngine.called = True
                raise RuntimeError("review should not run when invariants fail")

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain), patch(
            "engine.agent.verification.ReviewEngine", ShouldNotRunReviewEngine
        ):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=True))

        assert result["verification_status"] == "fail"
        assert result["failed_stage"] == "invariant_check"
        assert ShouldNotRunReviewEngine.called is False
        assert "review_error" not in result["evidence"]

    def test_verify_cycle_fails_when_state_payload_shape_is_not_dict(self):
        from engine.agent.verification import AgentVerificationHarness

        class FakeAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                await self_ref.svc.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [{"stock_code": "600519"}],
                        "analysis_results": [{"stock_code": "600519"}],
                        "decisions": [{"stock_code": "600519", "action": "hold"}],
                        "plan_ids": [],
                        "trade_ids": [],
                        "state_before": {"position_level": 0.2},
                        "state_after": ["bad-shape"],
                        "execution_summary": {"candidate_count": 1},
                    },
                )

        self_ref = self
        with patch("engine.agent.verification.AgentBrain", FakeAgentBrain):
            harness = AgentVerificationHarness(service=self.svc, db=self.db)
            result = run(harness.verify_cycle("live", include_review=False))

        assert result["verification_status"] == "fail"
        assert result["failed_stage"] == "invariant_check"
        assert any(
            check["name"] == "state_after_present" and check["status"] == "fail"
            for check in result["checks"]
        )
