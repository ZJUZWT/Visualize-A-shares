"""Agent 复盘引擎骨架"""
from __future__ import annotations

from engine.agent.db import AgentDB
from engine.agent.memory import MemoryManager


class ReviewEngine:
    """日复盘 / 周复盘最小可用骨架。"""

    def __init__(self, db: AgentDB, memory_mgr: MemoryManager):
        self.db = db
        self.memory_mgr = memory_mgr

    async def daily_review(self) -> dict:
        return {
            "status": "pending",
            "review_type": "daily",
            "records_created": 0,
        }

    async def weekly_review(self) -> dict:
        return {
            "status": "pending",
            "review_type": "weekly",
            "new_rules": [],
        }
