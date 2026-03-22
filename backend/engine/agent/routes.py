"""
Main Agent FastAPI 路由
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from engine.agent.chat_routes import create_agent_chat_router
from engine.agent.db import AgentDB
from engine.agent.models import (
    TradeInput,
    TradePlanInput,
    TradePlanUpdate,
    WatchSignalInput,
    WatchlistInput,
)
from engine.agent.service import AgentService
from engine.agent.strategy_action_routes import create_strategy_action_router
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


class CreateWatchSignalRequest(WatchSignalInput):
    portfolio_id: str


# ── 路由工厂 ──────────────────────────────────────────

def create_agent_router() -> APIRouter:
    router = APIRouter(tags=["agent"])
    router.include_router(create_agent_chat_router())
    router.include_router(create_strategy_action_router())

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

    # ── Plans ──

    @router.post("/plans")
    async def create_plan(req: TradePlanInput):
        svc = _get_service()
        return await svc.create_plan(req)

    @router.get("/plans")
    async def list_plans(
        status: str | None = None,
        stock_code: str | None = None,
    ):
        svc = _get_service()
        return await svc.list_plans(status, stock_code)

    @router.get("/plans/{plan_id}")
    async def get_plan(plan_id: str):
        svc = _get_service()
        try:
            return await svc.get_plan(plan_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/plans/{plan_id}")
    async def update_plan(plan_id: str, req: TradePlanUpdate):
        svc = _get_service()
        try:
            return await svc.update_plan(plan_id, req.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/plans/{plan_id}")
    async def delete_plan(plan_id: str):
        svc = _get_service()
        try:
            await svc.delete_plan(plan_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Watchlist ──

    @router.post("/watchlist")
    async def add_watchlist(req: WatchlistInput):
        svc = _get_service()
        return await svc.add_watchlist(req)

    @router.get("/watchlist")
    async def list_watchlist():
        svc = _get_service()
        return await svc.list_watchlist()

    @router.delete("/watchlist/{item_id}")
    async def remove_watchlist(item_id: str):
        svc = _get_service()
        try:
            await svc.remove_watchlist(item_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/watch-signals")
    async def create_watch_signal(req: CreateWatchSignalRequest):
        svc = _get_service()
        try:
            payload = WatchSignalInput(**req.model_dump(exclude={"portfolio_id"}))
            return await svc.create_watch_signal(req.portfolio_id, payload)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/watch-signals")
    async def list_watch_signals(
        portfolio_id: str,
        status: str | None = Query(None),
    ):
        svc = _get_service()
        try:
            return await svc.list_watch_signals(portfolio_id, status=status)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/watch-signals/{signal_id}")
    async def update_watch_signal(signal_id: str, req: dict):
        svc = _get_service()
        try:
            return await svc.update_watch_signal(signal_id, req)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Agent State ──

    @router.get("/state")
    async def get_agent_state(portfolio_id: str):
        svc = _get_service()
        try:
            return await svc.get_agent_state(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/state")
    async def update_agent_state(portfolio_id: str, req: dict):
        svc = _get_service()
        source_run_id = req.pop("source_run_id", None)
        try:
            return await svc.update_agent_state(portfolio_id, req, source_run_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Ledger Read Model ──

    @router.get("/ledger/overview")
    async def get_ledger_overview(portfolio_id: str):
        svc = _get_service()
        try:
            return await svc.get_ledger_overview(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Review / Memory Read Models ──

    @router.get("/reviews")
    async def get_reviews(
        portfolio_id: str,
        days: int = Query(30, ge=1, le=3650),
        type: str | None = Query(None, pattern="^(daily|weekly)$"),
    ):
        svc = _get_service()
        try:
            return await svc.list_review_records(portfolio_id, days=days, review_type=type)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/reviews/stats")
    async def get_review_stats(
        portfolio_id: str,
        days: int = Query(30, ge=1, le=3650),
    ):
        svc = _get_service()
        try:
            return await svc.get_review_stats(portfolio_id, days=days)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/reviews/weekly")
    async def get_weekly_summaries(limit: int = Query(10, ge=1, le=100)):
        svc = _get_service()
        return await svc.list_weekly_summaries(limit=limit)

    @router.get("/memories")
    async def get_memories(
        status: str = Query("active", pattern="^(active|retired|all)$"),
    ):
        svc = _get_service()
        return await svc.list_memories(status=status)

    @router.get("/strategy/history")
    async def get_strategy_history(
        portfolio_id: str,
        limit: int = Query(20, ge=1, le=200),
    ):
        svc = _get_service()
        try:
            return await svc.list_strategy_history(portfolio_id, limit=limit)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/reflections")
    async def get_reflections(
        limit: int = Query(20, ge=1, le=200),
    ):
        svc = _get_service()
        return await svc.list_reflections(limit=limit)

    # ── Brain ──

    @router.get("/brain/config")
    async def get_brain_config():
        svc = _get_service()
        return await svc.get_brain_config()

    @router.patch("/brain/config")
    async def update_brain_config(req: dict):
        svc = _get_service()
        await svc.update_brain_config(req)
        return await svc.get_brain_config()

    @router.get("/brain/runs")
    async def list_brain_runs(portfolio_id: str):
        svc = _get_service()
        return await svc.list_brain_runs(portfolio_id)

    @router.get("/brain/runs/{run_id}")
    async def get_brain_run(run_id: str):
        svc = _get_service()
        try:
            return await svc.get_brain_run(run_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/brain/run")
    async def trigger_brain_run(portfolio_id: str):
        """手动触发一次 Brain 运行"""
        svc = _get_service()
        run_record = await svc.create_brain_run(portfolio_id, "manual")
        import asyncio
        from engine.agent.brain import AgentBrain
        brain = AgentBrain(portfolio_id)
        asyncio.create_task(brain.execute(run_record["id"]))
        return run_record

    return router
