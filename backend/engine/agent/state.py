"""
AgentState 读写边界
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from engine.agent.db import AgentDB


JSON_STATE_FIELDS = ("market_view", "sector_preferences", "risk_alerts")
STATE_UPDATE_FIELDS = (
    "market_view",
    "position_level",
    "sector_preferences",
    "risk_alerts",
)


def _encode_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _decode_json(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _normalize_state_row(row: dict) -> dict:
    normalized = dict(row)
    for field in JSON_STATE_FIELDS:
        normalized[field] = _decode_json(normalized.get(field))
    return normalized


async def _ensure_portfolio_exists(db: AgentDB, portfolio_id: str):
    rows = await db.execute_read(
        "SELECT id FROM agent.portfolio_config WHERE id = ?",
        [portfolio_id],
    )
    if not rows:
        raise ValueError(f"账户 {portfolio_id} 不存在")


async def get_state(db: AgentDB, portfolio_id: str) -> dict:
    await _ensure_portfolio_exists(db, portfolio_id)
    rows = await db.execute_read(
        "SELECT * FROM agent.agent_state WHERE portfolio_id = ?",
        [portfolio_id],
    )
    if not rows:
        now = datetime.now().isoformat()
        await db.execute_write(
            """INSERT INTO agent.agent_state
               (portfolio_id, created_at, updated_at)
               VALUES (?, ?, ?)""",
            [portfolio_id, now, now],
        )
        rows = await db.execute_read(
            "SELECT * FROM agent.agent_state WHERE portfolio_id = ?",
            [portfolio_id],
        )
    return _normalize_state_row(rows[0])


async def upsert_state(
    db: AgentDB,
    portfolio_id: str,
    updates: dict,
    source_run_id: str | None = None,
) -> dict:
    await get_state(db, portfolio_id)

    sets = []
    params = []
    for field in STATE_UPDATE_FIELDS:
        if field not in updates:
            continue
        value = updates[field]
        if field in JSON_STATE_FIELDS:
            value = _encode_json(value)
        sets.append(f"{field} = ?")
        params.append(value)

    if source_run_id is None and "source_run_id" in updates:
        source_run_id = updates["source_run_id"]
    if source_run_id is not None:
        sets.append("source_run_id = ?")
        params.append(source_run_id)

    sets.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(portfolio_id)

    await db.execute_write(
        f"UPDATE agent.agent_state SET {', '.join(sets)} WHERE portfolio_id = ?",
        params,
    )
    return await get_state(db, portfolio_id)


def build_state_snapshot(
    portfolio_id: str,
    market_view: dict[str, Any] | None = None,
    position_level: str | None = None,
    sector_preferences: list[Any] | None = None,
    risk_alerts: list[Any] | None = None,
    source_run_id: str | None = None,
) -> dict:
    return {
        "portfolio_id": portfolio_id,
        "market_view": market_view,
        "position_level": position_level,
        "sector_preferences": sector_preferences,
        "risk_alerts": risk_alerts,
        "source_run_id": source_run_id,
    }
