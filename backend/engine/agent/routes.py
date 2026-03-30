"""
Main Agent FastAPI 路由
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from pydantic import ValidationError

from auth import get_current_user
from engine.agent.backtest import AgentBacktestEngine
from engine.agent.chat_routes import create_agent_chat_router
from engine.agent.db import AgentDB
from engine.agent.verification import AgentVerificationHarness, DEFAULT_VERIFY_TIMEOUT_SECONDS
from engine.agent.models import (
    StrategyMemoInput,
    StrategyMemoUpdate,
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


class RunBacktestRequest(BaseModel):
    portfolio_id: str
    start_date: str
    end_date: str
    execution_price_mode: str = "next_open"


class RunVerificationSuiteRequest(BaseModel):
    scenario_id: str = "demo-evolution"
    backtest_start_date: str | None = None
    backtest_end_date: str | None = None
    timeout_seconds: int = 30
    execution_price_mode: str = "next_open"
    smoke_mode: bool = False


class RunAgentVerificationRequest(BaseModel):
    portfolio_id: str
    as_of_date: str | None = None
    include_review: bool = True
    include_weekly: bool = False
    require_trade: bool = False
    timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS


class PrepareDemoAgentRequest(BaseModel):
    scenario_id: str = "demo-evolution"


class VerifyDemoAgentRequest(BaseModel):
    scenario_id: str = "demo-evolution"
    timeout_seconds: int = 30


def _http_status_for_value_error(error: ValueError) -> int:
    return 404 if "不存在" in str(error) else 400


def _get_verification_suite_module():
    from mcpserver import agent_verification_suite

    return agent_verification_suite


def _get_verification_harness() -> AgentVerificationHarness:
    return AgentVerificationHarness()


def _get_verification_suite_runner():
    return _get_verification_suite_module()._run_demo_agent_verification_suite_local


# ── 路由工厂 ──────────────────────────────────────────

def create_agent_router() -> APIRouter:
    router = APIRouter(tags=["agent"])
    router.include_router(create_agent_chat_router())
    router.include_router(create_strategy_action_router())

    def _get_service() -> AgentService:
        db = AgentDB.get_instance()
        return AgentService(db=db, validator=TradeValidator())

    def _get_backtest_engine() -> AgentBacktestEngine:
        db = AgentDB.get_instance()
        return AgentBacktestEngine(db=db, service=AgentService(db=db, validator=TradeValidator()))

    async def _verify_portfolio_owner(portfolio_id: str, user_id: str) -> None:
        """校验 portfolio 归属当前用户"""
        db = AgentDB.get_instance()
        rows = await db.execute_read(
            "SELECT user_id FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Portfolio 不存在: {portfolio_id}")
        if rows[0]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="无权访问此 Portfolio")

    # ── Portfolio ──

    @router.post("/portfolio")
    async def create_portfolio(req: CreatePortfolioRequest, user_id: str = Depends(get_current_user)):
        svc = _get_service()
        try:
            result = await svc.create_portfolio(
                req.id, req.mode, req.initial_capital, req.sim_start_date
            )
            # 写入 user_id
            db = AgentDB.get_instance()
            await db.execute_write(
                "UPDATE agent.portfolio_config SET user_id = ? WHERE id = ?",
                [user_id, req.id],
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.get("/portfolio")
    async def list_portfolios(user_id: str = Depends(get_current_user)):
        db = AgentDB.get_instance()
        return await db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE user_id = ? ORDER BY created_at DESC",
            [user_id],
        )

    @router.get("/portfolio/{portfolio_id}")
    async def get_portfolio(portfolio_id: str, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.get_portfolio(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/portfolio/{portfolio_id}")
    async def delete_portfolio(portfolio_id: str, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            await svc.delete_portfolio(portfolio_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Positions ──

    @router.get("/portfolio/{portfolio_id}/positions")
    async def get_positions(
        portfolio_id: str,
        status: str = Query("open", pattern="^(open|closed)$"),
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        return await svc.get_positions(portfolio_id, status)

    @router.get("/portfolio/{portfolio_id}/positions/{position_id}")
    async def get_position(portfolio_id: str, position_id: str, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
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
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        return await svc.get_trades(portfolio_id, position_id, limit)

    @router.post("/portfolio/{portfolio_id}/trades")
    async def execute_trade(
        portfolio_id: str,
        trade_input: TradeInput,
        position_id: str | None = None,
        trade_date: str | None = None,
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
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
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.create_strategy(
                portfolio_id, position_id, req.model_dump()
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/portfolio/{portfolio_id}/positions/{position_id}/strategy")
    async def get_strategy(portfolio_id: str, position_id: str, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.get_strategy(portfolio_id, position_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Plans ──

    @router.post("/plans")
    async def create_plan(req: TradePlanInput, user_id: str = Depends(get_current_user)):
        svc = _get_service()
        result = await svc.create_plan(req)
        # 写入 user_id
        db = AgentDB.get_instance()
        await db.execute_write(
            "UPDATE agent.trade_plans SET user_id = ? WHERE id = ?",
            [user_id, result["id"]],
        )
        return result

    @router.get("/plans")
    async def list_plans(
        status: str | None = None,
        stock_code: str | None = None,
        user_id: str = Depends(get_current_user),
    ):
        db = AgentDB.get_instance()
        sql = "SELECT * FROM agent.trade_plans WHERE user_id = ?"
        params: list = [user_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if stock_code:
            sql += " AND stock_code = ?"
            params.append(stock_code)
        sql += " ORDER BY created_at DESC"
        return await db.execute_read(sql, params)

    @router.get("/plans/{plan_id}")
    async def get_plan(plan_id: str, user_id: str = Depends(get_current_user)):
        svc = _get_service()
        try:
            plan = await svc.get_plan(plan_id)
            # 校验归属
            if plan.get("user_id", "anonymous") != user_id:
                raise HTTPException(status_code=403, detail="无权访问此交易计划")
            return plan
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/plans/{plan_id}")
    async def update_plan(plan_id: str, req: TradePlanUpdate, user_id: str = Depends(get_current_user)):
        # 先校验归属
        db = AgentDB.get_instance()
        rows = await db.execute_read("SELECT user_id FROM agent.trade_plans WHERE id = ?", [plan_id])
        if not rows:
            raise HTTPException(status_code=404, detail="交易计划不存在")
        if rows[0].get("user_id", "anonymous") != user_id:
            raise HTTPException(status_code=403, detail="无权修改此交易计划")
        svc = _get_service()
        try:
            return await svc.update_plan(plan_id, req.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/plans/{plan_id}")
    async def delete_plan(plan_id: str, user_id: str = Depends(get_current_user)):
        db = AgentDB.get_instance()
        rows = await db.execute_read("SELECT user_id FROM agent.trade_plans WHERE id = ?", [plan_id])
        if not rows:
            raise HTTPException(status_code=404, detail="交易计划不存在")
        if rows[0].get("user_id", "anonymous") != user_id:
            raise HTTPException(status_code=403, detail="无权删除此交易计划")
        svc = _get_service()
        try:
            await svc.delete_plan(plan_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Watchlist ──

    @router.post("/watchlist")
    async def add_watchlist(
        req: WatchlistInput,
        portfolio_id: str | None = Query(None),
        user_id: str = Depends(get_current_user),
    ):
        svc = _get_service()
        result = await svc.add_watchlist(req, portfolio_id=portfolio_id)
        # 写入 user_id
        db = AgentDB.get_instance()
        await db.execute_write(
            "UPDATE agent.watchlist SET user_id = ? WHERE id = ?",
            [user_id, result["id"]],
        )
        return result

    @router.get("/watchlist")
    async def list_watchlist(
        portfolio_id: str | None = Query(None),
        user_id: str = Depends(get_current_user),
    ):
        db = AgentDB.get_instance()
        sql = "SELECT * FROM agent.watchlist WHERE user_id = ?"
        params: list = [user_id]
        if portfolio_id:
            sql += " AND portfolio_id = ?"
            params.append(portfolio_id)
        sql += " ORDER BY created_at DESC"
        return await db.execute_read(sql, params)

    @router.delete("/watchlist/{item_id}")
    async def remove_watchlist(item_id: str, user_id: str = Depends(get_current_user)):
        db = AgentDB.get_instance()
        rows = await db.execute_read("SELECT user_id FROM agent.watchlist WHERE id = ?", [item_id])
        if not rows:
            raise HTTPException(status_code=404, detail="关注项不存在")
        if rows[0].get("user_id", "anonymous") != user_id:
            raise HTTPException(status_code=403, detail="无权删除此关注项")
        svc = _get_service()
        try:
            await svc.remove_watchlist(item_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/strategy-memos")
    async def create_strategy_memo(req: StrategyMemoInput, user_id: str = Depends(get_current_user)):
        svc = _get_service()
        try:
            result = await svc.create_strategy_memo(req)
            # 写入 user_id
            db = AgentDB.get_instance()
            await db.execute_write(
                "UPDATE agent.strategy_memos SET user_id = ? WHERE id = ?",
                [user_id, result["id"]],
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.get("/strategy-memos")
    async def list_strategy_memos(
        portfolio_id: str,
        status: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.list_strategy_memos(portfolio_id, status=status, limit=limit)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.patch("/strategy-memos/{memo_id}")
    async def update_strategy_memo(memo_id: str, req: dict, user_id: str = Depends(get_current_user)):
        db = AgentDB.get_instance()
        rows = await db.execute_read("SELECT user_id FROM agent.strategy_memos WHERE id = ?", [memo_id])
        if not rows:
            raise HTTPException(status_code=404, detail="策略备忘不存在")
        if rows[0].get("user_id", "anonymous") != user_id:
            raise HTTPException(status_code=403, detail="无权修改此策略备忘")
        svc = _get_service()
        try:
            return await svc.update_strategy_memo(
                memo_id,
                StrategyMemoUpdate(**req).model_dump(exclude_none=True),
            )
        except ValidationError:
            raise HTTPException(status_code=400, detail="策略备忘更新参数非法")
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.delete("/strategy-memos/{memo_id}")
    async def delete_strategy_memo(memo_id: str, user_id: str = Depends(get_current_user)):
        db = AgentDB.get_instance()
        rows = await db.execute_read("SELECT user_id FROM agent.strategy_memos WHERE id = ?", [memo_id])
        if not rows:
            raise HTTPException(status_code=404, detail="策略备忘不存在")
        if rows[0].get("user_id", "anonymous") != user_id:
            raise HTTPException(status_code=403, detail="无权删除此策略备忘")
        svc = _get_service()
        try:
            await svc.delete_strategy_memo(memo_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.post("/watch-signals")
    async def create_watch_signal(req: CreateWatchSignalRequest, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(req.portfolio_id, user_id)
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
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.list_watch_signals(portfolio_id, status=status)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/watch-signals/{signal_id}")
    async def update_watch_signal(signal_id: str, req: dict, user_id: str = Depends(get_current_user)):
        svc = _get_service()
        try:
            return await svc.update_watch_signal(signal_id, req)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/info-digests")
    async def list_info_digests(
        portfolio_id: str,
        run_id: str | None = None,
        stock_code: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.list_info_digests(
                portfolio_id=portfolio_id,
                run_id=run_id,
                stock_code=stock_code,
                limit=limit,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Agent State ──

    @router.get("/state")
    async def get_agent_state(portfolio_id: str, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.get_agent_state(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/state")
    async def update_agent_state(portfolio_id: str, req: dict, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        source_run_id = req.pop("source_run_id", None)
        try:
            return await svc.update_agent_state(portfolio_id, req, source_run_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Ledger Read Model ──

    @router.get("/ledger/overview")
    async def get_ledger_overview(portfolio_id: str, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.get_ledger_overview(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/timeline/equity")
    async def get_equity_timeline(
        portfolio_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.get_equity_timeline(
                portfolio_id,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.get("/timeline/replay")
    async def get_timeline_replay(
        portfolio_id: str,
        date: str,
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.get_replay_snapshot(portfolio_id, date)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.get("/timeline/replay-learning")
    async def get_timeline_replay_learning(
        portfolio_id: str,
        date: str,
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.get_replay_learning(portfolio_id, date)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    # ── Review / Memory Read Models ──

    @router.get("/reviews")
    async def get_reviews(
        portfolio_id: str,
        days: int = Query(30, ge=1, le=3650),
        type: str | None = Query(None, pattern="^(daily|weekly)$"),
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.list_review_records(portfolio_id, days=days, review_type=type)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/reviews/stats")
    async def get_review_stats(
        portfolio_id: str,
        days: int = Query(30, ge=1, le=3650),
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
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
        portfolio_id: str | None = Query(None),
        user_id: str = Depends(get_current_user),
    ):
        if portfolio_id:
            await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        return await svc.list_memories(status=status, portfolio_id=portfolio_id)

    @router.post("/verification-suite/run")
    async def run_verification_suite(req: RunVerificationSuiteRequest):
        run_suite = _get_verification_suite_runner()

        try:
            result = await run_suite(
                scenario_id=req.scenario_id,
                backtest_start_date=req.backtest_start_date,
                backtest_end_date=req.backtest_end_date,
                timeout_seconds=req.timeout_seconds,
                execution_price_mode=req.execution_price_mode,
                smoke_mode=req.smoke_mode,
            )
            return json.loads(result)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.post("/verification/run")
    async def run_agent_verification(req: RunAgentVerificationRequest):
        harness = _get_verification_harness()
        try:
            return await harness.verify_cycle(
                portfolio_id=req.portfolio_id,
                as_of_date=req.as_of_date,
                include_review=req.include_review,
                include_weekly=req.include_weekly,
                require_trade=req.require_trade,
                timeout_seconds=req.timeout_seconds,
            )
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.get("/verification/snapshot")
    async def get_agent_verification_snapshot(
        portfolio_id: str,
        run_id: str | None = Query(None),
    ):
        harness = _get_verification_harness()
        try:
            return await harness.inspect_snapshot(portfolio_id=portfolio_id, run_id=run_id)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.post("/demo/prepare")
    async def prepare_demo_agent(req: PrepareDemoAgentRequest):
        harness = _get_verification_harness()
        try:
            return await harness.prepare_demo_portfolio(scenario_id=req.scenario_id)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.post("/demo/verify")
    async def verify_demo_agent(req: VerifyDemoAgentRequest):
        harness = _get_verification_harness()
        try:
            return await harness.verify_demo_cycle(
                scenario_id=req.scenario_id,
                timeout_seconds=req.timeout_seconds,
            )
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.post("/backtest/run")
    async def run_backtest(req: RunBacktestRequest, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(req.portfolio_id, user_id)
        engine = _get_backtest_engine()
        try:
            result = await engine.run_backtest(
                portfolio_id=req.portfolio_id,
                start_date=req.start_date,
                end_date=req.end_date,
                execution_price_mode=req.execution_price_mode,
            )
            return {
                "run_id": result["id"],
                "status": result["status"],
            }
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.get("/backtest/run/{run_id}")
    async def get_backtest_summary(run_id: str):
        engine = _get_backtest_engine()
        try:
            return await engine.get_run_summary(run_id)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.get("/backtest/run/{run_id}/days")
    async def get_backtest_days(run_id: str):
        engine = _get_backtest_engine()
        try:
            return await engine.list_run_days(run_id)
        except ValueError as e:
            raise HTTPException(status_code=_http_status_for_value_error(e), detail=str(e))

    @router.get("/strategy/history")
    async def get_strategy_history(
        portfolio_id: str,
        limit: int = Query(20, ge=1, le=200),
        user_id: str = Depends(get_current_user),
    ):
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        try:
            return await svc.list_strategy_history(portfolio_id, limit=limit)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/reflections")
    async def get_reflections(
        portfolio_id: str | None = Query(None),
        limit: int = Query(20, ge=1, le=200),
        user_id: str = Depends(get_current_user),
    ):
        if portfolio_id:
            await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        return await svc.list_reflections(limit=limit, portfolio_id=portfolio_id)

    # ── Brain ──

    @router.get("/brain/config")
    async def get_brain_config(user_id: str = Depends(get_current_user)):
        svc = _get_service()
        return await svc.get_brain_config()

    @router.patch("/brain/config")
    async def update_brain_config(req: dict, user_id: str = Depends(get_current_user)):
        svc = _get_service()
        await svc.update_brain_config(req)
        return await svc.get_brain_config()

    @router.get("/brain/runs")
    async def list_brain_runs(portfolio_id: str, user_id: str = Depends(get_current_user)):
        await _verify_portfolio_owner(portfolio_id, user_id)
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
    async def trigger_brain_run(portfolio_id: str, user_id: str = Depends(get_current_user)):
        """手动触发一次 Brain 运行"""
        await _verify_portfolio_owner(portfolio_id, user_id)
        svc = _get_service()
        run_record = await svc.create_brain_run(portfolio_id, "manual")
        import asyncio
        from engine.agent.brain import AgentBrain
        brain = AgentBrain(portfolio_id)
        run_id = run_record["id"]

        async def _safe_execute():
            try:
                await brain.execute(run_id)
            except Exception as exc:
                logger.error(f"🧠 Brain 后台任务异常 (run_id={run_id}): {exc}")
                try:
                    await svc.update_brain_run(run_id, {
                        "status": "failed",
                        "current_step": None,
                        "error_message": f"后台任务异常: {exc}",
                    })
                except Exception as db_exc:
                    logger.error(f"🧠 更新失败状态也失败: {db_exc}")

        asyncio.create_task(_safe_execute())
        return run_record

    return router
