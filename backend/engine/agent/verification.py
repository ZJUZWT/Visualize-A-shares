"""Verification harness for Main Agent cycle checks."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from engine.agent.brain import AgentBrain
from engine.agent.db import AgentDB
from engine.agent.memory import MemoryManager
from engine.agent.review import ReviewEngine
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator

DEFAULT_VERIFY_TIMEOUT_SECONDS = 45


class AgentVerificationHarness:
    """Run a minimal end-to-end verification pass for a portfolio."""

    _VERIFY_MAX_CANDIDATES = 1
    _VERIFY_QUANT_TOP_N = 1

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
        stages: list[dict[str, Any]],
        evolution_diff: dict[str, Any] | None,
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
            "stages": stages,
            "checks": checks,
            "evidence": evidence,
            "evolution_diff": evolution_diff or {},
            "review_result": review_result,
            "include_weekly": include_weekly,
            "next_actions": next_actions,
        }

    @staticmethod
    def _record_stage(
        stages: list[dict[str, Any]],
        *,
        name: str,
        status: str,
        detail: Any = None,
    ) -> None:
        stage = {"name": name, "status": status}
        if detail is not None:
            stage["detail"] = detail
        stages.append(stage)

    @staticmethod
    def _snapshot_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "latest_run_id": (snapshot.get("latest_run") or {}).get("id"),
            "memory_count": len(snapshot.get("memories") or []),
            "review_record_count": len(snapshot.get("review_records") or []),
            "daily_review_count": len(snapshot.get("daily_reviews") or []),
            "weekly_reflection_count": len(snapshot.get("weekly_reflections") or []),
            "weekly_summary_count": len(snapshot.get("weekly_summaries") or []),
            "strategy_history_count": len(snapshot.get("strategy_history") or []),
        }

    @staticmethod
    def _build_memory_diff(
        before_memories: list[dict[str, Any]],
        after_memories: list[dict[str, Any]],
    ) -> dict[str, Any]:
        before_by_id = {item["id"]: item for item in before_memories if item.get("id")}
        after_by_id = {item["id"]: item for item in after_memories if item.get("id")}

        added_ids = sorted(set(after_by_id) - set(before_by_id))
        updated_ids: list[str] = []
        retired_ids: list[str] = []

        tracked_fields = ("confidence", "verify_count", "verify_win", "status")
        for memory_id in sorted(set(after_by_id) & set(before_by_id)):
            before_item = before_by_id[memory_id]
            after_item = after_by_id[memory_id]
            if any(before_item.get(field) != after_item.get(field) for field in tracked_fields):
                updated_ids.append(memory_id)
            if before_item.get("status") != "retired" and after_item.get("status") == "retired":
                retired_ids.append(memory_id)

        return {
            "memories_added": len(added_ids),
            "memories_updated": len(updated_ids),
            "memories_retired": len(retired_ids),
            "memory_change_ids": sorted(set(added_ids + updated_ids)),
            "memory_added_ids": added_ids,
            "memory_updated_ids": updated_ids,
            "memory_retired_ids": retired_ids,
        }

    def _build_evolution_diff(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        before_strategy_ids = {
            item.get("run_id")
            for item in (before.get("strategy_history") or [])
            if item.get("run_id")
        }
        after_strategy_ids = {
            item.get("run_id")
            for item in (after.get("strategy_history") or [])
            if item.get("run_id")
        }
        memory_diff = self._build_memory_diff(
            before.get("memories") or [],
            after.get("memories") or [],
        )
        strategy_history_changed = bool(before_strategy_ids) and after_strategy_ids != before_strategy_ids

        diff = {
            "brain_runs_delta": len(after.get("brain_runs") or []) - len(before.get("brain_runs") or []),
            "review_records_delta": len(after.get("review_records") or []) - len(before.get("review_records") or []),
            "daily_reviews_delta": len(after.get("daily_reviews") or []) - len(before.get("daily_reviews") or []),
            "weekly_summaries_delta": len(after.get("weekly_summaries") or []) - len(before.get("weekly_summaries") or []),
            "weekly_reflections_delta": len(after.get("weekly_reflections") or []) - len(before.get("weekly_reflections") or []),
            "strategy_history_count_delta": len(after.get("strategy_history") or []) - len(before.get("strategy_history") or []),
            "strategy_history_changed": strategy_history_changed,
            **memory_diff,
        }

        signals: list[str] = []
        if diff["review_records_delta"] > 0:
            signals.append("review_records_delta")
        if diff["daily_reviews_delta"] > 0:
            signals.append("daily_reviews_delta")
        if diff["memories_added"] > 0:
            signals.append("memories_added")
        if diff["memories_updated"] > 0:
            signals.append("memories_updated")
        if diff["memories_retired"] > 0:
            signals.append("memories_retired")
        if diff["weekly_reflections_delta"] > 0:
            signals.append("weekly_reflections_delta")
        if diff["weekly_summaries_delta"] > 0:
            signals.append("weekly_summaries_delta")
        if strategy_history_changed:
            signals.append("strategy_history_changed")

        diff["signals"] = signals
        return diff

    def _prepare_verification_brain(self, brain: Any) -> Any:
        original_select = getattr(brain, "_select_candidates", None)
        if original_select is None:
            return brain

        async def _limited_select(config: dict) -> list[dict]:
            limited_config = dict(config or {})
            max_candidates = int(limited_config.get("max_candidates") or self._VERIFY_MAX_CANDIDATES)
            quant_top_n = int(limited_config.get("quant_top_n") or self._VERIFY_QUANT_TOP_N)
            limited_config["max_candidates"] = min(max_candidates, self._VERIFY_MAX_CANDIDATES)
            limited_config["quant_top_n"] = min(quant_top_n, self._VERIFY_QUANT_TOP_N)
            return await original_select(limited_config)

        brain._select_candidates = _limited_select
        return brain

    async def _collect_snapshot(
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

        brain_runs = await self.service.list_brain_runs(portfolio_id, limit=50)
        latest_run = None
        if run_id:
            latest_run = await self.service.get_brain_run(run_id)
        elif brain_runs:
            latest_run = brain_runs[0]

        ledger = await self.service.get_ledger_overview(portfolio_id)
        review_records = await self.service.list_review_records(portfolio_id, days=3650)
        review_stats = await self.service.get_review_stats(portfolio_id, days=30)
        memories = await self.service.list_memories(status="all")
        strategy_history = await self.service.list_strategy_history(portfolio_id, limit=50)
        daily_reviews = await self.db.execute_read(
            """
            SELECT *
            FROM agent.daily_reviews
            ORDER BY review_date DESC, created_at DESC
            LIMIT 50
            """
        )
        weekly_reflections = await self.db.execute_read(
            """
            SELECT *
            FROM agent.weekly_reflections
            ORDER BY week_end DESC, created_at DESC
            LIMIT 50
            """
        )
        weekly_summaries = await self.service.list_weekly_summaries(limit=50)

        return {
            "portfolio_id": portfolio_id,
            "state": state,
            "latest_run": latest_run,
            "brain_runs": brain_runs,
            "ledger": ledger,
            "review_records": review_records,
            "review_stats": review_stats,
            "memories": memories,
            "strategy_history": strategy_history,
            "daily_reviews": daily_reviews,
            "weekly_reflections": weekly_reflections,
            "weekly_summaries": weekly_summaries,
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
        timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS,
        brain_factory: Callable[[str], Any] | None = None,
    ) -> dict[str, Any]:
        stages: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        evidence: dict[str, Any] = {}
        evolution_diff: dict[str, Any] | None = None
        review_result = None
        run_id: str | None = None
        failed_stage: str | None = None
        brain_status: str | None = None
        snapshot_before = await self._collect_snapshot(portfolio_id)
        evidence["snapshot_before"] = snapshot_before
        self._record_stage(
            stages,
            name="snapshot_before",
            status="pass",
            detail=self._snapshot_detail(snapshot_before),
        )

        try:
            run_record = await self.service.create_brain_run(portfolio_id, run_type="manual")
        except Exception as exc:
            failed_stage = "brain_run_create"
            checks.append({"name": "brain_run_created", "status": "fail", "detail": str(exc)})
            self._record_stage(stages, name="brain_execute", status="fail", detail="create_failed")
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=None,
                brain_run_status=None,
                failed_stage=failed_stage,
                stages=stages,
                checks=checks,
                evidence=evidence,
                evolution_diff=evolution_diff,
                next_actions=["verify_portfolio_setup"],
                include_weekly=include_weekly,
            )

        run_id = run_record["id"]
        evidence["brain_run_created"] = run_record
        checks.append({"name": "brain_run_created", "status": "pass"})
        brain = brain_factory(portfolio_id) if brain_factory else AgentBrain(portfolio_id)
        brain = self._prepare_verification_brain(brain)
        try:
            await asyncio.wait_for(brain.execute(run_id), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            failed_stage = "brain_execute"
            checks.append({"name": "brain_run_completed", "status": "fail", "detail": "timeout"})
            timed_out_run = await self.service.get_brain_run(run_id)
            if timed_out_run.get("status") == "running":
                await self.service.update_brain_run(
                    run_id,
                    {
                        "status": "failed",
                        "current_step": None,
                        "error_message": f"verification timeout after {timeout_seconds}s",
                    },
                )
                timed_out_run = await self.service.get_brain_run(run_id)
            evidence["brain_run"] = timed_out_run
            self._record_stage(stages, name="brain_execute", status="fail", detail="timeout")
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=timed_out_run.get("status"),
                failed_stage=failed_stage,
                stages=stages,
                checks=checks,
                evidence=evidence,
                evolution_diff=evolution_diff,
                next_actions=["increase_timeout_or_check_brain_logs"],
                include_weekly=include_weekly,
            )

        run = await self.service.get_brain_run(run_id)
        evidence["brain_run"] = run
        brain_status = run.get("status")

        if brain_status == "completed":
            checks.append({"name": "brain_run_completed", "status": "pass"})
            self._record_stage(
                stages,
                name="brain_execute",
                status="pass",
                detail={"run_id": run_id, "status": brain_status},
            )
        else:
            failed_stage = "brain_execute"
            checks.append({"name": "brain_run_completed", "status": "fail", "detail": brain_status})
            self._record_stage(stages, name="brain_execute", status="fail", detail=brain_status)
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=brain_status,
                failed_stage=failed_stage,
                stages=stages,
                checks=checks,
                evidence=evidence,
                evolution_diff=evolution_diff,
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
            self._record_stage(stages, name="invariant_check", status="fail", detail="require_trade")
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=brain_status,
                failed_stage=failed_stage,
                stages=stages,
                checks=checks,
                evidence=evidence,
                evolution_diff=evolution_diff,
                next_actions=["inspect_decision_gating_and_market_data"],
                include_weekly=include_weekly,
            )

        invariant_checks, invariant_evidence = await self._check_run_invariants(run)
        checks.extend(invariant_checks)
        evidence.update(invariant_evidence)

        if any(check["status"] == "fail" for check in invariant_checks):
            failed_stage = "invariant_check"
            self._record_stage(stages, name="invariant_check", status="fail", detail="check_failed")
            return self._build_result(
                verification_status="fail",
                portfolio_id=portfolio_id,
                run_id=run_id,
                brain_run_status=brain_status,
                failed_stage=failed_stage,
                stages=stages,
                checks=checks,
                evidence=evidence,
                evolution_diff=evolution_diff,
                next_actions=["inspect_brain_run_and_execution_records"],
                review_result=review_result,
                include_weekly=include_weekly,
            )
        self._record_stage(stages, name="invariant_check", status="pass")

        if include_review:
            review_engine = ReviewEngine(self.db, MemoryManager(self.db))
            try:
                daily_review_result = await review_engine.daily_review(as_of_date=as_of_date)
            except Exception as exc:
                failed_stage = "review_daily"
                evidence["review_error"] = str(exc)
                checks.append({"name": "daily_review_completed", "status": "fail", "detail": str(exc)})
                self._record_stage(stages, name="daily_review", status="fail", detail=str(exc))
                return self._build_result(
                    verification_status="fail",
                    portfolio_id=portfolio_id,
                    run_id=run_id,
                    brain_run_status=brain_status,
                    failed_stage=failed_stage,
                    stages=stages,
                    checks=checks,
                    evidence=evidence,
                    evolution_diff=evolution_diff,
                    next_actions=["inspect_review_dependencies"],
                    include_weekly=include_weekly,
                )
            review_result = daily_review_result
            evidence["daily_review"] = daily_review_result
            evidence["review"] = review_result
            checks.append({"name": "daily_review_completed", "status": "pass"})
            self._record_stage(
                stages,
                name="daily_review",
                status="pass",
                detail={"records_created": daily_review_result.get("records_created", 0)},
            )

            if include_weekly:
                try:
                    weekly_review_result = await review_engine.weekly_review(as_of_date=as_of_date)
                except Exception as exc:
                    failed_stage = "review_weekly"
                    evidence["review_error"] = str(exc)
                    checks.append({"name": "weekly_review_completed", "status": "fail", "detail": str(exc)})
                    self._record_stage(stages, name="weekly_review", status="fail", detail=str(exc))
                    return self._build_result(
                        verification_status="fail",
                        portfolio_id=portfolio_id,
                        run_id=run_id,
                        brain_run_status=brain_status,
                        failed_stage=failed_stage,
                        stages=stages,
                        checks=checks,
                        evidence=evidence,
                        evolution_diff=evolution_diff,
                        next_actions=["inspect_weekly_review_dependencies"],
                        include_weekly=include_weekly,
                    )
                review_result = weekly_review_result
                evidence["weekly_review"] = weekly_review_result
                evidence["review"] = review_result
                checks.append({"name": "weekly_review_completed", "status": "pass"})
                self._record_stage(
                    stages,
                    name="weekly_review",
                    status="pass",
                    detail={"summary_id": weekly_review_result.get("summary_id")},
                )

        snapshot_after = await self._collect_snapshot(portfolio_id, run_id=run_id)
        evidence["snapshot_after"] = snapshot_after
        self._record_stage(
            stages,
            name="snapshot_after",
            status="pass",
            detail=self._snapshot_detail(snapshot_after),
        )

        evolution_diff = self._build_evolution_diff(snapshot_before, snapshot_after)
        evidence["evolution_diff"] = evolution_diff
        evolution_stage_status = "pass" if evolution_diff.get("signals") else "warn"
        self._record_stage(
            stages,
            name="evolution_diff",
            status=evolution_stage_status,
            detail={"signals": evolution_diff.get("signals", [])},
        )

        status = "pass" if evolution_diff.get("signals") else "warn"
        if any(check["status"] == "warn" for check in checks):
            status = "warn"

        next_actions: list[str] = []
        if status == "warn":
            next_actions.append("inspect_review_and_memory_evolution_inputs")

        return self._build_result(
            verification_status=status,
            portfolio_id=portfolio_id,
            run_id=run_id,
            brain_run_status=brain_status,
            failed_stage=failed_stage,
            stages=stages,
            checks=checks,
            evidence=evidence,
            evolution_diff=evolution_diff,
            next_actions=next_actions,
            review_result=review_result,
            include_weekly=include_weekly,
        )

    async def inspect_snapshot(
        self,
        portfolio_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._collect_snapshot(portfolio_id, run_id=run_id)

    async def prepare_demo_portfolio(
        self,
        scenario_id: str = "demo-evolution",
    ) -> dict[str, Any]:
        from engine.agent.demo_scenarios import DemoAgentScenarioSeeder

        seeder = DemoAgentScenarioSeeder(service=self.service, db=self.db)
        return await seeder.prepare_scenario(scenario_id)

    async def verify_demo_cycle(
        self,
        scenario_id: str = "demo-evolution",
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        from engine.agent.demo_scenarios import DemoAgentScenarioSeeder

        seeder = DemoAgentScenarioSeeder(service=self.service, db=self.db)
        seed_summary = await seeder.prepare_scenario(scenario_id)
        result = await self.verify_cycle(
            portfolio_id=seed_summary["portfolio_id"],
            as_of_date=seed_summary["as_of_date"],
            include_review=True,
            include_weekly=True,
            require_trade=True,
            timeout_seconds=timeout_seconds,
            brain_factory=seeder.build_brain_factory(seed_summary),
        )
        result["seed_summary"] = seed_summary
        return result
