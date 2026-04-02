"""
Main Agent 数据模型
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, field_validator


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
    entry_price: str | None = None       # 支持多档："15.2 / 14.5"
    entry_method: str | None = None
    position_pct: float | None = None    # 旧字段，保留向后兼容
    win_odds: str | None = None          # 胜率赔率估计
    take_profit: str | None = None       # 支持多档："18.0 / 20.5"
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
    source_message_id: str | None = None
    source_run_id: str | None = None
    created_at: str
    updated_at: str


class TradePlanInput(BaseModel):
    stock_code: str
    stock_name: str
    current_price: float | None = None
    direction: Literal["buy", "sell"]
    entry_price: str | None = None       # 支持多档："15.2 / 14.5"
    entry_method: str | None = None
    position_pct: float | None = None    # 旧字段，保留向后兼容
    win_odds: str | None = None          # 胜率赔率估计
    take_profit: str | None = None       # 支持多档："18.0 / 20.5"
    take_profit_method: str | None = None
    stop_loss: float | None = None
    stop_loss_method: str | None = None
    reasoning: str
    risk_note: str | None = None
    invalidation: str | None = None
    valid_until: str | None = None
    source_type: Literal["expert", "agent", "manual"] = "expert"
    source_conversation_id: str | None = None
    source_message_id: str | None = None

    @field_validator("entry_price", "take_profit", mode="before")
    @classmethod
    def _coerce_price_text(cls, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(value)
        return value


class TradePlanUpdate(BaseModel):
    status: Literal["pending", "executing", "completed", "expired", "ignored"] | None = None


# ── 策略备忘录 ────────────────────────────────────────

class StrategyMemo(BaseModel):
    id: str
    portfolio_id: str
    source_agent: str | None = None
    source_session_id: str | None = None
    source_message_id: str | None = None
    strategy_key: str
    stock_code: str
    stock_name: str | None = None
    plan_snapshot: dict[str, Any]
    note: str | None = None
    status: Literal["saved", "ignored", "archived"] = "saved"
    created_at: str
    updated_at: str


class StrategyMemoInput(BaseModel):
    portfolio_id: str
    source_agent: str | None = None
    source_session_id: str | None = None
    source_message_id: str | None = None
    strategy_key: str
    stock_code: str
    stock_name: str | None = None
    plan_snapshot: dict[str, Any]
    note: str | None = None
    status: Literal["saved", "ignored", "archived"] = "saved"


class StrategyMemoUpdate(BaseModel):
    note: str | None = None
    status: Literal["saved", "ignored", "archived"] | None = None


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


class WatchSignal(BaseModel):
    id: str
    portfolio_id: str
    stock_code: str | None = None
    sector: str | None = None
    signal_description: str
    check_engine: str
    keywords: list[str] | None = None
    if_triggered: str | None = None
    cycle_context: str | None = None
    status: Literal["watching", "analyzing", "triggered", "failed", "expired", "cancelled"] = "watching"
    trigger_evidence: list[Any] | dict[str, Any] | None = None
    source_run_id: str | None = None
    created_at: str
    updated_at: str
    triggered_at: str | None = None


class WatchSignalInput(BaseModel):
    stock_code: str | None = None
    sector: str | None = None
    signal_description: str
    check_engine: str
    keywords: list[str] | None = None
    if_triggered: str | None = None
    cycle_context: str | None = None
    status: Literal["watching", "analyzing", "triggered", "failed", "expired", "cancelled"] = "watching"
    trigger_evidence: list[Any] | dict[str, Any] | None = None


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


# ── Review / Memory ──────────────────────────────────

class ReviewRecord(BaseModel):
    id: str
    brain_run_id: str | None = None
    trade_id: str | None = None
    stock_code: str | None = None
    stock_name: str | None = None
    action: Literal["buy", "sell", "add", "reduce"] | None = None
    decision_price: float | None = None
    review_price: float | None = None
    pnl_pct: float | None = None
    holding_days: int | None = None
    status: Literal["win", "loss", "holding"] | None = None
    review_date: str | None = None
    review_type: Literal["daily", "weekly"] | None = None
    created_at: str


class WeeklySummary(BaseModel):
    id: str
    week_start: str
    week_end: str
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    total_pnl_pct: float = 0.0
    best_trade_id: str | None = None
    worst_trade_id: str | None = None
    insights: str | None = None
    created_at: str


class AgentMemory(BaseModel):
    id: str
    rule_text: str
    category: str
    source_run_id: str | None = None
    status: Literal["active", "retired"] = "active"
    confidence: float = 0.5
    verify_count: int = 0
    verify_win: int = 0
    created_at: str
    retired_at: str | None = None


class InfoDigest(BaseModel):
    id: str
    portfolio_id: str
    run_id: str
    stock_code: str
    digest_type: str
    raw_summary: dict[str, Any] | list[Any] | str | None = None
    structured_summary: dict[str, Any] | list[Any] | str | None = None
    strategy_relevance: str | None = None
    impact_assessment: Literal["none", "noted", "minor_adjust", "reassess"]
    missing_sources: list[str] | None = None
    created_at: str


# ── Reflection Journals ──────────────────────────────

class DailyReview(BaseModel):
    id: str
    review_date: str
    total_reviews: int = 0
    win_count: int = 0
    loss_count: int = 0
    holding_count: int = 0
    total_pnl_pct: float = 0.0
    summary: str | None = None
    info_review_summary: str | None = None
    info_review_details: dict[str, Any] | list[Any] | str | None = None
    created_at: str


class WeeklyReflection(BaseModel):
    id: str
    week_start: str
    week_end: str
    total_reviews: int = 0
    win_count: int = 0
    loss_count: int = 0
    holding_count: int = 0
    win_rate: float = 0.0
    total_pnl_pct: float = 0.0
    summary: str | None = None
    info_review_summary: str | None = None
    info_review_details: dict[str, Any] | list[Any] | str | None = None
    created_at: str


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
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    execution_summary: dict[str, Any] | None = None
    info_digest_ids: list[str] | None = None
    triggered_signal_ids: list[str] | None = None
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


# ── Strategy Actions ─────────────────────────────────

class StrategyActionPlanPayload(BaseModel):
    stock_code: str
    stock_name: str
    direction: Literal["buy", "sell"]
    current_price: float | None = None
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
    holding_type: Literal["long_term", "mid_term", "short_term"] = "mid_term"


class AdoptStrategyRequest(BaseModel):
    portfolio_id: str
    session_id: str
    message_id: str
    strategy_key: str
    plan: StrategyActionPlanPayload
    source_run_id: str | None = None


class RejectStrategyRequest(BaseModel):
    portfolio_id: str
    session_id: str
    message_id: str
    strategy_key: str
    plan: StrategyActionPlanPayload
    reason: str | None = None
    source_run_id: str | None = None
