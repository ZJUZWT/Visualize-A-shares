"""
AgentService — Main Agent 业务逻辑层
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta

from loguru import logger

from engine.agent.db import AgentDB
from engine.agent.models import TradeInput
from engine.agent.state import get_state, upsert_state
from engine.agent.validator import TradeValidator


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
)


def _decode_json_value(value):
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _normalize_json_safe(value):
    if isinstance(value, dict):
        return {key: _normalize_json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_safe(item) for item in value]
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
    for field in ("review_date", "week_start", "week_end"):
        value = normalized.get(field)
        if isinstance(value, str) and "T" in value:
            normalized[field] = value.split("T", 1)[0]
    return normalized


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
        "position_pct": plan["position_pct"],
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
                entry_price, entry_method, position_pct,
                take_profit, take_profit_method, stop_loss, stop_loss_method,
                reasoning, risk_note, invalidation, valid_until,
                status, source_type, source_conversation_id, source_run_id,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
            [plan_id, plan_input.stock_code, plan_input.stock_name,
             plan_input.current_price, plan_input.direction,
             plan_input.entry_price, plan_input.entry_method, plan_input.position_pct,
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

    async def add_watchlist(self, item_input) -> dict:
        """添加关注"""
        item_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.db.execute_write(
            """INSERT INTO agent.watchlist (id, stock_code, stock_name, reason, added_by, created_at)
               VALUES (?, ?, ?, ?, 'manual', ?)""",
            [item_id, item_input.stock_code, item_input.stock_name,
             item_input.reason, now],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.watchlist WHERE id = ?", [item_id]
        )
        return rows[0]

    async def list_watchlist(self) -> list[dict]:
        """关注列表"""
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

        position_models = [_build_position_read_model(position) for position in open_positions]
        trade_models = [_build_trade_read_model(trade) for trade in recent_trades]
        pending_models = [_build_plan_read_model(plan) for plan in pending_plans]
        executing_models = [_build_plan_read_model(plan) for plan in executing_plans]
        position_value = round(sum(item["market_value"] for item in position_models), 2)

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

    async def list_memories(self, status: str = "active") -> list[dict]:
        if status == "all":
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

    async def list_reflections(self, limit: int = 20) -> list[dict]:
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
            if "does not exist" in str(exc):
                return []
            raise

    # ── BrainRuns CRUD ─────────────────────────────────

    async def create_brain_run(self, portfolio_id: str, run_type: str = "scheduled") -> dict:
        """创建运行记录"""
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
        for key in ("status", "candidates", "analysis_results", "decisions",
                     "plan_ids", "trade_ids", "thinking_process",
                     "state_before", "state_after", "execution_summary",
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
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_runs WHERE portfolio_id = ? ORDER BY started_at DESC LIMIT ?",
            [portfolio_id, limit],
        )
        return [_normalize_brain_run(row) for row in rows]

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
