"""Agent 经验规则管理"""
from __future__ import annotations

import uuid
from datetime import datetime

from engine.agent.db import AgentDB


class MemoryManager:
    """管理 agent_memories 规则库的最小实现。"""

    def __init__(self, db: AgentDB):
        self.db = db

    async def get_active_rules(self, limit: int = 20) -> list[dict]:
        return await self.db.execute_read(
            """
            SELECT *
            FROM agent.agent_memories
            WHERE status = 'active'
            ORDER BY confidence DESC, created_at DESC
            LIMIT ?
            """,
            [limit],
        )

    async def list_rules(self, status: str | None = None) -> list[dict]:
        if status:
            return await self.db.execute_read(
                """
                SELECT *
                FROM agent.agent_memories
                WHERE status = ?
                ORDER BY created_at DESC
                """,
                [status],
            )
        return await self.db.execute_read(
            """
            SELECT *
            FROM agent.agent_memories
            ORDER BY created_at DESC
            """
        )

    async def add_rules(self, rules: list[dict], source_run_id: str) -> list[str]:
        created_ids: list[str] = []
        for rule in rules:
            rule_id = str(uuid.uuid4())
            created_ids.append(rule_id)
            await self.db.execute_write(
                """
                INSERT INTO agent.agent_memories (
                    id, rule_text, category, source_run_id, status, confidence, verify_count, verify_win
                )
                VALUES (?, ?, ?, ?, 'active', 0.5, 0, 0)
                """,
                [rule_id, rule["rule_text"], rule["category"], source_run_id],
            )
        return created_ids

    async def update_verification(self, rule_id: str, validated: bool):
        rows = await self.db.execute_read(
            """
            SELECT verify_count, verify_win
            FROM agent.agent_memories
            WHERE id = ?
            """,
            [rule_id],
        )
        if not rows:
            raise ValueError(f"规则 {rule_id} 不存在")

        current = rows[0]
        verify_count = int(current["verify_count"] or 0) + 1
        verify_win = int(current["verify_win"] or 0) + (1 if validated else 0)
        confidence = verify_win / verify_count if verify_count else 0.5

        status = "active"
        retired_at = None
        if verify_count >= 5 and confidence < 0.3:
            status = "retired"
            retired_at = datetime.now().isoformat()

        await self.db.execute_write(
            """
            UPDATE agent.agent_memories
            SET verify_count = ?, verify_win = ?, confidence = ?, status = ?, retired_at = ?
            WHERE id = ?
            """,
            [verify_count, verify_win, confidence, status, retired_at, rule_id],
        )

    async def retire_rules(self, rule_ids: list[str]):
        if not rule_ids:
            return

        retired_at = datetime.now().isoformat()
        for rule_id in rule_ids:
            await self.db.execute_write(
                """
                UPDATE agent.agent_memories
                SET status = 'retired', retired_at = ?
                WHERE id = ?
                """,
                [retired_at, rule_id],
            )
