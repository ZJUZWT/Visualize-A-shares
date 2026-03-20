"""
Main Agent FastAPI 路由
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from engine.agent.db import AgentDB
from engine.agent.models import TradeInput
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator


# ── 请求模型 ──────────────────────────────────────────

class CreatePortfolioRequest(BaseModel):
    id: str
    mode: str = "live"
    initial_capital: float
    sim_start_date: str | None = None


class CreateStrategyRequest(BaseModel):
    take_profit: float | None = None
    stop_loss: float | None = None
    reasoning: str = ""
    details: dict = {}


# ── 路由工厂 ──────────────────────────────────────────

def create_agent_router() -> APIRouter:
    router = APIRouter(tags=["agent"])

    def _get_service() -> AgentService:
        db = AgentDB.get_instance()
        return AgentService(db=db, validator=TradeValidator())

    # ── Portfolio ──

    @router.post("/portfolio")
    async def create_portfolio(req: CreatePortfolioRequest):
        svc = _get_service()
        try:
            result = await svc.create_portfolio(
                req.id, req.mode, req.initial_capital, req.sim_start_date
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.get("/portfolio")
    async def list_portfolios():
        svc = _get_service()
        return await svc.list_portfolios()

    @router.get("/portfolio/{portfolio_id}")
    async def get_portfolio(portfolio_id: str):
        svc = _get_service()
        try:
            return await svc.get_portfolio(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Positions ──

    @router.get("/portfolio/{portfolio_id}/positions")
    async def get_positions(
        portfolio_id: str,
        status: str = Query("open", pattern="^(open|closed)$"),
    ):
        svc = _get_service()
        return await svc.get_positions(portfolio_id, status)

    @router.get("/portfolio/{portfolio_id}/positions/{position_id}")
    async def get_position(portfolio_id: str, position_id: str):
        svc = _get_service()
        try:
            return await svc.get_position(portfolio_id, position_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Trades ──

    @router.get("/portfolio/{portfolio_id}/trades")
    async def get_trades(
        portfolio_id: str,
        position_id: str | None = None,
        limit: int = Query(50, ge=1, le=500),
    ):
        svc = _get_service()
        return await svc.get_trades(portfolio_id, position_id, limit)

    @router.post("/portfolio/{portfolio_id}/trades")
    async def execute_trade(
        portfolio_id: str,
        trade_input: TradeInput,
        position_id: str | None = None,
        trade_date: str | None = None,
    ):
        svc = _get_service()
        if trade_date is None:
            trade_date = date.today().isoformat()
        try:
            return await svc.execute_trade(
                portfolio_id, trade_input, trade_date, position_id
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── Strategy ──

    @router.post("/portfolio/{portfolio_id}/positions/{position_id}/strategy")
    async def create_strategy(
        portfolio_id: str, position_id: str, req: CreateStrategyRequest,
    ):
        svc = _get_service()
        try:
            return await svc.create_strategy(
                portfolio_id, position_id, req.model_dump()
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/portfolio/{portfolio_id}/positions/{position_id}/strategy")
    async def get_strategy(portfolio_id: str, position_id: str):
        svc = _get_service()
        try:
            return await svc.get_strategy(portfolio_id, position_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return router
