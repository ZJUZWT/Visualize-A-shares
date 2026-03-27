"""
AgentService — Main Agent 业务逻辑层
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta

from loguru import logger

from engine.agent.db import AgentDB
from pydantic import ValidationError

from engine.agent.models import StrategyMemoInput, TradeInput
from engine.agent.state import get_state, upsert_state
from engine.agent.validator import TradeValidator
import engine.data as data_module


BRAIN_RUN_JSON_FIELDS = (
    "candidates",
    "analysis_results",
    "decisions",
    "plan_ids",
    "trade_ids",
    "thinking_process",
    "state_before",
    "state_after",
    "execution_summary",
    "info_digest_ids",
    "triggered_signal_ids",
)
WATCH_SIGNAL_JSON_FIELDS = ("keywords", "trigger_evidence")
INFO_DIGEST_JSON_FIELDS = ("raw_summary", "structured_summary", "missing_sources")
REFLECTION_JSON_FIELDS = ("info_review_details",)
STRATEGY_MEMO_JSON_FIELDS = ("plan_snapshot",)
TRADE_JSON_FIELDS = ("data_basis",)
POSITION_STRATEGY_JSON_FIELDS = ("details",)
STRATEGY_MEMO_STATUSES = {"saved", "ignored", "archived"}
WATCH_SIGNAL_STATUSES = {
    "watching",
    "analyzing",
    "triggered",
    "failed",
    "expired",
    "cancelled",
}


def _decode_json_value(value):
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


import re as _re
_CONTROL_CHAR_RE = _re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _normalize_json_safe(value):
    if isinstance(value, dict):
        return {key: _normalize_json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_safe(item) for item in value]
    if isinstance(value, str):
        # 移除 JSON 不允许的控制字符（保留 \n \r \t）
        return _CONTROL_CHAR_RE.sub('', value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return value


def _normalize_brain_run(row: dict) -> dict:
    normalized = _normalize_json_safe(dict(row))
    for field in BRAIN_RUN_JSON_FIELDS:
        normalized[field] = _decode_json_value(normalized.get(field))
        normalized[field] = _normalize_json_safe(normalized[field])
    return normalized


def _normalize_record(row: dict) -> dict:
    normalized = _normalize_json_safe(dict(row))
    for field in REFLECTION_JSON_FIELDS:
        normalized[field] = _decode_json_value(normalized.get(field))
        normalized[field] = _normalize_json_safe(normalized[field])
    for field in ("review_date", "week_start", "week_end"):
        value = normalized.get(field)
        if isinstance(value, str) and "T" in value:
            normalized[field] = value.split("T", 1)[0]
    return normalized


def _normalize_trade_record(row: dict) -> dict:
    normalized = _normalize_record(row)
    for field in TRADE_JSON_FIELDS:
        normalized[field] = _decode_json_value(normalized.get(field))
        normalized[field] = _normalize_json_safe(normalized[field])
    return normalized


def _build_info_review_payload(row: dict) -> dict | None:
    summary = row.get("info_review_summary")
    details = row.get("info_review_details")
    if summary is None and details is None:
        return None
    return {
        "summary": summary,
        "details": details,
    }


def _normalize_watch_signal(row: dict) -> dict:
    normalized = _normalize_record(row)
    for field in WATCH_SIGNAL_JSON_FIELDS:
        normalized[field] = _decode_json_value(normalized.get(field))
        normalized[field] = _normalize_json_safe(normalized[field])
    return normalized


def _normalize_info_digest(row: dict) -> dict:
    normalized = _normalize_record(row)
    for field in INFO_DIGEST_JSON_FIELDS:
        normalized[field] = _decode_json_value(normalized.get(field))
        normalized[field] = _normalize_json_safe(normalized[field])
    return normalized


def _normalize_strategy_memo(row: dict) -> dict:
    normalized = _normalize_record(row)
    for field in STRATEGY_MEMO_JSON_FIELDS:
        normalized[field] = _decode_json_value(normalized.get(field))
        normalized[field] = _normalize_json_safe(normalized[field])
    return normalized


def _normalize_position_strategy(row: dict) -> dict:
    normalized = _normalize_record(row)
    for field in POSITION_STRATEGY_JSON_FIELDS:
        normalized[field] = _decode_json_value(normalized.get(field))
        normalized[field] = _normalize_json_safe(normalized[field])
    return normalized


def _coerce_to_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value is None:
        raise ValueError("缺少日期")
    text = str(value)
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError as exc:
            raise ValueError(f"非法日期: {value}") from exc


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _daterange(start_day: date, end_day: date) -> list[date]:
    days = []
    current = start_day
    while current <= end_day:
        days.append(current)
        current += timedelta(days=1)
    return days


def _lookup_close_on_or_before(
    price_history: dict[str, float],
    target_day: date,
    fallback: float,
) -> float:
    target_iso = target_day.isoformat()
    candidates = [day for day in price_history.keys() if day <= target_iso]
    if not candidates:
        return _round_money(fallback)
    return _round_money(price_history[max(candidates)])


def _lookup_next_close_after(
    price_history: dict[str, float],
    target_day: date,
) -> tuple[str, float] | None:
    target_iso = target_day.isoformat()
    candidates = [day for day in price_history.keys() if day > target_iso]
    if not candidates:
        return None
    next_day = min(candidates)
    return next_day, _round_money(price_history[next_day])


def _build_position_read_model(position: dict) -> dict:
    market_value = round(position["entry_price"] * position["current_qty"], 2)
    unrealized_pnl = round(market_value - position["cost_basis"], 2)
    unrealized_pnl_pct = round(
        (unrealized_pnl / position["cost_basis"] * 100) if position["cost_basis"] else 0.0,
        2,
    )
    return {
        "id": position["id"],
        "stock_code": position["stock_code"],
        "stock_name": position["stock_name"],
        "holding_type": position["holding_type"],
        "current_qty": position["current_qty"],
        "entry_price": position["entry_price"],
        "cost_basis": position["cost_basis"],
        "entry_date": position["entry_date"],
        "status": position["status"],
        "market_value": market_value,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
    }


def _build_strategy_summary(strategy: dict | None) -> dict | None:
    if not strategy:
        return None
    return {
        "id": strategy["id"],
        "holding_type": strategy.get("holding_type"),
        "take_profit": strategy.get("take_profit"),
        "stop_loss": strategy.get("stop_loss"),
        "reasoning": strategy.get("reasoning"),
        "details": strategy.get("details") or {},
        "version": strategy.get("version"),
        "source_run_id": strategy.get("source_run_id"),
        "created_at": strategy.get("created_at"),
        "updated_at": strategy.get("updated_at"),
    }


def _build_position_status_signal(position_model: dict, latest_strategy: dict | None) -> tuple[str, str]:
    pnl_pct = position_model.get("unrealized_pnl_pct")
    stop_loss = latest_strategy.get("stop_loss") if latest_strategy else None
    take_profit = latest_strategy.get("take_profit") if latest_strategy else None
    entry_price = position_model.get("entry_price")

    if pnl_pct is not None and pnl_pct <= -5:
        return "danger", "浮亏已超过 5%，接近防守阈值"
    if (
        stop_loss is not None
        and entry_price is not None
        and entry_price > 0
        and abs((entry_price - stop_loss) / entry_price * 100) <= 5
    ):
        return "warning", "止损阈值距离较近，需要提高警惕"
    if pnl_pct is not None and pnl_pct >= 8:
        return "warning", "浮盈已较大，需关注兑现或上调止盈"
    if (
        take_profit is not None
        and entry_price is not None
        and entry_price > 0
        and abs((take_profit - entry_price) / entry_price * 100) <= 8
    ):
        return "warning", "止盈空间有限，建议关注执行节奏"
    return "healthy", "策略阈值仍处于正常观察区间"


def _build_trade_read_model(trade: dict) -> dict:
    return {
        "id": trade["id"],
        "position_id": trade["position_id"],
        "action": trade["action"],
        "stock_code": trade["stock_code"],
        "stock_name": trade["stock_name"],
        "price": trade["price"],
        "quantity": trade["quantity"],
        "amount": trade["amount"],
        "reason": trade["reason"],
        "thesis": trade["thesis"],
        "triggered_by": trade["triggered_by"],
        "created_at": trade["created_at"],
        "source_run_id": trade.get("source_run_id"),
        "source_plan_id": trade.get("source_plan_id"),
        "source_strategy_id": trade.get("source_strategy_id"),
        "source_strategy_version": trade.get("source_strategy_version"),
    }


def _build_plan_read_model(plan: dict) -> dict:
    return {
        "id": plan["id"],
        "stock_code": plan["stock_code"],
        "stock_name": plan["stock_name"],
        "direction": plan["direction"],
        "status": plan["status"],
        "entry_price": plan["entry_price"],
        "current_price": plan["current_price"],
        "position_pct": plan.get("position_pct"),
        "win_odds": plan.get("win_odds"),
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        "source_run_id": plan.get("source_run_id"),
    }


def _build_strategy_history_item(run: dict) -> dict:
    state_after = run.get("state_after") or {}
    execution_summary = run.get("execution_summary") or {}
    return {
        "run_id": run["id"],
        "occurred_at": run.get("completed_at") or run.get("started_at"),
        "market_view": state_after.get("market_view"),
        "position_level": state_after.get("position_level"),
        "sector_preferences": state_after.get("sector_preferences") or [],
        "risk_alerts": state_after.get("risk_alerts") or [],
        "candidate_count": execution_summary.get("candidate_count", 0),
        "analysis_count": execution_summary.get("analysis_count", 0),
        "decision_count": execution_summary.get("decision_count", 0),
        "plan_count": execution_summary.get("plan_count", 0),
        "trade_count": execution_summary.get("trade_count", 0),
    }


def _build_daily_reflection_item(row: dict) -> dict:
    total_trades = row.get("total_trades")
    if total_trades is None:
        total_trades = row.get("total_reviews", 0)
    win_count = row.get("win_count", 0)
    loss_count = row.get("loss_count", 0)
    holding_count = row.get("holding_count", 0)
    win_rate = row.get("win_rate")
    if win_rate is None:
        decided_count = (win_count or 0) + (loss_count or 0)
        win_rate = ((win_count or 0) / decided_count) if decided_count else 0.0
    avg_pnl_pct = row.get("avg_pnl_pct")
    if avg_pnl_pct is None:
        avg_pnl_pct = ((row.get("total_pnl_pct") or 0.0) / total_trades) if total_trades else 0.0
    return {
        "id": row["id"],
        "kind": "daily",
        "date": row["review_date"],
        "summary": row.get("summary") or "",
        "created_at": row.get("created_at"),
        "metrics": {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "holding_count": holding_count,
            "win_rate": win_rate,
            "avg_pnl_pct": avg_pnl_pct,
            "total_pnl_pct": row.get("total_pnl_pct", 0.0),
        },
        "details": {
            "portfolio_id": row.get("portfolio_id"),
            "notes": row.get("notes"),
            "info_review": _build_info_review_payload(row),
        },
    }


def _build_weekly_reflection_item(row: dict) -> dict:
    total_trades = row.get("total_trades")
    if total_trades is None:
        total_trades = row.get("total_reviews", 0)
    return {
        "id": row["id"],
        "kind": "weekly",
        "date": row["week_end"],
        "summary": row.get("summary") or "",
        "created_at": row.get("created_at"),
        "metrics": {
            "total_trades": total_trades,
            "win_count": row.get("win_count", 0),
            "loss_count": row.get("loss_count", 0),
            "win_rate": row.get("win_rate", 0.0),
            "total_pnl_pct": row.get("total_pnl_pct", 0.0),
        },
        "details": {
            "week_start": row.get("week_start"),
            "week_end": row.get("week_end"),
            "info_review": _build_info_review_payload(row),
        },
    }


class AgentService:
    """Main Agent 业务逻辑"""

    def __init__(self, db: AgentDB, validator: TradeValidator):
        self.db = db
        self.validator = validator

    # ── Portfolio CRUD ────────────────────────────────

    async def create_portfolio(
        self,
        portfolio_id: str,
        mode: str,
        initial_capital: float,
        sim_start_date: str | None = None,
    ) -> dict:
        """创建虚拟账户"""
        existing = await self.db.execute_read(
            "SELECT id FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if existing:
            raise ValueError(f"账户 {portfolio_id} 已存在")

        if mode == "live":
            lives = await self.db.execute_read(
                "SELECT id FROM agent.portfolio_config WHERE mode = 'live'"
            )
            if lives:
                raise ValueError(f"live 账户已存在: {lives[0]['id']}，不能重复创建")

        now = datetime.now().isoformat()
        await self.db.execute_write(
            """INSERT INTO agent.portfolio_config
               (id, mode, initial_capital, cash_balance, sim_start_date, sim_current_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [portfolio_id, mode, initial_capital, initial_capital,
             sim_start_date, sim_start_date, now],
        )
        logger.info(f"创建账户: {portfolio_id} ({mode}), 初始资金: {initial_capital}")
        rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        return rows[0]

    async def list_portfolios(self) -> list[dict]:
        """列出所有账户"""
        return await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config ORDER BY created_at"
        )

    async def delete_portfolio(self, portfolio_id: str):
        """删除账户及其所有关联数据"""
        rows = await self.db.execute_read(
            "SELECT id FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if not rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")

        # 级联删除所有关联数据
        await self.db.execute_transaction([
            ("DELETE FROM agent.positions WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.trades WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.trade_groups WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.watch_signals WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.info_digests WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.brain_runs WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.agent_state WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.strategy_memos WHERE portfolio_id = ?", [portfolio_id]),
            ("DELETE FROM agent.portfolio_config WHERE id = ?", [portfolio_id]),
        ])
        logger.info(f"已删除账户及关联数据: {portfolio_id}")

    async def get_portfolio(self, portfolio_id: str) -> dict:
        """获取账户概览"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if not rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")
        config = rows[0]

        positions = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE portfolio_id = ? AND status = 'open'",
            [portfolio_id],
        )

        cash = config["cash_balance"]
        # TODO: Phase 1B — 调用 DataEngine 获取实时价格计算持仓市值
        position_value = sum(p["entry_price"] * p["current_qty"] for p in positions)
        total_asset = cash + position_value
        total_pnl = total_asset - config["initial_capital"]
        total_pnl_pct = (total_pnl / config["initial_capital"] * 100) if config["initial_capital"] > 0 else 0.0

        return {
            "config": config,
            "cash_balance": cash,
            "total_asset": round(total_asset, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "positions": positions,
        }

    async def get_positions(
        self, portfolio_id: str, status: str = "open"
    ) -> list[dict]:
        """持仓列表"""
        return await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE portfolio_id = ? AND status = ?",
            [portfolio_id, status],
        )

    async def get_position(self, portfolio_id: str, position_id: str) -> dict:
        """单个持仓详情（含策略 + 交易记录）"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
            [position_id, portfolio_id],
        )
        if not rows:
            raise ValueError(f"持仓 {position_id} 不存在")
        position = rows[0]

        strategies = await self.db.execute_read(
            "SELECT * FROM agent.position_strategies WHERE position_id = ? ORDER BY version DESC",
            [position_id],
        )
        trades = await self.db.execute_read(
            "SELECT * FROM agent.trades WHERE position_id = ? ORDER BY created_at DESC",
            [position_id],
        )
        position["strategies"] = strategies
        position["trades"] = trades
        return position

    async def get_trades(
        self, portfolio_id: str, position_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        """交易记录"""
        if position_id:
            return await self.db.execute_read(
                "SELECT * FROM agent.trades WHERE portfolio_id = ? AND position_id = ? ORDER BY created_at DESC LIMIT ?",
                [portfolio_id, position_id, limit],
            )
        return await self.db.execute_read(
            "SELECT * FROM agent.trades WHERE portfolio_id = ? ORDER BY created_at DESC LIMIT ?",
            [portfolio_id, limit],
        )

    # ── Trade Execution ───────────────────────────────

    async def execute_trade(
        self,
        portfolio_id: str,
        trade_input: TradeInput,
        trade_date: str,
        position_id: str | None = None,
        stock_name: str | None = None,
        source_run_id: str | None = None,
        source_plan_id: str | None = None,
        source_strategy_id: str | None = None,
        source_strategy_version: int | None = None,
    ) -> dict:
        """
        执行交易 — 核心方法

        Args:
            portfolio_id: 账户 ID
            trade_input: 交易入参
            trade_date: 交易日期 YYYY-MM-DD
            position_id: add/sell/reduce 时指定持仓 ID
            stock_name: 股票名称（可选，未传时用 stock_code 占位）
        """
        action = trade_input.action
        code = trade_input.stock_code
        name = stock_name or code

        # ── 1. 校验股票代码 ──
        ok, msg = self.validator.validate_code(code, name)
        if not ok:
            raise ValueError(msg)

        # ── 2. 校验数量 ──
        ok, msg = self.validator.validate_quantity(trade_input.quantity)
        if not ok:
            raise ValueError(msg)

        # ── 3. 获取账户 ──
        portfolio_rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?", [portfolio_id]
        )
        if not portfolio_rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")
        portfolio = portfolio_rows[0]
        cash = portfolio["cash_balance"]

        # ── 4. 计算成交价（含滑点）──
        exec_price = self.validator.apply_slippage(action, trade_input.price)
        amount = exec_price * trade_input.quantity
        fee = self.validator.calc_fee(action, exec_price, trade_input.quantity, code)

        # ── 5. 按操作类型处理 ──
        if action == "buy":
            if not trade_input.holding_type:
                raise ValueError("buy 操作必须指定 holding_type")

            ok, msg = self.validator.validate_cash(action, exec_price, trade_input.quantity, cash)
            if not ok:
                raise ValueError(msg)

            pos_id = str(uuid.uuid4())
            cost_basis = amount + fee
            now = datetime.now().isoformat()

            queries = [
                (
                    """INSERT INTO agent.positions
                       (id, portfolio_id, stock_code, stock_name, direction, holding_type,
                        entry_price, current_qty, cost_basis, entry_date, entry_reason, status, created_at)
                       VALUES (?, ?, ?, ?, 'long', ?, ?, ?, ?, ?, ?, 'open', ?)""",
                    [pos_id, portfolio_id, code, name, trade_input.holding_type,
                     exec_price, trade_input.quantity, cost_basis, trade_date,
                     trade_input.reason, now],
                ),
                self._insert_trade_sql(
                    portfolio_id, pos_id, trade_input, exec_price, amount, name, now,
                    source_run_id=source_run_id,
                    source_plan_id=source_plan_id,
                    source_strategy_id=source_strategy_id,
                    source_strategy_version=source_strategy_version,
                ),
                (
                    "UPDATE agent.portfolio_config SET cash_balance = cash_balance - ? WHERE id = ?",
                    [cost_basis, portfolio_id],
                ),
            ]
            await self.db.execute_transaction(queries)
            position_id = pos_id

        elif action == "add":
            if not position_id:
                raise ValueError("add 操作必须指定 position_id")

            pos_rows = await self.db.execute_read(
                "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
                [position_id, portfolio_id],
            )
            if not pos_rows:
                raise ValueError(f"持仓 {position_id} 不存在")
            position = pos_rows[0]

            ok, msg = self.validator.validate_cash(action, exec_price, trade_input.quantity, cash)
            if not ok:
                raise ValueError(msg)

            old_qty = position["current_qty"]
            old_cost = position["cost_basis"]
            new_cost = amount + fee
            total_qty = old_qty + trade_input.quantity
            total_cost = old_cost + new_cost
            new_avg_price = total_cost / total_qty

            now = datetime.now().isoformat()
            queries = [
                (
                    """UPDATE agent.positions
                       SET entry_price = ?, current_qty = ?, cost_basis = ?
                       WHERE id = ?""",
                    [round(new_avg_price, 4), total_qty, round(total_cost, 2), position_id],
                ),
                self._insert_trade_sql(
                    portfolio_id, position_id, trade_input, exec_price, amount, name, now,
                    source_run_id=source_run_id,
                    source_plan_id=source_plan_id,
                    source_strategy_id=source_strategy_id,
                    source_strategy_version=source_strategy_version,
                ),
                (
                    "UPDATE agent.portfolio_config SET cash_balance = cash_balance - ? WHERE id = ?",
                    [new_cost, portfolio_id],
                ),
            ]
            await self.db.execute_transaction(queries)

        elif action in ("sell", "reduce"):
            if not position_id:
                raise ValueError(f"{action} 操作必须指定 position_id")

            pos_rows = await self.db.execute_read(
                "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
                [position_id, portfolio_id],
            )
            if not pos_rows:
                raise ValueError(f"持仓 {position_id} 不存在")
            position = pos_rows[0]

            # T+1 检查 — entry_date 可能是 date 对象，转为字符串
            entry_date_str = str(position["entry_date"])
            ok, msg = self.validator.validate_t_plus_1(action, entry_date_str, trade_date)
            if not ok:
                raise ValueError(msg)

            ok, msg = self.validator.validate_position_qty(action, position["current_qty"], trade_input.quantity)
            if not ok:
                raise ValueError(msg)

            new_qty = position["current_qty"] - trade_input.quantity
            proceeds = amount - fee
            now = datetime.now().isoformat()

            queries = [
                self._insert_trade_sql(
                    portfolio_id, position_id, trade_input, exec_price, amount, name, now,
                    source_run_id=source_run_id,
                    source_plan_id=source_plan_id,
                    source_strategy_id=source_strategy_id,
                    source_strategy_version=source_strategy_version,
                ),
                (
                    "UPDATE agent.portfolio_config SET cash_balance = cash_balance + ? WHERE id = ?",
                    [proceeds, portfolio_id],
                ),
            ]

            if new_qty == 0:
                queries.append((
                    "UPDATE agent.positions SET current_qty = 0, status = 'closed', closed_at = ?, closed_reason = ? WHERE id = ?",
                    [now, trade_input.reason, position_id],
                ))
            else:
                queries.append((
                    "UPDATE agent.positions SET current_qty = ? WHERE id = ?",
                    [new_qty, position_id],
                ))

            await self.db.execute_transaction(queries)

        # ── 6. 返回结果 ──
        pos_rows = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE id = ?", [position_id]
        )
        trade_rows = await self.db.execute_read(
            "SELECT * FROM agent.trades WHERE position_id = ? ORDER BY created_at DESC LIMIT 1",
            [position_id],
        )

        return {
            "position": pos_rows[0] if pos_rows else None,
            "trade": trade_rows[0] if trade_rows else None,
            "fee": fee,
            "exec_price": exec_price,
        }

    def _insert_trade_sql(
        self, portfolio_id, position_id, ti: TradeInput,
        exec_price, amount, stock_name, now,
        source_run_id: str | None = None,
        source_plan_id: str | None = None,
        source_strategy_id: str | None = None,
        source_strategy_version: int | None = None,
    ) -> tuple[str, list]:
        """生成 INSERT trade 的 SQL + params"""
        trade_id = str(uuid.uuid4())
        return (
            """INSERT INTO agent.trades
               (id, portfolio_id, position_id, action, stock_code, stock_name,
                price, quantity, amount, reason, thesis, data_basis,
                risk_note, invalidation, triggered_by, created_at,
                source_run_id, source_plan_id, source_strategy_id, source_strategy_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [trade_id, portfolio_id, position_id, ti.action, ti.stock_code,
             stock_name, exec_price, ti.quantity, round(amount, 2),
             ti.reason, ti.thesis, json.dumps(ti.data_basis, ensure_ascii=False),
             ti.risk_note, ti.invalidation, ti.triggered_by, now,
             source_run_id, source_plan_id, source_strategy_id, source_strategy_version],
        )

    # ── Strategy CRUD ─────────────────────────────────

    async def create_strategy(
        self,
        portfolio_id: str,
        position_id: str,
        strategy_input: dict,
        source_run_id: str | None = None,
    ) -> dict:
        """创建/更新持仓策略（version 自增）"""
        pos_rows = await self.db.execute_read(
            "SELECT * FROM agent.positions WHERE id = ? AND portfolio_id = ?",
            [position_id, portfolio_id],
        )
        if not pos_rows:
            raise ValueError(f"持仓 {position_id} 不存在")
        position = pos_rows[0]

        existing = await self.db.execute_read(
            "SELECT MAX(version) as max_ver FROM agent.position_strategies WHERE position_id = ?",
            [position_id],
        )
        max_ver = existing[0]["max_ver"] if existing and existing[0]["max_ver"] is not None else 0
        new_version = max_ver + 1

        strategy_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        details = strategy_input.get("details", {})

        await self.db.execute_write(
            """INSERT INTO agent.position_strategies
               (id, position_id, holding_type, take_profit, stop_loss,
                reasoning, details, version, source_run_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [strategy_id, position_id, position["holding_type"],
             strategy_input.get("take_profit"), strategy_input.get("stop_loss"),
             strategy_input.get("reasoning", ""),
             json.dumps(details, ensure_ascii=False) if details else None,
             new_version, source_run_id, now, now],
        )

        rows = await self.db.execute_read(
            "SELECT * FROM agent.position_strategies WHERE id = ?", [strategy_id]
        )
        return rows[0]

    async def get_strategy(
        self, portfolio_id: str, position_id: str
    ) -> list[dict]:
        """获取持仓策略（含历史版本，最新在前）"""
        pos_rows = await self.db.execute_read(
            "SELECT id FROM agent.positions WHERE id = ? AND portfolio_id = ?",
            [position_id, portfolio_id],
        )
        if not pos_rows:
            raise ValueError(f"持仓 {position_id} 不存在")

        return await self.db.execute_read(
            "SELECT * FROM agent.position_strategies WHERE position_id = ? ORDER BY version DESC",
            [position_id],
        )

    # ── Plans CRUD ────────────────────────────────────

    async def create_plan(self, plan_input, source_run_id: str | None = None) -> dict:
        """创建交易计划"""
        plan_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        await self.db.execute_write(
            """INSERT INTO agent.trade_plans
               (id, stock_code, stock_name, current_price, direction,
                entry_price, entry_method, position_pct, win_odds,
                take_profit, take_profit_method, stop_loss, stop_loss_method,
                reasoning, risk_note, invalidation, valid_until,
                status, source_type, source_conversation_id, source_run_id,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
            [plan_id, plan_input.stock_code, plan_input.stock_name,
             plan_input.current_price, plan_input.direction,
             plan_input.entry_price, plan_input.entry_method,
             plan_input.position_pct, plan_input.win_odds,
             plan_input.take_profit, plan_input.take_profit_method,
             plan_input.stop_loss, plan_input.stop_loss_method,
             plan_input.reasoning, plan_input.risk_note, plan_input.invalidation,
             plan_input.valid_until,
             plan_input.source_type, plan_input.source_conversation_id, source_run_id,
             now, now],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.trade_plans WHERE id = ?", [plan_id]
        )
        return rows[0]

    async def list_plans(
        self, status: str | None = None, stock_code: str | None = None
    ) -> list[dict]:
        """列出交易计划"""
        sql = "SELECT * FROM agent.trade_plans WHERE 1=1"
        params = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if stock_code:
            sql += " AND stock_code = ?"
            params.append(stock_code)
        sql += " ORDER BY created_at DESC"
        return await self.db.execute_read(sql, params if params else None)

    async def get_plan(self, plan_id: str) -> dict:
        """获取单个交易计划"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.trade_plans WHERE id = ?", [plan_id]
        )
        if not rows:
            raise ValueError(f"交易计划 {plan_id} 不存在")
        return rows[0]

    async def update_plan(self, plan_id: str, updates: dict) -> dict:
        """更新交易计划"""
        await self.get_plan(plan_id)  # 确认存在
        now = datetime.now().isoformat()
        if "status" in updates and updates["status"]:
            await self.db.execute_write(
                "UPDATE agent.trade_plans SET status = ?, updated_at = ? WHERE id = ?",
                [updates["status"], now, plan_id],
            )
        return await self.get_plan(plan_id)

    async def update_trade_sources(
        self,
        trade_id: str,
        source_strategy_id: str | None = None,
        source_strategy_version: int | None = None,
    ) -> dict:
        """补写交易与策略的引用关系"""
        sets = []
        params = []
        if source_strategy_id is not None:
            sets.append("source_strategy_id = ?")
            params.append(source_strategy_id)
        if source_strategy_version is not None:
            sets.append("source_strategy_version = ?")
            params.append(source_strategy_version)
        if sets:
            params.append(trade_id)
            await self.db.execute_write(
                f"UPDATE agent.trades SET {', '.join(sets)} WHERE id = ?",
                params,
            )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.trades WHERE id = ?",
            [trade_id],
        )
        return rows[0]

    async def delete_plan(self, plan_id: str):
        """删除交易计划"""
        await self.get_plan(plan_id)  # 确认存在
        await self.db.execute_write(
            "DELETE FROM agent.trade_plans WHERE id = ?", [plan_id]
        )

    # ── Watchlist CRUD ─────────────────────────────────

    async def add_watchlist(self, item_input, portfolio_id: str | None = None) -> dict:
        """添加关注"""
        item_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.db.execute_write(
            """INSERT INTO agent.watchlist (id, stock_code, stock_name, reason, added_by, portfolio_id, created_at)
               VALUES (?, ?, ?, ?, 'manual', ?, ?)""",
            [item_id, item_input.stock_code, item_input.stock_name,
             item_input.reason, portfolio_id, now],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.watchlist WHERE id = ?", [item_id]
        )
        return rows[0]

    async def list_watchlist(self, portfolio_id: str | None = None) -> list[dict]:
        """关注列表"""
        if portfolio_id:
            return await self.db.execute_read(
                "SELECT * FROM agent.watchlist WHERE portfolio_id = ? ORDER BY created_at DESC",
                [portfolio_id],
            )
        return await self.db.execute_read(
            "SELECT * FROM agent.watchlist ORDER BY created_at DESC"
        )

    async def remove_watchlist(self, item_id: str):
        """取消关注"""
        rows = await self.db.execute_read(
            "SELECT id FROM agent.watchlist WHERE id = ?", [item_id]
        )
        if not rows:
            raise ValueError(f"关注项 {item_id} 不存在")
        await self.db.execute_write(
            "DELETE FROM agent.watchlist WHERE id = ?", [item_id]
        )

    async def create_strategy_memo(self, payload) -> dict:
        try:
            if isinstance(payload, StrategyMemoInput):
                memo_input = payload
            elif hasattr(payload, "model_dump"):
                memo_input = StrategyMemoInput(**payload.model_dump())
            else:
                memo_input = StrategyMemoInput(**dict(payload))
        except ValidationError as exc:
            raise ValueError("策略备忘参数非法") from exc

        data = memo_input.model_dump()
        await self.get_portfolio(data["portfolio_id"])

        status = data.get("status") or "saved"
        if status not in STRATEGY_MEMO_STATUSES:
            raise ValueError(f"非法状态: {status}")

        source_message_id = data.get("source_message_id")
        if source_message_id:
            rows = await self.db.execute_read(
                """
                SELECT *
                FROM agent.strategy_memos
                WHERE portfolio_id = ?
                  AND source_message_id = ?
                  AND strategy_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [data["portfolio_id"], source_message_id, data["strategy_key"]],
            )
            if rows:
                return _normalize_strategy_memo(rows[0])

        memo_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        plan_snapshot = _normalize_json_safe(data["plan_snapshot"])
        await self.db.execute_write(
            """
            INSERT INTO agent.strategy_memos (
                id, portfolio_id, source_agent, source_session_id, source_message_id,
                strategy_key, stock_code, stock_name, plan_snapshot, note, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                memo_id,
                data["portfolio_id"],
                data.get("source_agent"),
                data.get("source_session_id"),
                source_message_id,
                data["strategy_key"],
                data["stock_code"],
                data.get("stock_name"),
                json.dumps(plan_snapshot, ensure_ascii=False),
                data.get("note"),
                status,
                now,
                now,
            ],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.strategy_memos WHERE id = ?",
            [memo_id],
        )
        return _normalize_strategy_memo(rows[0])

    async def list_strategy_memos(
        self,
        portfolio_id: str,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        await self.get_portfolio(portfolio_id)
        if status is not None and status not in STRATEGY_MEMO_STATUSES:
            raise ValueError(f"非法状态: {status}")

        sql = """
            SELECT *
            FROM agent.strategy_memos
            WHERE portfolio_id = ?
        """
        params: list = [portfolio_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.execute_read(sql, params)
        return [_normalize_strategy_memo(row) for row in rows]

    async def update_strategy_memo(self, memo_id: str, updates: dict) -> dict:
        rows = await self.db.execute_read(
            "SELECT * FROM agent.strategy_memos WHERE id = ?",
            [memo_id],
        )
        if not rows:
            raise ValueError(f"策略备忘 {memo_id} 不存在")

        sets = []
        params = []
        if "note" in updates:
            sets.append("note = ?")
            params.append(updates["note"])
        if "status" in updates:
            status = updates["status"]
            if status not in STRATEGY_MEMO_STATUSES:
                raise ValueError(f"非法状态: {status}")
            sets.append("status = ?")
            params.append(status)

        if sets:
            sets.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(memo_id)
            await self.db.execute_write(
                f"UPDATE agent.strategy_memos SET {', '.join(sets)} WHERE id = ?",
                params,
            )

        refreshed = await self.db.execute_read(
            "SELECT * FROM agent.strategy_memos WHERE id = ?",
            [memo_id],
        )
        return _normalize_strategy_memo(refreshed[0])

    async def delete_strategy_memo(self, memo_id: str):
        rows = await self.db.execute_read(
            "SELECT id FROM agent.strategy_memos WHERE id = ?",
            [memo_id],
        )
        if not rows:
            raise ValueError(f"策略备忘 {memo_id} 不存在")
        await self.db.execute_write(
            "DELETE FROM agent.strategy_memos WHERE id = ?",
            [memo_id],
        )

    async def create_watch_signal(
        self,
        portfolio_id: str,
        item_input,
        source_run_id: str | None = None,
    ) -> dict:
        await self.get_portfolio(portfolio_id)
        if item_input.status not in WATCH_SIGNAL_STATUSES:
            raise ValueError(f"非法状态: {item_input.status}")

        signal_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        keywords = _normalize_json_safe(item_input.keywords)
        trigger_evidence = _normalize_json_safe(item_input.trigger_evidence)
        await self.db.execute_write(
            """
            INSERT INTO agent.watch_signals (
                id, portfolio_id, stock_code, sector, signal_description,
                check_engine, keywords, if_triggered, cycle_context, status,
                trigger_evidence, source_run_id, created_at, updated_at, triggered_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                signal_id,
                portfolio_id,
                item_input.stock_code,
                item_input.sector,
                item_input.signal_description,
                item_input.check_engine,
                json.dumps(keywords, ensure_ascii=False) if keywords is not None else None,
                item_input.if_triggered,
                item_input.cycle_context,
                item_input.status,
                (
                    json.dumps(trigger_evidence, ensure_ascii=False)
                    if trigger_evidence is not None else None
                ),
                source_run_id,
                now,
                now,
                now if item_input.status == "triggered" else None,
            ],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.watch_signals WHERE id = ?",
            [signal_id],
        )
        return _normalize_watch_signal(rows[0])

    async def list_watch_signals(
        self,
        portfolio_id: str,
        status: str | None = None,
    ) -> list[dict]:
        await self.get_portfolio(portfolio_id)
        if status is not None and status not in WATCH_SIGNAL_STATUSES:
            raise ValueError(f"非法状态: {status}")

        sql = """
            SELECT *
            FROM agent.watch_signals
            WHERE portfolio_id = ?
        """
        params: list = [portfolio_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC, created_at DESC"
        rows = await self.db.execute_read(sql, params)
        return [_normalize_watch_signal(row) for row in rows]

    async def update_watch_signal(self, signal_id: str, updates: dict) -> dict:
        rows = await self.db.execute_read(
            "SELECT * FROM agent.watch_signals WHERE id = ?",
            [signal_id],
        )
        if not rows:
            raise ValueError(f"观察信号 {signal_id} 不存在")

        sets = []
        params = []
        for key in (
            "stock_code",
            "sector",
            "signal_description",
            "check_engine",
            "keywords",
            "if_triggered",
            "cycle_context",
            "status",
            "trigger_evidence",
            "source_run_id",
        ):
            if key not in updates:
                continue
            value = _normalize_json_safe(updates[key])
            if key == "status" and value not in WATCH_SIGNAL_STATUSES:
                raise ValueError(f"非法状态: {value}")
            if key in WATCH_SIGNAL_JSON_FIELDS and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            sets.append(f"{key} = ?")
            params.append(value)

        if "status" in updates:
            sets.append("triggered_at = ?")
            params.append(
                datetime.now().isoformat() if updates["status"] == "triggered" else None
            )

        if sets:
            sets.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(signal_id)
            await self.db.execute_write(
                f"UPDATE agent.watch_signals SET {', '.join(sets)} WHERE id = ?",
                params,
            )

        rows = await self.db.execute_read(
            "SELECT * FROM agent.watch_signals WHERE id = ?",
            [signal_id],
        )
        return _normalize_watch_signal(rows[0])

    async def create_info_digest(
        self,
        portfolio_id: str,
        run_id: str,
        stock_code: str,
        digest_type: str,
        raw_summary,
        structured_summary,
        strategy_relevance: str | None,
        impact_assessment: str,
        missing_sources: list[str] | None = None,
    ) -> dict:
        await self.get_portfolio(portfolio_id)
        digest_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.db.execute_write(
            """
            INSERT INTO agent.info_digests (
                id, portfolio_id, run_id, stock_code, digest_type,
                raw_summary, structured_summary, strategy_relevance,
                impact_assessment, missing_sources, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                digest_id,
                portfolio_id,
                run_id,
                stock_code,
                digest_type,
                json.dumps(_normalize_json_safe(raw_summary), ensure_ascii=False),
                json.dumps(_normalize_json_safe(structured_summary), ensure_ascii=False),
                strategy_relevance,
                impact_assessment,
                (
                    json.dumps(_normalize_json_safe(missing_sources), ensure_ascii=False)
                    if missing_sources is not None else None
                ),
                now,
            ],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.info_digests WHERE id = ?",
            [digest_id],
        )
        return _normalize_info_digest(rows[0])

    async def list_info_digests(
        self,
        portfolio_id: str,
        run_id: str | None = None,
        stock_code: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        await self.get_portfolio(portfolio_id)
        sql = """
            SELECT *
            FROM agent.info_digests
            WHERE portfolio_id = ?
        """
        params: list = [portfolio_id]
        if run_id is not None:
            sql += " AND run_id = ?"
            params.append(run_id)
        if stock_code is not None:
            sql += " AND stock_code = ?"
            params.append(stock_code)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.execute_read(sql, params)
        return [_normalize_info_digest(row) for row in rows]

    # ── Agent State ──────────────────────────────────

    async def get_agent_state(self, portfolio_id: str) -> dict:
        return await get_state(self.db, portfolio_id)

    async def update_agent_state(
        self,
        portfolio_id: str,
        updates: dict,
        source_run_id: str | None = None,
    ) -> dict:
        return await upsert_state(self.db, portfolio_id, updates, source_run_id)

    async def _get_portfolio_config(self, portfolio_id: str) -> dict:
        rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?",
            [portfolio_id],
        )
        if not rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")
        return _normalize_record(rows[0])

    async def _list_timeline_positions(self, portfolio_id: str) -> list[dict]:
        rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.positions
            WHERE portfolio_id = ?
            ORDER BY created_at ASC, entry_date ASC, id ASC
            """,
            [portfolio_id],
        )
        return [_normalize_record(row) for row in rows]

    async def _list_timeline_trades(self, portfolio_id: str) -> list[dict]:
        rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.trades
            WHERE portfolio_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            [portfolio_id],
        )
        return [_normalize_trade_record(row) for row in rows]

    def _resolve_timeline_start_date(self, config: dict, trades: list[dict]) -> date:
        if config.get("sim_start_date"):
            return _coerce_to_date(config["sim_start_date"])
        if trades:
            return _coerce_to_date(trades[0]["created_at"])
        return _coerce_to_date(config["created_at"])

    def _resolve_timeline_end_date(
        self,
        config: dict,
        trades: list[dict],
        start_day: date,
    ) -> date:
        if trades:
            return max(_coerce_to_date(trades[-1]["created_at"]), start_day)
        if config.get("sim_current_date"):
            return max(_coerce_to_date(config["sim_current_date"]), start_day)
        return start_day

    async def _load_price_history(
        self,
        stock_codes: list[str],
        start_day: date,
        end_day: date,
    ) -> dict[str, dict[str, float]]:
        if not stock_codes:
            return {}

        engine = data_module.get_data_engine()
        start_iso = start_day.isoformat()
        end_iso = end_day.isoformat()
        result: dict[str, dict[str, float]] = {}

        for code in sorted(set(stock_codes)):
            store = getattr(engine, "store", None)
            if store is not None and hasattr(store, "get_daily"):
                # Agent timeline/replay/backtest read paths must stay local-only.
                df = await asyncio.to_thread(store.get_daily, code, start_iso, end_iso)
            else:
                df = await asyncio.to_thread(engine.get_daily_history, code, start_iso, end_iso)
            history: dict[str, float] = {}
            if df is not None and not df.empty:
                date_col = "date" if "date" in df.columns else "trade_date" if "trade_date" in df.columns else None
                close_col = "close" if "close" in df.columns else None
                if date_col and close_col:
                    for _, row in df.iterrows():
                        day_key = _coerce_to_date(row[date_col]).isoformat()
                        history[day_key] = float(row[close_col])
            result[code] = history

        return result

    def _rebuild_daily_ledger(
        self,
        config: dict,
        positions: list[dict],
        trades: list[dict],
        price_history: dict[str, dict[str, float]],
        start_day: date,
        end_day: date,
    ) -> dict[str, dict]:
        positions_by_id = {row["id"]: row for row in positions}
        events_by_day: dict[str, list[dict]] = {}
        for trade in trades:
            trade_day = _coerce_to_date(trade["created_at"]).isoformat()
            events_by_day.setdefault(trade_day, []).append(trade)

        cash_balance = float(config["initial_capital"])
        realized_pnl = 0.0
        position_state: dict[str, dict] = {}
        states: dict[str, dict] = {}

        for current_day in _daterange(start_day, end_day):
            day_key = current_day.isoformat()
            for trade in events_by_day.get(day_key, []):
                position_id = trade["position_id"]
                quantity = int(trade["quantity"])
                fee = float(
                    self.validator.calc_fee(
                        trade["action"],
                        float(trade["price"]),
                        quantity,
                        str(trade["stock_code"]),
                    )
                )
                meta = positions_by_id.get(position_id, {})
                state = position_state.setdefault(
                    position_id,
                    {
                        "id": position_id,
                        "stock_code": trade["stock_code"],
                        "stock_name": trade["stock_name"],
                        "holding_type": meta.get("holding_type"),
                        "entry_date": meta.get("entry_date"),
                        "qty": 0,
                        "open_cost_basis": 0.0,
                    },
                )

                if trade["action"] in ("buy", "add"):
                    cash_balance -= float(trade["amount"]) + fee
                    state["qty"] += quantity
                    state["open_cost_basis"] += float(trade["amount"]) + fee
                elif trade["action"] in ("sell", "reduce"):
                    previous_qty = int(state["qty"])
                    if previous_qty <= 0:
                        continue
                    allocated_cost = state["open_cost_basis"] * quantity / previous_qty
                    proceeds = float(trade["amount"]) - fee
                    cash_balance += proceeds
                    state["qty"] = max(previous_qty - quantity, 0)
                    state["open_cost_basis"] = max(state["open_cost_basis"] - allocated_cost, 0.0)
                    realized_pnl += proceeds - allocated_cost
                    if state["qty"] == 0:
                        state["open_cost_basis"] = 0.0

            open_positions = []
            position_value = 0.0
            open_cost_basis = 0.0

            for item in position_state.values():
                if item["qty"] <= 0:
                    continue
                avg_entry_price = (
                    float(item["open_cost_basis"]) / int(item["qty"])
                    if item["qty"] else 0.0
                )
                close_price = _lookup_close_on_or_before(
                    price_history.get(item["stock_code"], {}),
                    current_day,
                    avg_entry_price,
                )
                market_value = close_price * int(item["qty"])
                unrealized_pnl = market_value - float(item["open_cost_basis"])
                open_positions.append(
                    {
                        "id": item["id"],
                        "stock_code": item["stock_code"],
                        "stock_name": item["stock_name"],
                        "holding_type": item.get("holding_type"),
                        "entry_date": item.get("entry_date"),
                        "current_qty": int(item["qty"]),
                        "avg_entry_price": _round_money(avg_entry_price),
                        "cost_basis": _round_money(item["open_cost_basis"]),
                        "close_price": _round_money(close_price),
                        "market_value": _round_money(market_value),
                        "unrealized_pnl": _round_money(unrealized_pnl),
                    }
                )
                position_value += market_value
                open_cost_basis += float(item["open_cost_basis"])

            total_asset_mark_to_market = cash_balance + position_value
            total_asset_realized_only = cash_balance + open_cost_basis
            states[day_key] = {
                "date": day_key,
                "cash_balance": _round_money(cash_balance),
                "position_value": _round_money(position_value),
                "position_cost_basis_open": _round_money(open_cost_basis),
                "realized_pnl": _round_money(realized_pnl),
                "unrealized_pnl": _round_money(position_value - open_cost_basis),
                "total_asset_mark_to_market": _round_money(total_asset_mark_to_market),
                "total_asset_realized_only": _round_money(total_asset_realized_only),
                "positions": open_positions,
            }

        return states

    async def get_equity_timeline(
        self,
        portfolio_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        config = await self._get_portfolio_config(portfolio_id)
        positions = await self._list_timeline_positions(portfolio_id)
        trades = await self._list_timeline_trades(portfolio_id)

        default_start = self._resolve_timeline_start_date(config, trades)
        default_end = self._resolve_timeline_end_date(config, trades, default_start)
        start_day = _coerce_to_date(start_date) if start_date else default_start
        end_day = _coerce_to_date(end_date) if end_date else default_end
        if end_day < start_day:
            raise ValueError("结束日期不能早于开始日期")

        price_history = await self._load_price_history(
            [row["stock_code"] for row in trades],
            start_day,
            end_day,
        )
        states = self._rebuild_daily_ledger(
            config,
            positions,
            trades,
            price_history,
            start_day,
            end_day,
        )

        mark_to_market = []
        realized_only = []
        for day_key in [item.isoformat() for item in _daterange(start_day, end_day)]:
            state = states[day_key]
            mark_to_market.append(
                {
                    "date": day_key,
                    "equity": state["total_asset_mark_to_market"],
                    "cash_balance": state["cash_balance"],
                    "position_value": state["position_value"],
                    "realized_pnl": state["realized_pnl"],
                    "unrealized_pnl": state["unrealized_pnl"],
                }
            )
            realized_only.append(
                {
                    "date": day_key,
                    "equity": state["total_asset_realized_only"],
                    "cash_balance": state["cash_balance"],
                    "position_cost_basis_open": state["position_cost_basis_open"],
                    "realized_pnl": state["realized_pnl"],
                }
            )

        return {
            "portfolio_id": portfolio_id,
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "mark_to_market": mark_to_market,
            "realized_only": realized_only,
        }

    async def get_replay_snapshot(
        self,
        portfolio_id: str,
        replay_date: str,
    ) -> dict:
        config = await self._get_portfolio_config(portfolio_id)
        positions = await self._list_timeline_positions(portfolio_id)
        trades = await self._list_timeline_trades(portfolio_id)
        start_day = self._resolve_timeline_start_date(config, trades)
        replay_day = _coerce_to_date(replay_date)
        if replay_day < start_day:
            raise ValueError("回放日期早于组合起始")

        codes = {row["stock_code"] for row in trades}
        timeline_prices = await self._load_price_history(
            list(codes),
            start_day,
            replay_day + timedelta(days=7),
        )
        states = self._rebuild_daily_ledger(
            config,
            positions,
            trades,
            timeline_prices,
            start_day,
            replay_day,
        )
        state = states[replay_day.isoformat()]

        day_start = f"{replay_day.isoformat()}T00:00:00"
        day_end = f"{(replay_day + timedelta(days=1)).isoformat()}T00:00:00"
        runs = await self.db.execute_read(
            """
            SELECT *
            FROM agent.brain_runs
            WHERE portfolio_id = ?
              AND (
                    (started_at >= ? AND started_at < ?)
                 OR (completed_at >= ? AND completed_at < ?)
              )
            ORDER BY COALESCE(completed_at, started_at) DESC, id DESC
            """,
            [portfolio_id, day_start, day_end, day_start, day_end],
        )
        normalized_runs = [_normalize_brain_run(row) for row in runs]

        plan_rows = await self.db.execute_read(
            """
            SELECT p.*
            FROM agent.trade_plans p
            JOIN agent.brain_runs r
              ON p.source_run_id = r.id
            WHERE r.portfolio_id = ?
              AND (
                    (p.created_at >= ? AND p.created_at < ?)
                 OR (p.updated_at >= ? AND p.updated_at < ?)
              )
            ORDER BY p.updated_at DESC, p.id DESC
            """,
            [portfolio_id, day_start, day_end, day_start, day_end],
        )
        normalized_plans = [_normalize_record(row) for row in plan_rows]

        trade_rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.trades
            WHERE portfolio_id = ?
              AND created_at >= ?
              AND created_at < ?
            ORDER BY created_at DESC, id DESC
            """,
            [portfolio_id, day_start, day_end],
        )
        normalized_trades = [_normalize_trade_record(row) for row in trade_rows]

        review_rows = await self.db.execute_read(
            """
            SELECT rr.*, br.portfolio_id
            FROM agent.review_records rr
            JOIN agent.brain_runs br
              ON rr.brain_run_id = br.id
            WHERE br.portfolio_id = ?
              AND rr.review_date = ?
            ORDER BY rr.created_at DESC, rr.id DESC
            """,
            [portfolio_id, replay_day.isoformat()],
        )
        normalized_reviews = [_normalize_record(row) for row in review_rows]

        reflection_rows = await self._safe_reflection_query(
            """
            SELECT *
            FROM agent.daily_reviews
            WHERE review_date = ?
            ORDER BY created_at DESC, id DESC
            """,
            [replay_day.isoformat()],
        )
        reflection_items = [
            _build_daily_reflection_item(_normalize_record(row))
            for row in reflection_rows
        ]

        trade_models = [_build_trade_read_model(row) for row in normalized_trades]
        plan_models = [_build_plan_read_model(row) for row in normalized_plans]
        next_day_move_pct = None
        next_day_price = None
        next_day_date = None
        target_code = None
        if normalized_trades:
            target_code = normalized_trades[0]["stock_code"]
        elif state["positions"]:
            target_code = state["positions"][0]["stock_code"]
        if target_code:
            current_close = _lookup_close_on_or_before(
                timeline_prices.get(target_code, {}),
                replay_day,
                state["positions"][0]["avg_entry_price"] if state["positions"] else 0.0,
            )
            next_close = _lookup_next_close_after(timeline_prices.get(target_code, {}), replay_day)
            if next_close and current_close:
                next_day_date, next_day_price = next_close
                next_day_move_pct = _round_money((next_day_price - current_close) / current_close * 100)

        what_ai_knew = {
            "run_ids": [row["id"] for row in normalized_runs],
            "thinking_process": [row.get("thinking_process") for row in normalized_runs if row.get("thinking_process")],
            "state_before": [row.get("state_before") for row in normalized_runs if row.get("state_before")],
            "state_after": [row.get("state_after") for row in normalized_runs if row.get("state_after")],
            "plan_reasoning": [row.get("reasoning") for row in normalized_plans if row.get("reasoning")],
            "trade_theses": [row.get("thesis") for row in normalized_trades if row.get("thesis")],
            "trade_reasons": [row.get("reason") for row in normalized_trades if row.get("reason")],
            "trade_data_basis": [row.get("data_basis") for row in normalized_trades if row.get("data_basis")],
        }
        what_happened = {
            "trade_count": len(normalized_trades),
            "review_statuses": [row.get("status") for row in normalized_reviews if row.get("status")],
            "total_asset_mark_to_market_close": state["total_asset_mark_to_market"],
            "total_asset_realized_only_close": state["total_asset_realized_only"],
            "realized_pnl": state["realized_pnl"],
            "unrealized_pnl": state["unrealized_pnl"],
            "next_day_move_pct": next_day_move_pct,
            "next_day_price": next_day_price,
            "next_day_date": next_day_date,
            "next_day_move_stock_code": target_code,
        }

        return {
            "portfolio_id": portfolio_id,
            "date": replay_day.isoformat(),
            "account": {
                "cash_balance": state["cash_balance"],
                "position_value_mark_to_market": state["position_value"],
                "position_cost_basis_open": state["position_cost_basis_open"],
                "total_asset_mark_to_market": state["total_asset_mark_to_market"],
                "total_asset_realized_only": state["total_asset_realized_only"],
                "realized_pnl": state["realized_pnl"],
                "unrealized_pnl": state["unrealized_pnl"],
            },
            "positions": state["positions"],
            "brain_runs": normalized_runs,
            "plans": plan_models,
            "trades": trade_models,
            "reviews": normalized_reviews,
            "reflections": reflection_items,
            "what_ai_knew": what_ai_knew,
            "what_happened": what_happened,
        }

    async def get_replay_learning(
        self,
        portfolio_id: str,
        replay_date: str,
    ) -> dict:
        replay = await self.get_replay_snapshot(portfolio_id, replay_date)
        what_ai_knew = replay.get("what_ai_knew") or {}
        what_happened = replay.get("what_happened") or {}
        reviews = replay.get("reviews") or []
        trade_theses = what_ai_knew.get("trade_theses") or []
        review_statuses = what_happened.get("review_statuses") or []
        next_day_move_pct = what_happened.get("next_day_move_pct")

        would_change = False
        action_bias = "hold_course"
        rationale = "当时的动作和事后结果基本一致，优先保留原计划。"

        if "loss" in review_statuses:
            would_change = True
            action_bias = "tighten_confirmation"
            rationale = "事后复盘出现亏损，下一次应先提高确认门槛。"
        elif isinstance(next_day_move_pct, (int, float)) and next_day_move_pct < 0:
            would_change = True
            action_bias = "reduce_earlier"
            rationale = "次日延续走弱，若重来一次应更早收缩仓位。"
        elif isinstance(next_day_move_pct, (int, float)) and next_day_move_pct > 0:
            action_bias = "hold_course"
            rationale = "次日走势没有否定原判断，本次动作更适合保留。"

        thesis_text = trade_theses[0] if trade_theses else "当日动作"
        lesson_summary = f"{thesis_text}；复盘结论：{rationale}"

        return {
            "portfolio_id": replay["portfolio_id"],
            "date": replay["date"],
            "what_ai_knew": what_ai_knew,
            "what_happened": what_happened,
            "counterfactual": {
                "would_change": would_change,
                "action_bias": action_bias,
                "rationale": rationale,
            },
            "lesson_summary": lesson_summary,
            "reviews": reviews,
        }

    # ── Ledger Read Model ────────────────────────────

    async def _list_ledger_plans(self, portfolio_id: str, status: str) -> list[dict]:
        """读取与指定 portfolio 关联的 agent plans。

        当前 trade_plans 没有 portfolio_id，因此 read model 通过 source_run_id
        回连 brain_runs 做归属判定，避免串入其他组合的 agent 计划。
        """
        return await self.db.execute_read(
            """
            SELECT p.*
            FROM agent.trade_plans p
            JOIN agent.brain_runs r
              ON p.source_run_id = r.id
            WHERE p.status = ?
              AND p.source_type = 'agent'
              AND r.portfolio_id = ?
            ORDER BY p.updated_at DESC
            """,
            [status, portfolio_id],
        )

    async def get_ledger_overview(self, portfolio_id: str) -> dict:
        portfolio = await self.get_portfolio(portfolio_id)
        open_positions = await self.get_positions(portfolio_id, status="open")
        recent_trades = await self.get_trades(portfolio_id, limit=20)
        pending_plans = await self._list_ledger_plans(portfolio_id, status="pending")
        executing_plans = await self._list_ledger_plans(portfolio_id, status="executing")

        latest_strategies: dict[str, dict] = {}
        for position in open_positions:
            strategy_rows = await self.db.execute_read(
                """
                SELECT *
                FROM agent.position_strategies
                WHERE position_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                [position["id"]],
            )
            latest_strategies[position["id"]] = (
                _normalize_position_strategy(strategy_rows[0]) if strategy_rows else None
            )

        position_models = []
        for position in open_positions:
            model = _build_position_read_model(position)
            model["latest_strategy"] = _build_strategy_summary(latest_strategies[position["id"]])
            position_models.append(model)
        trade_models = [_build_trade_read_model(trade) for trade in recent_trades]
        pending_models = [_build_plan_read_model(plan) for plan in pending_plans]
        executing_models = [_build_plan_read_model(plan) for plan in executing_plans]
        position_value = round(sum(item["market_value"] for item in position_models), 2)

        for item in position_models:
            item["position_pct"] = round(
                (item["market_value"] / position_value) if position_value else 0.0,
                4,
            )
            status_signal, status_reason = _build_position_status_signal(
                item,
                item.get("latest_strategy"),
            )
            item["status_signal"] = status_signal
            item["status_reason"] = status_reason

        return {
            "portfolio_id": portfolio_id,
            "asset_summary": {
                "initial_capital": portfolio["config"]["initial_capital"],
                "cash_balance": portfolio["cash_balance"],
                "position_value": position_value,
                "total_asset": portfolio["total_asset"],
                "total_pnl": portfolio["total_pnl"],
                "total_pnl_pct": portfolio["total_pnl_pct"],
                "open_position_count": len(position_models),
                "recent_trade_count": len(trade_models),
                "pending_plan_count": len(pending_models),
                "executing_plan_count": len(executing_models),
            },
            "open_positions": position_models,
            "recent_trades": trade_models,
            "active_plans": {
                "pending": pending_models,
                "executing": executing_models,
            },
        }

    # ── Review / Memory Read Models ──────────────────

    async def list_review_records(
        self,
        portfolio_id: str,
        days: int = 30,
        review_type: str | None = None,
    ) -> list[dict]:
        await self.get_portfolio(portfolio_id)

        cutoff_date = (date.today() - timedelta(days=max(days - 1, 0))).isoformat()
        sql = """
            SELECT rr.*, br.portfolio_id
            FROM agent.review_records rr
            JOIN agent.brain_runs br
              ON rr.brain_run_id = br.id
            WHERE br.portfolio_id = ?
              AND rr.review_date >= ?
        """
        params: list = [portfolio_id, cutoff_date]
        if review_type:
            sql += " AND rr.review_type = ?"
            params.append(review_type)
        sql += " ORDER BY rr.review_date DESC, rr.created_at DESC"

        rows = await self.db.execute_read(sql, params)
        return [_normalize_record(row) for row in rows]

    async def get_review_stats(self, portfolio_id: str, days: int = 30) -> dict:
        records = await self.list_review_records(portfolio_id, days=days)
        total_reviews = len(records)
        win_count = sum(1 for row in records if row.get("status") == "win")
        loss_count = sum(1 for row in records if row.get("status") == "loss")
        holding_count = sum(1 for row in records if row.get("status") == "holding")
        pnl_values = [float(row["pnl_pct"]) for row in records if row.get("pnl_pct") is not None]
        total_pnl_pct = round(sum(pnl_values), 4) if pnl_values else 0.0
        avg_pnl_pct = round(total_pnl_pct / len(pnl_values), 4) if pnl_values else 0.0
        win_rate = round((win_count / total_reviews), 4) if total_reviews else 0.0

        best_review = max(records, key=lambda row: row.get("pnl_pct", float("-inf")), default=None)
        worst_review = min(records, key=lambda row: row.get("pnl_pct", float("inf")), default=None)

        return {
            "portfolio_id": portfolio_id,
            "days": days,
            "total_reviews": total_reviews,
            "win_count": win_count,
            "loss_count": loss_count,
            "holding_count": holding_count,
            "win_rate": win_rate,
            "total_pnl_pct": total_pnl_pct,
            "avg_pnl_pct": avg_pnl_pct,
            "best_review": best_review,
            "worst_review": worst_review,
        }

    async def list_weekly_summaries(self, limit: int = 10) -> list[dict]:
        rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.weekly_summaries
            ORDER BY week_start DESC, created_at DESC
            LIMIT ?
            """,
            [limit],
        )
        return [_normalize_record(row) for row in rows]

    async def list_memories(self, status: str = "active", portfolio_id: str | None = None) -> list[dict]:
        # 有 portfolio_id 时，通过 source_run_id → brain_runs 关联过滤
        if portfolio_id:
            where_clauses = ["br.portfolio_id = ?"]
            params: list = [portfolio_id]
            if status != "all":
                where_clauses.append("m.status = ?")
                params.append(status)
            rows = await self.db.execute_read(
                f"""
                SELECT m.*
                FROM agent.agent_memories m
                JOIN agent.brain_runs br ON m.source_run_id = br.id
                WHERE {' AND '.join(where_clauses)}
                ORDER BY m.created_at DESC
                """,
                params,
            )
        elif status == "all":
            rows = await self.db.execute_read(
                """
                SELECT *
                FROM agent.agent_memories
                ORDER BY created_at DESC
                """
            )
        else:
            rows = await self.db.execute_read(
                """
                SELECT *
                FROM agent.agent_memories
                WHERE status = ?
                ORDER BY created_at DESC
                """,
                [status],
            )
        return [_normalize_record(row) for row in rows]

    async def list_strategy_history(self, portfolio_id: str, limit: int = 20) -> list[dict]:
        await self.get_portfolio(portfolio_id)
        rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.brain_runs
            WHERE portfolio_id = ? AND status = 'completed'
            ORDER BY completed_at DESC, started_at DESC
            LIMIT ?
            """,
            [portfolio_id, limit],
        )
        normalized_runs = [_normalize_brain_run(row) for row in rows]
        return [_build_strategy_history_item(row) for row in normalized_runs]

    async def list_reflections(self, limit: int = 20, portfolio_id: str | None = None) -> list[dict]:
        if portfolio_id:
            # 按 portfolio 过滤：daily_reviews 通过 brain_run_id 关联
            try:
                daily_rows = await self._safe_reflection_query(
                    """
                    SELECT dr.*
                    FROM agent.daily_reviews dr
                    JOIN agent.brain_runs br ON dr.brain_run_id = br.id
                    WHERE br.portfolio_id = ?
                    ORDER BY dr.review_date DESC, dr.created_at DESC
                    LIMIT ?
                    """,
                    [portfolio_id, limit],
                )
            except Exception as exc:
                logger.warning(f"daily_reviews portfolio 过滤查询失败: {exc}")
                daily_rows = []
            # weekly_reflections 无 portfolio 关联，按 portfolio 过滤时跳过
            weekly_rows = []
        else:
            daily_rows = await self._safe_reflection_query(
                """
                SELECT *
                FROM agent.daily_reviews
                ORDER BY review_date DESC, created_at DESC
                LIMIT ?
                """,
                [limit],
            )
            weekly_rows = await self._safe_reflection_query(
                """
                SELECT *
                FROM agent.weekly_reflections
                ORDER BY week_end DESC, created_at DESC
                LIMIT ?
                """,
                [limit],
            )
        items = (
            [_build_daily_reflection_item(_normalize_record(row)) for row in daily_rows]
            + [_build_weekly_reflection_item(_normalize_record(row)) for row in weekly_rows]
        )
        items.sort(key=lambda item: (item["date"], item.get("created_at") or ""), reverse=True)
        return items[:limit]

    async def _safe_reflection_query(self, sql: str, params: list) -> list[dict]:
        try:
            return await self.db.execute_read(sql, params)
        except Exception as exc:
            err_msg = str(exc).lower()
            if "does not exist" in err_msg or "not found" in err_msg or "no such" in err_msg:
                logger.debug(f"反思查询安全降级 (表/列不存在): {exc}")
                return []
            raise

    # ── BrainRuns CRUD ─────────────────────────────────

    async def create_brain_run(self, portfolio_id: str, run_type: str = "scheduled") -> dict:
        """创建运行记录"""
        # 先清理可能存在的过期 running 记录
        await self._fail_stale_brain_runs()
        run_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.db.execute_write(
            """INSERT INTO agent.brain_runs (id, portfolio_id, run_type, status, started_at)
               VALUES (?, ?, ?, 'running', ?)""",
            [run_id, portfolio_id, run_type, now],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_runs WHERE id = ?", [run_id]
        )
        return _normalize_brain_run(rows[0])

    async def get_brain_run(self, run_id: str) -> dict:
        """获取运行记录"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_runs WHERE id = ?", [run_id]
        )
        if not rows:
            raise ValueError(f"运行记录 {run_id} 不存在")
        return _normalize_brain_run(rows[0])

    async def update_brain_run(self, run_id: str, updates: dict):
        """更新运行记录"""
        await self.get_brain_run(run_id)
        sets = []
        params = []
        for key in ("status", "current_step", "candidates", "analysis_results", "decisions",
                     "plan_ids", "trade_ids", "thinking_process",
                     "state_before", "state_after", "execution_summary",
                     "info_digest_ids", "triggered_signal_ids",
                     "error_message", "llm_tokens_used"):
            if key in updates:
                val = _normalize_json_safe(updates[key])
                if isinstance(val, (list, dict)):
                    val = json.dumps(val, ensure_ascii=False)
                sets.append(f"{key} = ?")
                params.append(val)
        if "status" in updates and updates["status"] in ("completed", "failed"):
            sets.append("completed_at = ?")
            params.append(datetime.now().isoformat())
        if sets:
            sql = f"UPDATE agent.brain_runs SET {', '.join(sets)} WHERE id = ?"
            params.append(run_id)
            await self.db.execute_write(sql, params)

    async def list_brain_runs(self, portfolio_id: str, limit: int = 50) -> list[dict]:
        """运行记录列表"""
        await self._fail_stale_brain_runs()
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_runs WHERE portfolio_id = ? ORDER BY started_at DESC LIMIT ?",
            [portfolio_id, limit],
        )
        return [_normalize_brain_run(row) for row in rows]

    async def _fail_stale_brain_runs(self, timeout_minutes: int = 10):
        """将超过 timeout_minutes 仍为 running 的记录标记为 failed"""
        cutoff = (datetime.now() - timedelta(minutes=timeout_minutes)).isoformat()
        stale_rows = await self.db.execute_read(
            "SELECT id FROM agent.brain_runs WHERE status = 'running' AND started_at < ?",
            [cutoff],
        )
        if not stale_rows:
            return
        now = datetime.now().isoformat()
        for row in stale_rows:
            run_id = row["id"]
            logger.warning(f"🧠 自动标记过期 brain_run 为 failed: {run_id}")
            await self.db.execute_write(
                "UPDATE agent.brain_runs SET status = 'failed', current_step = NULL, "
                "error_message = '运行超时（超过10分钟未完成）', completed_at = ? WHERE id = ?",
                [now, run_id],
            )

    # ── BrainConfig CRUD ───────────────────────────────

    async def get_brain_config(self) -> dict:
        """获取 Brain 配置"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_config WHERE id = 'default'"
        )
        if not rows:
            return {"enable_debate": False, "max_candidates": 30, "quant_top_n": 20,
                    "max_position_count": 10, "single_position_pct": 0.15, "schedule_time": "15:30"}
        return rows[0]

    async def update_brain_config(self, updates: dict):
        """更新 Brain 配置"""
        sets = []
        params = []
        for key in ("enable_debate", "max_candidates", "quant_top_n",
                     "max_position_count", "single_position_pct", "schedule_time"):
            if key in updates:
                sets.append(f"{key} = ?")
                params.append(updates[key])
        if sets:
            sets.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            sql = f"UPDATE agent.brain_config SET {', '.join(sets)} WHERE id = 'default'"
            await self.db.execute_write(sql, params)
