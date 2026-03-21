"""
Main Agent 数据模型
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel


# ── 持仓 ──────────────────────────────────────────────

class Position(BaseModel):
    id: str
    portfolio_id: str
    stock_code: str
    stock_name: str
    direction: Literal["long"] = "long"
    holding_type: Literal["long_term", "mid_term", "short_term"]
    entry_price: float
    current_qty: int
    cost_basis: float
    entry_date: str
    entry_reason: str
    status: Literal["open", "closed"] = "open"
    closed_at: str | None = None
    closed_reason: str | None = None
    created_at: str


class PositionStrategy(BaseModel):
    id: str
    position_id: str
    holding_type: str
    take_profit: float | None = None
    stop_loss: float | None = None
    reasoning: str
    details: dict = {}
    version: int = 1
    source_run_id: str | None = None
    created_at: str
    updated_at: str


# ── 交易 ──────────────────────────────────────────────

class Trade(BaseModel):
    id: str
    position_id: str
    portfolio_id: str
    action: Literal["buy", "sell", "add", "reduce"]
    stock_code: str
    stock_name: str
    price: float
    quantity: int
    amount: float
    reason: str
    thesis: str
    data_basis: list[str]
    risk_note: str
    invalidation: str
    triggered_by: Literal["manual", "agent"] = "agent"
    created_at: str
    source_run_id: str | None = None
    source_plan_id: str | None = None
    source_strategy_id: str | None = None
    source_strategy_version: int | None = None
    review_result: str | None = None
    review_note: str | None = None
    review_date: str | None = None
    pnl_at_review: float | None = None


class TradeInput(BaseModel):
    """API 入参"""
    action: Literal["buy", "sell", "add", "reduce"]
    stock_code: str
    price: float
    quantity: int
    holding_type: Literal["long_term", "mid_term", "short_term"] | None = None
    reason: str
    thesis: str
    data_basis: list[str]
    risk_note: str
    invalidation: str
    triggered_by: Literal["manual", "agent"] = "agent"


# ── 操作组 ────────────────────────────────────────────

class TradeGroup(BaseModel):
    id: str
    portfolio_id: str
    position_id: str | None = None
    group_type: Literal[
        "build_position", "reduce_position", "close_position",
        "day_trade_session", "rebalance",
    ]
    trade_ids: list[str]
    position_ids: list[str] = []
    thesis: str
    planned_duration: str | None = None
    status: Literal["executing", "completed", "abandoned"] = "executing"
    started_at: str
    completed_at: str | None = None
    review_eligible_after: str | None = None
    review_result: str | None = None
    review_note: str | None = None
    actual_pnl_pct: float | None = None
    created_at: str


# ── 虚拟账户 ──────────────────────────────────────────

class PortfolioConfig(BaseModel):
    id: str
    mode: Literal["live", "training"]
    initial_capital: float
    cash_balance: float
    sim_start_date: str | None = None
    sim_current_date: str | None = None
    created_at: str


class Portfolio(BaseModel):
    """账户概览 — API 返回结构"""
    config: PortfolioConfig
    cash_balance: float
    total_asset: float
    total_pnl: float
    total_pnl_pct: float
    positions: list[Position]


# ── 交易计划备忘录 ────────────────────────────────────

class TradePlan(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    current_price: float | None = None
    direction: Literal["buy", "sell"]
    entry_price: float | None = None
    entry_method: str | None = None
    position_pct: float | None = None
    take_profit: float | None = None
    take_profit_method: str | None = None
    stop_loss: float | None = None
    stop_loss_method: str | None = None
    reasoning: str
    risk_note: str | None = None
    invalidation: str | None = None
    valid_until: str | None = None
    status: Literal["pending", "executing", "completed", "expired", "ignored"] = "pending"
    source_type: Literal["expert", "agent", "manual"] = "expert"
    source_conversation_id: str | None = None
    source_run_id: str | None = None
    created_at: str
    updated_at: str


class TradePlanInput(BaseModel):
    stock_code: str
    stock_name: str
    current_price: float | None = None
    direction: Literal["buy", "sell"]
    entry_price: float | None = None
    entry_method: str | None = None
    position_pct: float | None = None
    take_profit: float | None = None
    take_profit_method: str | None = None
    stop_loss: float | None = None
    stop_loss_method: str | None = None
    reasoning: str
    risk_note: str | None = None
    invalidation: str | None = None
    valid_until: str | None = None
    source_type: Literal["expert", "agent", "manual"] = "expert"
    source_conversation_id: str | None = None


class TradePlanUpdate(BaseModel):
    status: Literal["pending", "executing", "completed", "expired", "ignored"] | None = None


# ── 关注列表 ──────────────────────────────────────────

class WatchlistItem(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    reason: str | None = None
    added_by: Literal["manual", "agent"] = "manual"
    created_at: str


class WatchlistInput(BaseModel):
    stock_code: str
    stock_name: str
    reason: str | None = None


# ── Agent State ───────────────────────────────────────

class AgentState(BaseModel):
    portfolio_id: str
    market_view: dict[str, Any] | None = None
    position_level: str | None = None
    sector_preferences: list[Any] | None = None
    risk_alerts: list[Any] | None = None
    source_run_id: str | None = None
    created_at: str
    updated_at: str


# ── Agent Brain ───────────────────────────────────────

class BrainRun(BaseModel):
    id: str
    portfolio_id: str
    run_type: Literal["scheduled", "manual"] = "scheduled"
    status: Literal["running", "completed", "failed"] = "running"
    candidates: list[dict] | None = None
    analysis_results: list[dict] | None = None
    decisions: list[dict] | None = None
    plan_ids: list[str] | None = None
    trade_ids: list[str] | None = None
    thinking_process: dict[str, Any] | list[Any] | str | None = None
    error_message: str | None = None
    llm_tokens_used: int = 0
    started_at: str
    completed_at: str | None = None


class BrainConfig(BaseModel):
    enable_debate: bool = False
    max_candidates: int = 30
    quant_top_n: int = 20
    max_position_count: int = 10
    single_position_pct: float = 0.15
    schedule_time: str = "15:30"
