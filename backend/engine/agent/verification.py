"""Verification harness for Main Agent cycle checks."""
from __future__ import annotations

import asyncio
from typing import Any

from engine.agent.brain import AgentBrain
from engine.agent.db import AgentDB
from engine.agent.memory import MemoryManager
from engine.agent.review import ReviewEngine
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator


class AgentVerificationHarness:
    """Run a minimal end-to-end verification pass for a portfolio."""

    def __init__(
        self,
        service: AgentService | None = None,
        db: AgentDB | None = None,
    ):
        self.db = db or AgentDB.get_instance()
        self.service = service or AgentService(db=self.db, validator=TradeValidator())

    @staticmethod
    def _build_result(
        *,
        verification_status: str,
        portfolio_id: str,
        run_id: str | None,
        brain_run_status: str | None,
        failed_stage: str | None,
        checks: list[dict[str, Any]],
        evidence: dict[str, Any],
        next_actions: list[str],
        review_result: dict[str, Any] | None = None,
        include_weekly: bool = False,
    ) -> dict[str, Any]:
        return {
            "verification_status": verification_status,
            "portfolio_id": portfolio_id,
            "run_id": run_id,
            "brain_run_status": brain_run_status,
            "failed_stage": failed_stage,
            "checks": checks,
            "evidence": evidence,
            "review_result": review_result,
            "include_weekly": include_weekly,
            "next_actions": next_actions,
        }

    async def _check_run_invariants(self, run: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        evidence: dict[str, Any] = {}

        for field_name in ("state_before", "state_after", "execution_summary"):
            value = run.get(field_name)
            check_name = f"{field_name}_present"
            if isinstance(value, dict) and len(value) > 0:
                checks.append({"name": check_name, "status": "pass"})
                evidence[check_name] = value
            else:
                checks.append({"name": check_name, "status": "fail"})

        plan_rows = await self.db.execute_read(
            """
            SELECT id
            FROM agent.trade_plans
            WHERE source_run_id = ?
            ORDER BY id
            """,
            [run["id"]],
        )
        actual_plan_ids = [row["id"] for row in plan_rows]
        expected_plan_ids = list(run.get("plan_ids") or [])
        evidence["expected_plan_ids"] = expected_plan_ids
        evidence["actual_plan_ids"] = actual_plan_ids
        expected_plan_id_set = {str(item) for item in expected_plan_ids}
        actual_plan_id_set = {str(item) for item in actual_plan_ids}
        plan_ids_consistent = (
            expected_plan_id_set == actual_plan_id_set
            and len(expected_plan_ids) == len(actual_plan_ids)
        )
        checks.append(
            {
                "name": "plan_ids_consistent",
                "status": "pass" if plan_ids_consistent else "fail",
                "detail": {"expected": expected_plan_ids, "actual": actual_plan_ids},
            }
        )

        trade_rows = await self.db.execute_read(
            """
            SELECT id
            FROM agent.trades
            WHERE source_run_id = ?
            ORDER BY id
            """,
            [run["id"]],
        )
        actual_trade_ids = [row["id"] for row in trade_rows]
        expected_trade_ids = list(run.get("trade_ids") or [])
        evidence["expected_trade_ids"] = expected_trade_ids
        evidence["actual_trade_ids"] = actual_trade_ids
        expected_trade_id_set = {str(item) for item in expected_trade_ids}
        actual_trade_id_set = {str(item) for item in actual_trade_ids}
        trade_ids_consistent = (
            expected_trade_id_set == actual_trade_id_set
            and len(expected_trade_ids) == len(actual_trade_ids)
        )
        checks.append(
            {
                "name": "trade_ids_consistent",
                "status": "pass" if trade_ids_consistent else "fail",
                "detail": {"expected": expected_trade_ids, "actual": actual_trade_ids},
            }
        )

        return checks, evidence

    async def verify_cycle(
        self,
        portfolio_id: str,
        as_of_date: str | None = None,
        include_review: bool = True,
        include_weekly: bool = False,
        require_trade: bool = False,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        evidence: dict[str, Any] = {}
        review_result = None
        run_id: str | None = None
        failed_stage: str | None = None
        brain_status: str | None = None

        try:
            run_record = await self.service.create_brain_run(portfolio_id, run_type="manual")
        except Exception as exc:
            failed_stage = "brain_run_create"
            checks.append({"name": "brain_run_created", "status": "fail", "detail": str(exc)})
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=None,
                brain_run_status=None,
                failed_stage=failed_stage,
                checks=checks,
                evidence=evidence,
                next_actions=["verify_portfolio_setup"],
                include_weekly=include_weekly,
            )

        run_id = run_record["id"]
        evidence["brain_run_created"] = run_record
        checks.append({"name": "brain_run_created", "status": "pass"})
        brain = AgentBrain(portfolio_id)
        try:
            await asyncio.wait_for(brain.execute(run_id), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            failed_stage = "brain_execute"
            checks.append({"name": "brain_run_completed", "status": "fail", "detail": "timeout"})
            timed_out_run = await self.service.get_brain_run(run_id)
            evidence["brain_run"] = timed_out_run
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=timed_out_run.get("status"),
                failed_stage=failed_stage,
                checks=checks,
                evidence=evidence,
                next_actions=["increase_timeout_or_check_brain_logs"],
                include_weekly=include_weekly,
            )

        run = await self.service.get_brain_run(run_id)
        evidence["brain_run"] = run
        brain_status = run.get("status")

        if brain_status == "completed":
            checks.append({"name": "brain_run_completed", "status": "pass"})
        else:
            failed_stage = "brain_execute"
            checks.append({"name": "brain_run_completed", "status": "fail", "detail": brain_status})
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=brain_status,
                failed_stage=failed_stage,
                checks=checks,
                evidence=evidence,
                next_actions=["inspect_brain_run_error"],
                include_weekly=include_weekly,
            )

        candidate_count = len(run.get("candidates") or [])
        if candidate_count > 0:
            checks.append({"name": "has_candidates", "status": "pass", "detail": candidate_count})
        else:
            checks.append({"name": "has_candidates", "status": "warn", "detail": 0})

        trade_count = len(run.get("trade_ids") or [])
        if require_trade and trade_count == 0:
            checks.append({"name": "has_trades", "status": "fail", "detail": 0})
            failed_stage = "invariant_check"
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=brain_status,
                failed_stage=failed_stage,
                checks=checks,
                evidence=evidence,
                next_actions=["inspect_decision_gating_and_market_data"],
                include_weekly=include_weekly,
            )

        invariant_checks, invariant_evidence = await self._check_run_invariants(run)
        checks.extend(invariant_checks)
        evidence.update(invariant_evidence)

        if any(check["status"] == "fail" for check in invariant_checks):
            failed_stage = "invariant_check"
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=brain_status,
                failed_stage=failed_stage,
                checks=checks,
                evidence=evidence,
                next_actions=["inspect_brain_run_and_execution_records"],
                review_result=review_result,
                include_weekly=include_weekly,
            )

        if include_review:
            review_engine = ReviewEngine(self.db, MemoryManager(self.db))
            try:
                review_result = await review_engine.daily_review(as_of_date=as_of_date)
            except Exception as exc:
                failed_stage = "review_daily"
                evidence["review_error"] = str(exc)
                checks.append({"name": "daily_review_completed", "status": "fail", "detail": str(exc)})
                return self._build_result(
                    verification_status="fail",
                    portfolio_id=portfolio_id,
                    run_id=run_id,
                    brain_run_status=brain_status,
                    failed_stage=failed_stage,
                    checks=checks,
                    evidence=evidence,
                    next_actions=["inspect_review_dependencies"],
                    include_weekly=include_weekly,
                )
            evidence["review"] = review_result
            checks.append({"name": "daily_review_completed", "status": "pass"})

        status = "pass"
        if any(check["status"] == "warn" for check in checks):
            status = "warn"

        return self._build_result(
            verification_status=status,
            portfolio_id=portfolio_id,
            run_id=run_id,
            brain_run_status=brain_status,
            failed_stage=failed_stage,
            checks=checks,
            evidence=evidence,
            next_actions=[],
            review_result=review_result,
            include_weekly=include_weekly,
        )

    async def inspect_snapshot(
        self,
        portfolio_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        state = await self.service.get_agent_state(portfolio_id)
        if isinstance(state.get("position_level"), str):
            try:
                state["position_level"] = float(state["position_level"])
            except ValueError:
                pass
        if run_id:
            latest_run = await self.service.get_brain_run(run_id)
        else:
            runs = await self.service.list_brain_runs(portfolio_id, limit=1)
            latest_run = runs[0] if runs else None

        ledger = await self.service.get_ledger_overview(portfolio_id)
        review_stats = await self.service.get_review_stats(portfolio_id, days=30)
        memories = await self.service.list_memories(status="active")

        return {
            "portfolio_id": portfolio_id,
            "state": state,
            "latest_run": latest_run,
            "ledger": ledger,
            "review_stats": review_stats,
            "memories": memories,
        }
