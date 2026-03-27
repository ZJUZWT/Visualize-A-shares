"""Unified MCP verification suite for demo cycle plus short backtest."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pandas as pd

from .agent_http import post_agent_json
from .agent_backtest import _get_engine as _resolve_backtest_engine
from .agent_verification import _build_demo_cycle_summary
from .agent_verification import _get_harness as _resolve_verification_harness

_SMOKE_START_DATE = "2026-03-18"
_SMOKE_END_DATE = "2026-03-20"
_SMOKE_HISTORY = {
    "600519": [
        {"date": "2026-03-18", "open": 100.0, "close": 101.0},
        {"date": "2026-03-19", "open": 102.0, "close": 103.0},
        {"date": "2026-03-20", "open": 104.0, "close": 105.0},
    ],
    "601318": [
        {"date": "2026-03-18", "open": 50.0, "close": 50.5},
        {"date": "2026-03-19", "open": 51.0, "close": 51.5},
        {"date": "2026-03-20", "open": 52.0, "close": 52.5},
    ],
}


class _SmokeDataEngine:
    def __init__(self, history_by_code: dict[str, list[dict[str, Any]]]):
        self._history_by_code = history_by_code

    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        rows = []
        for row in self._history_by_code.get(code, []):
            if start <= row["date"] <= end:
                rows.append(row)
        return pd.DataFrame(rows)

    def get_snapshot(self) -> pd.DataFrame:
        return pd.DataFrame()


class _SmokeAgentBrain:
    def __init__(self, portfolio_id: str):
        self.portfolio_id = portfolio_id

    async def execute(self, run_id: str):
        from engine.agent.db import AgentDB
        from engine.agent.service import AgentService
        from engine.agent.validator import TradeValidator

        service = AgentService(db=AgentDB.get_instance(), validator=TradeValidator())
        portfolio = await service.get_portfolio(self.portfolio_id)
        trade_day = portfolio["config"]["sim_current_date"]
        decisions = []
        if trade_day == _SMOKE_START_DATE:
            decisions.append(
                {
                    "action": "buy",
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "quantity": 100,
                    "holding_type": "mid_term",
                    "reasoning": "suite smoke entry",
                    "risk_note": "suite smoke risk",
                    "invalidation": "suite smoke invalidation",
                }
            )
        await service.update_brain_run(
            run_id,
            {
                "status": "completed",
                "decisions": decisions,
            },
        )


@contextmanager
def _with_smoke_backtest_env():
    import engine.agent.backtest as backtest_module
    import engine.data as data_module

    smoke_engine = _SmokeDataEngine(_SMOKE_HISTORY)
    original_brain = backtest_module.AgentBrain
    original_backtest_factory = backtest_module.get_data_engine
    original_data_factory = data_module.get_data_engine

    backtest_module.AgentBrain = _SmokeAgentBrain
    backtest_module.get_data_engine = lambda: smoke_engine
    data_module.get_data_engine = lambda: smoke_engine
    try:
        yield
    finally:
        backtest_module.AgentBrain = original_brain
        backtest_module.get_data_engine = original_backtest_factory
        data_module.get_data_engine = original_data_factory


def _get_harness():
    return _resolve_verification_harness()


def _get_engine():
    return _resolve_backtest_engine()


async def _post_json(
    path: str,
    payload: dict[str, Any],
    timeout: float = 120.0,
) -> dict[str, Any]:
    return await post_agent_json(path, payload=payload, timeout=timeout)


def _resolve_backtest_window(
    seed_summary: dict[str, Any],
    *,
    backtest_start_date: str | None,
    backtest_end_date: str | None,
    smoke_mode: bool,
) -> tuple[str | None, str | None]:
    if smoke_mode and not backtest_start_date and not backtest_end_date:
        return (_SMOKE_START_DATE, _SMOKE_END_DATE)
    return (
        backtest_start_date or seed_summary.get("week_start"),
        backtest_end_date or seed_summary.get("as_of_date"),
    )


def _build_result(
    *,
    mode: str,
    overall_status: str,
    scenario_id: str,
    portfolio_id: str | None,
    seed_summary: dict[str, Any],
    demo_verification: dict[str, Any],
    backtest: dict[str, Any],
    evidence: dict[str, Any],
    next_actions: list[str],
) -> str:
    return json.dumps(
        {
            "mode": mode,
            "overall_status": overall_status,
            "scenario_id": scenario_id,
            "portfolio_id": portfolio_id,
            "seed_summary": seed_summary,
            "demo_verification": demo_verification,
            "backtest": backtest,
            "evidence": evidence,
            "next_actions": next_actions,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _warn_on_backtest_summary(summary: dict[str, Any], next_actions: list[str]) -> bool:
    warn = False
    if int(summary.get("trade_count") or 0) == 0:
        next_actions.append("backtest weak signal: trade_count=0")
        warn = True
    if int(summary.get("review_count") or 0) == 0:
        next_actions.append("backtest weak signal: review_count=0")
        warn = True

    memory_added = int(summary.get("memory_added") or 0)
    memory_updated = int(summary.get("memory_updated") or 0)
    memory_retired = int(summary.get("memory_retired") or 0)
    if memory_added == 0 and memory_updated == 0 and memory_retired == 0:
        next_actions.append("backtest weak signal: no memory movement")
        warn = True
    return warn


async def _run_demo_agent_verification_suite_local(
    scenario_id: str = "demo-evolution",
    backtest_start_date: str | None = None,
    backtest_end_date: str | None = None,
    timeout_seconds: int = 30,
    execution_price_mode: str = "next_open",
    smoke_mode: bool = False,
) -> str:
    mode = "smoke" if smoke_mode else "default"
    harness = _get_harness()
    verification_result = await harness.verify_demo_cycle(
        scenario_id=scenario_id,
        timeout_seconds=timeout_seconds,
    )
    seed_summary = verification_result.get("seed_summary") or {}
    demo_verification = _build_demo_cycle_summary(verification_result)
    portfolio_id = seed_summary.get("portfolio_id") or verification_result.get("portfolio_id")
    start_date, end_date = _resolve_backtest_window(
        seed_summary,
        backtest_start_date=backtest_start_date,
        backtest_end_date=backtest_end_date,
        smoke_mode=smoke_mode,
    )
    evidence = {
        "verification_run_id": verification_result.get("run_id"),
        "backtest_run_id": None,
        "backtest_start_date": start_date,
        "backtest_end_date": end_date,
    }
    next_actions: list[str] = []

    verification_status = verification_result.get("verification_status")
    if verification_status == "fail":
        next_actions.append(
            f"demo verification failed at {verification_result.get('failed_stage') or 'unknown_stage'}"
        )
        return _build_result(
            mode=mode,
            overall_status="fail",
            scenario_id=seed_summary.get("scenario_id") or scenario_id,
            portfolio_id=portfolio_id,
            seed_summary=seed_summary,
            demo_verification=demo_verification,
            backtest={
                "status": "skipped",
                "reason": "demo_verification_failed",
                "start_date": start_date,
                "end_date": end_date,
                "execution_price_mode": execution_price_mode,
            },
            evidence=evidence,
            next_actions=next_actions,
        )

    if not portfolio_id or not start_date or not end_date:
        next_actions.append("suite failed: missing portfolio_id or backtest window")
        return _build_result(
            mode=mode,
            overall_status="fail",
            scenario_id=seed_summary.get("scenario_id") or scenario_id,
            portfolio_id=portfolio_id,
            seed_summary=seed_summary,
            demo_verification=demo_verification,
            backtest={
                "status": "skipped",
                "reason": "missing_backtest_inputs",
                "start_date": start_date,
                "end_date": end_date,
                "execution_price_mode": execution_price_mode,
            },
            evidence=evidence,
            next_actions=next_actions,
        )

    engine = _get_engine()
    try:
        if smoke_mode:
            with _with_smoke_backtest_env():
                backtest_run = await engine.run_backtest(
                    portfolio_id=portfolio_id,
                    start_date=start_date,
                    end_date=end_date,
                    execution_price_mode=execution_price_mode,
                )
                backtest_summary = await engine.get_run_summary(backtest_run["id"])
        else:
            backtest_run = await engine.run_backtest(
                portfolio_id=portfolio_id,
                start_date=start_date,
                end_date=end_date,
                execution_price_mode=execution_price_mode,
            )
            backtest_summary = await engine.get_run_summary(backtest_run["id"])
    except Exception as exc:
        next_actions.append("backtest execution failed")
        return _build_result(
            mode=mode,
            overall_status="fail",
            scenario_id=seed_summary.get("scenario_id") or scenario_id,
            portfolio_id=portfolio_id,
            seed_summary=seed_summary,
            demo_verification=demo_verification,
            backtest={
                "status": "fail",
                "error": str(exc),
                "start_date": start_date,
                "end_date": end_date,
                "execution_price_mode": execution_price_mode,
            },
            evidence=evidence,
            next_actions=next_actions,
        )

    evidence["backtest_run_id"] = backtest_run.get("id")
    backtest = {
        "status": backtest_run.get("status") or backtest_summary.get("status"),
        "run_id": backtest_run.get("id"),
        "start_date": start_date,
        "end_date": end_date,
        "execution_price_mode": execution_price_mode,
        "summary": backtest_summary,
    }

    overall_status = "pass"
    if verification_status == "warn":
        overall_status = "warn"
        next_actions.append("demo verification returned warn")
    if _warn_on_backtest_summary(backtest_summary, next_actions):
        overall_status = "warn"

    return _build_result(
        mode=mode,
        overall_status=overall_status,
        scenario_id=seed_summary.get("scenario_id") or scenario_id,
        portfolio_id=portfolio_id,
        seed_summary=seed_summary,
        demo_verification=demo_verification,
        backtest=backtest,
        evidence=evidence,
        next_actions=next_actions,
    )


async def run_demo_agent_verification_suite(
    scenario_id: str = "demo-evolution",
    backtest_start_date: str | None = None,
    backtest_end_date: str | None = None,
    timeout_seconds: int = 30,
    execution_price_mode: str = "next_open",
    smoke_mode: bool = False,
) -> str:
    result = await _post_json(
        "/api/v1/agent/verification-suite/run",
        {
            "scenario_id": scenario_id,
            "backtest_start_date": backtest_start_date,
            "backtest_end_date": backtest_end_date,
            "timeout_seconds": timeout_seconds,
            "execution_price_mode": execution_price_mode,
            "smoke_mode": smoke_mode,
        },
        timeout=max(float(timeout_seconds), 120.0),
    )
    return json.dumps(result, ensure_ascii=False, sort_keys=True)
