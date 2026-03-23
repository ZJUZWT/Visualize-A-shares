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


def _render_stages(stages: list[dict[str, Any]]) -> str:
    lines = ["## Stages", "", "Name | Status | Detail", "--- | --- | ---"]
    for stage in stages:
        lines.append(
            f"{stage.get('name', '-')}"
            f" | {stage.get('status', '-')}"
            f" | {_fmt_value(stage.get('detail'))}"
        )
    return "\n".join(lines)


def _render_evolution_diff(evolution_diff: dict[str, Any]) -> str:
    lines = ["## Evolution Diff", ""]
    if not evolution_diff:
        lines.append("- None")
        return "\n".join(lines)

    for key in (
        "brain_runs_delta",
        "review_records_delta",
        "daily_reviews_delta",
        "weekly_summaries_delta",
        "weekly_reflections_delta",
        "strategy_history_count_delta",
        "strategy_history_changed",
        "memories_added",
        "memories_updated",
        "memories_retired",
        "memory_change_ids",
        "signals",
    ):
        if key in evolution_diff:
            lines.append(f"- {key}: {_fmt_value(evolution_diff.get(key))}")
    return "\n".join(lines)


def _render_seed_summary(seed_summary: dict[str, Any]) -> str:
    lines = ["## Demo Seed", ""]
    if not seed_summary:
        lines.append("- None")
        return "\n".join(lines)

    for key in (
        "scenario_id",
        "portfolio_id",
        "as_of_date",
        "week_start",
        "seed_run_id",
        "seeded_counts",
    ):
        if key in seed_summary:
            lines.append(f"- {key}: {_fmt_value(seed_summary.get(key))}")
    return "\n".join(lines)


def _render_summary(result: dict[str, Any]) -> str:
    seed_summary = result.get("seed_summary") or {}
    evolution_diff = result.get("evolution_diff") or {}
    review_result = result.get("review_result") or {}
    lines = ["## Summary", ""]

    scenario_id = seed_summary.get("scenario_id")
    if scenario_id:
        lines.append(f"- Scenario: `{scenario_id}`")
    lines.append(f"- Outcome: `{result.get('verification_status', '-')}`")
    lines.append(f"- Run: `{result.get('run_id', '-')}`")

    proof_parts: list[str] = []
    if evolution_diff.get("review_records_delta"):
        proof_parts.append(f"review_records_delta={evolution_diff['review_records_delta']}")
    if evolution_diff.get("daily_reviews_delta"):
        proof_parts.append(f"daily_reviews_delta={evolution_diff['daily_reviews_delta']}")
    if evolution_diff.get("weekly_reflections_delta"):
        proof_parts.append(f"weekly_reflections_delta={evolution_diff['weekly_reflections_delta']}")
    if evolution_diff.get("weekly_summaries_delta"):
        proof_parts.append(f"weekly_summaries_delta={evolution_diff['weekly_summaries_delta']}")
    if evolution_diff.get("memories_added"):
        proof_parts.append(f"memories_added={evolution_diff['memories_added']}")
    if evolution_diff.get("memories_updated"):
        proof_parts.append(f"memories_updated={evolution_diff['memories_updated']}")
    if evolution_diff.get("memories_retired"):
        proof_parts.append(f"memories_retired={evolution_diff['memories_retired']}")
    lines.append(f"- Evolution Proof: {', '.join(proof_parts) if proof_parts else 'none'}")

    review_parts: list[str] = []
    if review_result.get("review_type"):
        review_parts.append(f"review_type={review_result['review_type']}")
    if review_result.get("summary_id"):
        review_parts.append("weekly_summary_written")
    if review_result.get("reflection_id"):
        review_parts.append("weekly_reflection_written")
    if review_result.get("records_created") is not None:
        review_parts.append(f"records_created={review_result['records_created']}")
    lines.append(f"- Review Effect: {', '.join(review_parts) if review_parts else 'none'}")
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
    ]

    if result.get("seed_summary"):
        lines.extend(["", _render_summary(result)])

    seed_summary = result.get("seed_summary") or {}
    if seed_summary:
        lines.extend(
            [
                "",
                _render_seed_summary(seed_summary),
            ]
        )

    lines.extend(
        [
        "",
        _render_stages(result.get("stages") or []),
        "",
        _render_checks(result.get("checks") or []),
        "",
        _render_evolution_diff(result.get("evolution_diff") or {}),
        ]
    )

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
                f"- Snapshot Before: {_fmt_value((evidence.get('snapshot_before') or {}).get('portfolio_id'))}",
                f"- Snapshot After: {_fmt_value((evidence.get('snapshot_after') or {}).get('portfolio_id'))}",
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
    daily_reviews = snapshot.get("daily_reviews") or []
    weekly_reflections = snapshot.get("weekly_reflections") or []
    strategy_history = snapshot.get("strategy_history") or []
    weekly_summaries = snapshot.get("weekly_summaries") or []

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
        "## Evolution State",
        "",
        f"- Strategy History Entries: {_fmt_value(len(strategy_history))}",
        f"- Daily Review Entries: {_fmt_value(len(daily_reviews))}",
        f"- Weekly Reflection Entries: {_fmt_value(len(weekly_reflections))}",
        f"- Weekly Summaries: {_fmt_value(len(weekly_summaries))}",
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


def _render_prepare_summary(seed_summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Demo Agent Portfolio Prepared",
            "",
            _render_seed_summary(seed_summary),
        ]
    )


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


async def prepare_demo_agent_portfolio(
    scenario_id: str = "demo-evolution",
) -> str:
    seed_summary = await _get_harness().prepare_demo_portfolio(scenario_id=scenario_id)
    return _render_prepare_summary(seed_summary)


async def verify_demo_agent_cycle(
    scenario_id: str = "demo-evolution",
    timeout_seconds: int = 30,
) -> str:
    result = await _get_harness().verify_demo_cycle(
        scenario_id=scenario_id,
        timeout_seconds=timeout_seconds,
    )
    return _render_verification_result(result)
