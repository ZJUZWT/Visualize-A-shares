"""Deterministic demo scenarios for agent verification."""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from engine.agent.db import AgentDB
from engine.agent.models import TradeInput, TradePlanInput
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator


_DEFAULT_SCENARIO_ID = "demo-evolution"


class DemoAgentScenarioSeeder:
    """Seed a deterministic backend-only scenario for verification."""

    def __init__(
        self,
        service: AgentService | None = None,
        db: AgentDB | None = None,
    ):
        self.db = db or AgentDB.get_instance()
        self.service = service or AgentService(db=self.db, validator=TradeValidator())

    async def prepare_scenario(self, scenario_id: str = _DEFAULT_SCENARIO_ID) -> dict[str, Any]:
        scenario = self._build_scenario(scenario_id)
        await self._cleanup_scenario(scenario)
        await self._seed_portfolio(scenario)
        await self._seed_state(scenario)
        await self._seed_watchlist(scenario)
        await self._seed_memories(scenario)
        await self._seed_review_baseline(scenario)
        return {
            "scenario_id": scenario["scenario_id"],
            "portfolio_id": scenario["portfolio_id"],
            "as_of_date": scenario["as_of_date"],
            "week_start": scenario["week_start"],
            "seed_run_id": scenario["seed_run_id"],
            "seeded_counts": {
                "watchlist_items": 2,
                "baseline_review_records": 2,
                "baseline_memories": 1,
            },
            "run_started_at": scenario["run_started_at"],
            "run_completed_at": scenario["run_completed_at"],
        }

    def build_brain_factory(self, seed_summary: dict[str, Any]):
        service = self.service
        db = self.db
        scenario = dict(seed_summary)

        class DemoAgentBrain:
            def __init__(self, portfolio_id: str):
                self.portfolio_id = portfolio_id

            async def execute(self, run_id: str):
                state_before = await service.get_agent_state(self.portfolio_id)
                plan = await service.create_plan(
                    TradePlanInput(
                        stock_code="600519",
                        stock_name="贵州茅台",
                        current_price=1800.0,
                        direction="buy",
                        entry_price="1800.0",
                        position_pct=0.18,
                        take_profit="1888.0",
                        stop_loss=1740.0,
                        reasoning="demo verification plan",
                        risk_note="demo scenario risk",
                        invalidation="scenario invalidation",
                        source_type="agent",
                    ),
                    source_run_id=run_id,
                )
                trade = await service.execute_trade(
                    self.portfolio_id,
                    TradeInput(
                        action="buy",
                        stock_code="600519",
                        price=1800.0,
                        quantity=100,
                        holding_type="mid_term",
                        reason="demo scenario entry",
                        thesis="deterministic verification trade",
                        data_basis=["demo-scenario"],
                        risk_note="demo scenario risk",
                        invalidation="scenario invalidation",
                        triggered_by="agent",
                    ),
                    trade_date=scenario["as_of_date"],
                    source_run_id=run_id,
                    source_plan_id=plan["id"],
                )
                await service.update_plan(plan["id"], {"status": "executing"})
                position = trade["position"] or {}
                trade_row = trade["trade"] or {}
                if position.get("id"):
                    await service.create_strategy(
                        self.portfolio_id,
                        position["id"],
                        {
                            "take_profit": 1888.0,
                            "stop_loss": 1740.0,
                            "reasoning": "demo strategy anchor",
                            "details": {
                                "trend_indicator": "weekly pullback",
                                "add_position_price": 1760.0,
                                "half_exit_price": 1860.0,
                                "target_catalyst": "demo verification",
                            },
                        },
                        source_run_id=run_id,
                    )

                await service.update_agent_state(
                    self.portfolio_id,
                    {
                        "market_view": {"stance": "selective-risk-on"},
                        "position_level": 0.35,
                        "sector_preferences": ["consumer", "finance"],
                        "risk_alerts": ["demo-cycle-open-position"],
                    },
                    source_run_id=run_id,
                )
                state_after = await service.get_agent_state(self.portfolio_id)

                await service.update_brain_run(
                    run_id,
                    {
                        "status": "completed",
                        "candidates": [
                            {"stock_code": "600519", "stock_name": "贵州茅台", "source": "watchlist"}
                        ],
                        "analysis_results": [
                            {
                                "stock_code": "600519",
                                "summary": "demo scenario analysis",
                                "confidence": 0.82,
                            }
                        ],
                        "decisions": [
                            {
                                "stock_code": "600519",
                                "action": "buy",
                                "position_pct": 0.18,
                                "reason": "demo verification entry",
                            }
                        ],
                        "plan_ids": [plan["id"]],
                        "trade_ids": [trade_row.get("id")] if trade_row.get("id") else [],
                        "state_before": state_before,
                        "state_after": state_after,
                        "execution_summary": {
                            "candidate_count": 1,
                            "analysis_count": 1,
                            "decision_count": 1,
                            "plan_count": 1,
                            "trade_count": 1 if trade_row.get("id") else 0,
                            "elapsed_seconds": 0.01,
                        },
                    },
                )
                await db.execute_write(
                    """
                    UPDATE agent.brain_runs
                    SET started_at = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    [scenario["run_started_at"], scenario["run_completed_at"], run_id],
                )

        return DemoAgentBrain

    def _build_scenario(self, scenario_id: str) -> dict[str, Any]:
        if scenario_id != _DEFAULT_SCENARIO_ID:
            raise ValueError(f"未知 demo scenario: {scenario_id}")

        as_of_day = date.fromisoformat("2042-01-10")
        week_start = as_of_day - timedelta(days=as_of_day.weekday())
        return {
            "scenario_id": scenario_id,
            "portfolio_id": scenario_id,
            "seed_run_id": f"demo-seed:{scenario_id}",
            "weekly_source_run_id": f"weekly:{week_start.isoformat()}",
            "as_of_date": as_of_day.isoformat(),
            "week_start": week_start.isoformat(),
            "review_dates": [
                week_start.isoformat(),
                (week_start + timedelta(days=2)).isoformat(),
            ],
            "run_started_at": f"{as_of_day.isoformat()}T09:35:00",
            "run_completed_at": f"{as_of_day.isoformat()}T09:36:00",
        }

    async def _cleanup_scenario(self, scenario: dict[str, Any]) -> None:
        portfolio_id = scenario["portfolio_id"]
        run_rows = await self.db.execute_read(
            "SELECT id FROM agent.brain_runs WHERE portfolio_id = ?",
            [portfolio_id],
        )
        run_ids = [row["id"] for row in run_rows]
        position_rows = await self.db.execute_read(
            "SELECT id FROM agent.positions WHERE portfolio_id = ?",
            [portfolio_id],
        )
        position_ids = [row["id"] for row in position_rows]

        if run_ids:
            await self._delete_many("agent.review_records", "brain_run_id", run_ids)
            await self._delete_many("agent.trade_plans", "source_run_id", run_ids)

        await self.db.execute_write("DELETE FROM agent.info_digests WHERE portfolio_id = ?", [portfolio_id])
        await self.db.execute_write("DELETE FROM agent.watch_signals WHERE portfolio_id = ?", [portfolio_id])
        await self.db.execute_write("DELETE FROM agent.strategy_memos WHERE portfolio_id = ?", [portfolio_id])
        await self.db.execute_write("DELETE FROM agent.trades WHERE portfolio_id = ?", [portfolio_id])
        if position_ids:
            await self._delete_many("agent.position_strategies", "position_id", position_ids)
        await self.db.execute_write("DELETE FROM agent.positions WHERE portfolio_id = ?", [portfolio_id])
        await self.db.execute_write("DELETE FROM agent.brain_runs WHERE portfolio_id = ?", [portfolio_id])
        await self.db.execute_write("DELETE FROM agent.agent_state WHERE portfolio_id = ?", [portfolio_id])
        await self.db.execute_write("DELETE FROM agent.portfolio_config WHERE id = ?", [portfolio_id])

        await self.db.execute_write("DELETE FROM agent.watchlist WHERE added_by = 'demo-seed'")
        await self.db.execute_write(
            "DELETE FROM agent.agent_memories WHERE source_run_id IN (?, ?)",
            [scenario["seed_run_id"], scenario["weekly_source_run_id"]],
        )
        await self.db.execute_write(
            "DELETE FROM agent.daily_reviews WHERE review_date = ?",
            [scenario["as_of_date"]],
        )
        await self.db.execute_write(
            "DELETE FROM agent.weekly_summaries WHERE week_start = ?",
            [scenario["week_start"]],
        )
        await self.db.execute_write(
            "DELETE FROM agent.weekly_reflections WHERE week_start = ?",
            [scenario["week_start"]],
        )

    async def _seed_portfolio(self, scenario: dict[str, Any]) -> None:
        await self.service.create_portfolio(
            scenario["portfolio_id"],
            "training",
            1_000_000.0,
            scenario["week_start"],
        )
        await self.db.execute_write(
            """
            UPDATE agent.portfolio_config
            SET sim_current_date = ?
            WHERE id = ?
            """,
            [scenario["as_of_date"], scenario["portfolio_id"]],
        )

    async def _seed_state(self, scenario: dict[str, Any]) -> None:
        await self.service.update_agent_state(
            scenario["portfolio_id"],
            {
                "market_view": {"stance": "risk-off", "summary": "demo baseline"},
                "position_level": 0.15,
                "sector_preferences": ["consumer", "bank"],
                "risk_alerts": ["awaiting-demo-cycle"],
            },
            source_run_id=scenario["seed_run_id"],
        )

    async def _seed_watchlist(self, scenario: dict[str, Any]) -> None:
        rows = [
            [
                f"{scenario['scenario_id']}-watch-1",
                "600519",
                "贵州茅台",
                "demo baseline watch",
                "demo-seed",
                scenario["portfolio_id"],
                scenario["run_started_at"],
            ],
            [
                f"{scenario['scenario_id']}-watch-2",
                "601318",
                "中国平安",
                "demo baseline watch",
                "demo-seed",
                scenario["portfolio_id"],
                scenario["run_started_at"],
            ],
        ]
        for row in rows:
            await self.db.execute_write(
                """
                INSERT INTO agent.watchlist (id, stock_code, stock_name, reason, added_by, portfolio_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

    async def _seed_memories(self, scenario: dict[str, Any]) -> None:
        await self.db.execute_write(
            """
            INSERT INTO agent.agent_memories (
                id, rule_text, category, source_run_id, status, confidence,
                verify_count, verify_win, created_at, retired_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            [
                f"{scenario['scenario_id']}-memory-risk",
                "低置信度旧规则",
                "risk",
                scenario["seed_run_id"],
                "active",
                0.25,
                4,
                1,
                scenario["run_started_at"],
            ],
        )

    async def _seed_review_baseline(self, scenario: dict[str, Any]) -> None:
        historical_runs = [
            (
                f"{scenario['scenario_id']}-hist-run-1",
                scenario["review_dates"][0],
                "600519",
                "贵州茅台",
                "demo-loss-trade-1",
            ),
            (
                f"{scenario['scenario_id']}-hist-run-2",
                scenario["review_dates"][1],
                "601318",
                "中国平安",
                "demo-loss-trade-2",
            ),
        ]
        for run_id, review_date, stock_code, stock_name, trade_id in historical_runs:
            started_at = f"{review_date}T09:30:00"
            completed_at = f"{review_date}T09:31:00"
            await self.db.execute_write(
                """
                INSERT INTO agent.brain_runs (
                    id, portfolio_id, run_type, status, candidates, analysis_results,
                    decisions, plan_ids, trade_ids, started_at, completed_at,
                    state_before, state_after, execution_summary
                ) VALUES (?, ?, 'seed', 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    scenario["portfolio_id"],
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    started_at,
                    completed_at,
                    json.dumps({"position_level": 0.1}, ensure_ascii=False),
                    json.dumps({"position_level": 0.1}, ensure_ascii=False),
                    json.dumps({"trade_count": 0}, ensure_ascii=False),
                ],
            )
            await self.db.execute_write(
                """
                INSERT INTO agent.review_records (
                    id, brain_run_id, trade_id, stock_code, stock_name, action,
                    decision_price, review_price, pnl_pct, holding_days,
                    status, review_date, review_type, created_at
                ) VALUES (?, ?, ?, ?, ?, 'buy', ?, ?, ?, ?, 'loss', ?, 'daily', ?)
                """,
                [
                    f"{scenario['scenario_id']}-review-{trade_id}",
                    run_id,
                    trade_id,
                    stock_code,
                    stock_name,
                    100.0,
                    97.0,
                    -0.03,
                    2,
                    review_date,
                    started_at,
                ],
            )

    async def _delete_many(self, table: str, column: str, values: list[str]) -> None:
        if not values:
            return
        placeholders = ", ".join("?" for _ in values)
        await self.db.execute_write(
            f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
            values,
        )
