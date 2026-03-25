"""MCP wrappers for Agent backtest tools."""
from __future__ import annotations

import json
from typing import Any

from engine.agent.backtest import AgentBacktestEngine
from engine.agent.db import AgentDB


def _get_engine() -> AgentBacktestEngine:
    try:
        AgentDB.get_instance()
    except RuntimeError as exc:
        if "not initialized" not in str(exc):
            raise
        AgentDB.init_instance()
    return AgentBacktestEngine()


def _fmt_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


async def _load_day_details(engine: AgentBacktestEngine, day_row: dict[str, Any]) -> dict[str, Any]:
    brain_run_id = day_row.get("brain_run_id")
    trade_rows: list[dict[str, Any]] = []
    if brain_run_id:
        trade_rows = await engine.db.execute_read(
            """
            SELECT id, stock_code, stock_name, action, quantity, price
            FROM agent.trades
            WHERE source_run_id = ?
            ORDER BY created_at, id
            """,
            [brain_run_id],
        )
    return {
        "brain_run_id": brain_run_id,
        "trades": trade_rows,
    }


async def run_agent_backtest(
    portfolio_id: str,
    start_date: str,
    end_date: str,
    execution_price_mode: str = "next_open",
) -> str:
    engine = _get_engine()
    result = await engine.run_backtest(
        portfolio_id=portfolio_id,
        start_date=start_date,
        end_date=end_date,
        execution_price_mode=execution_price_mode,
    )
    summary = await engine.get_run_summary(result["id"])
    lines = [
        "# Agent Backtest",
        "",
        f"- run_id: `{result['id']}`",
        f"- status: `{result['status']}`",
        f"- trade_count: {_fmt_value(summary.get('trade_count'))}",
        f"- review_count: {_fmt_value(summary.get('review_count'))}",
        f"- total_return: {_fmt_value(summary.get('total_return'))}",
        f"- max_drawdown: {_fmt_value(summary.get('max_drawdown'))}",
        f"- buy_and_hold_return: {_fmt_value(summary.get('buy_and_hold_return'))}",
        f"- memory_added: {_fmt_value(summary.get('memory_added'))}",
        f"- memory_updated: {_fmt_value(summary.get('memory_updated'))}",
        f"- memory_retired: {_fmt_value(summary.get('memory_retired'))}",
    ]
    return "\n".join(lines)


async def get_agent_backtest_summary(run_id: str) -> str:
    engine = _get_engine()
    summary = await engine.get_run_summary(run_id)
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)


async def get_agent_backtest_day(run_id: str, date: str) -> str:
    engine = _get_engine()
    days = await engine.list_run_days(run_id)
    target = next((row for row in days if str(row.get("trade_date"))[:10] == date), None)
    if target is None:
        raise ValueError(f"回测 {run_id} 在 {date} 无记录")
    details = await _load_day_details(engine, target)
    lines = [
        "# Agent Backtest Day",
        "",
        f"- run_id: `{run_id}`",
        f"- trade_date: `{date}`",
        f"- brain_run_id: `{details.get('brain_run_id') or '-'}`",
        f"- review_created: {_fmt_value(target.get('review_created'))}",
        f"- memory_delta: {_fmt_value(target.get('memory_delta') or {})}",
        f"- trades: {_fmt_value(details.get('trades') or [])}",
    ]
    return "\n".join(lines)
