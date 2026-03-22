"""Mounted strategy action routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from engine.agent.db import AgentDB
from engine.agent.memory import MemoryManager
from engine.agent.models import AdoptStrategyRequest, RejectStrategyRequest
from engine.agent.service import AgentService
from engine.agent.strategy_actions import StrategyActionService
from engine.agent.validator import TradeValidator


def create_strategy_action_router() -> APIRouter:
    router = APIRouter(tags=["agent-strategy-actions"])

    def _get_service() -> StrategyActionService:
        db = AgentDB.get_instance()
        return StrategyActionService(
            db=db,
            agent_service=AgentService(db=db, validator=TradeValidator()),
            memory_mgr=MemoryManager(db),
        )

    @router.post("/adopt-strategy")
    async def adopt_strategy(req: AdoptStrategyRequest):
        svc = _get_service()
        try:
            return await svc.adopt_strategy(req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/reject-strategy")
    async def reject_strategy(req: RejectStrategyRequest):
        svc = _get_service()
        try:
            return await svc.reject_strategy(req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/strategy-actions")
    async def list_strategy_actions(session_id: str = Query(..., min_length=1)):
        svc = _get_service()
        return await svc.list_actions(session_id)

    return router
