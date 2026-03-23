"""MCP wrappers for Main Agent verification tools."""
from __future__ import annotations

from typing import Any

from engine.agent.verification import AgentVerificationHarness

def _get_harness() -> AgentVerificationHarness:
    return AgentVerificationHarness()


def _fmt_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "-"
        return ", ".join(_fmt_value(item) for item in value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        return ", ".join(f"{key}={_fmt_value(val)}" for key, val in value.items())
    return str(value)


def _render_checks(checks: list[dict[str, Any]]) -> str:
    lines = ["## Checks", "", "Name | Status | Detail", "--- | --- | ---"]
    for check in checks:
        lines.append(
            f"{check.get('name', '-')}"
            f" | {check.get('status', '-')}"
            f" | {_fmt_value(check.get('detail'))}"
        )
    return "\n".join(lines)


def _render_verification_result(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Cycle Verification",
        "",
        f"- Status: **{result.get('verification_status', '-')}**",
        f"- Portfolio: `{result.get('portfolio_id', '-')}`",
        f"- Run ID: `{result.get('run_id', '-')}`",
        f"- Brain Run Status: `{result.get('brain_run_status', '-')}`",
        f"- Failed Stage: `{result.get('failed_stage') or '-'}`",
        "",
        _render_checks(result.get("checks") or []),
    ]

    evidence = result.get("evidence") or {}
    if evidence:
        lines.extend(
            [
                "",
                "## Evidence",
                "",
                f"- Brain Run: {_fmt_value((evidence.get('brain_run') or {}).get('status'))}",
                f"- Execution Summary: {_fmt_value((evidence.get('brain_run') or {}).get('execution_summary'))}",
                f"- Review: {_fmt_value(evidence.get('review'))}",
            ]
        )

    next_actions = result.get("next_actions") or []
    lines.extend(["", "## Next Actions", ""])
    if next_actions:
        for action in next_actions:
            lines.append(f"- {action}")
    else:
        lines.append("- None")
    return "\n".join(lines)


def _render_snapshot(snapshot: dict[str, Any]) -> str:
    latest_run = snapshot.get("latest_run") or {}
    asset_summary = (snapshot.get("ledger") or {}).get("asset_summary") or {}
    review_stats = snapshot.get("review_stats") or {}
    memories = snapshot.get("memories") or []

    lines = [
        "# Agent Snapshot",
        "",
        f"- Portfolio: `{snapshot.get('portfolio_id', '-')}`",
        "",
        "## State",
        "",
        f"- Market View: {_fmt_value((snapshot.get('state') or {}).get('market_view'))}",
        f"- Position Level: {_fmt_value((snapshot.get('state') or {}).get('position_level'))}",
        "",
        "## Latest Run",
        "",
        f"- Run ID: `{latest_run.get('id', '-')}`",
        f"- Status: `{latest_run.get('status', '-')}`",
        f"- Execution Summary: {_fmt_value(latest_run.get('execution_summary'))}",
        "",
        "## Ledger",
        "",
        f"- Open Positions: {_fmt_value(asset_summary.get('open_position_count'))}",
        f"- Recent Trades: {_fmt_value(asset_summary.get('recent_trade_count'))}",
        f"- Pending Plans: {_fmt_value(asset_summary.get('pending_plan_count'))}",
        f"- Executing Plans: {_fmt_value(asset_summary.get('executing_plan_count'))}",
        "",
        "## Review Stats",
        "",
        f"- Total Reviews: {_fmt_value(review_stats.get('total_reviews'))}",
        f"- Win Rate: {_fmt_value(review_stats.get('win_rate'))}",
        "",
        "## Memories",
        "",
    ]
    if memories:
        for memory in memories[:5]:
            lines.append(
                f"- {memory.get('rule_text', '-')}"
                f" (confidence={_fmt_value(memory.get('confidence'))})"
            )
    else:
        lines.append("- None")
    return "\n".join(lines)


async def verify_agent_cycle(
    portfolio_id: str,
    as_of_date: str | None = None,
    include_review: bool = True,
    include_weekly: bool = False,
    require_trade: bool = False,
    timeout_seconds: int = 30,
) -> str:
    result = await _get_harness().verify_cycle(
        portfolio_id=portfolio_id,
        as_of_date=as_of_date,
        include_review=include_review,
        include_weekly=include_weekly,
        require_trade=require_trade,
        timeout_seconds=timeout_seconds,
    )
    return _render_verification_result(result)


async def inspect_agent_snapshot(
    portfolio_id: str,
    run_id: str | None = None,
) -> str:
    snapshot = await _get_harness().inspect_snapshot(
        portfolio_id=portfolio_id,
        run_id=run_id,
    )
    return _render_snapshot(snapshot)
