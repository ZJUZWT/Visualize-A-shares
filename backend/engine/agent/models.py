"""
Main Agent 数据模型
"""
from __future__ import annotations

from typing import Literal
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
