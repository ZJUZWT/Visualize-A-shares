"""
AgentService — Main Agent 业务逻辑层
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from loguru import logger

from engine.agent.db import AgentDB
from engine.agent.models import TradeInput
from engine.agent.validator import TradeValidator


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
                    portfolio_id, pos_id, trade_input, exec_price, amount, name, now
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
                    portfolio_id, position_id, trade_input, exec_price, amount, name, now
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
                    portfolio_id, position_id, trade_input, exec_price, amount, name, now
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
    ) -> tuple[str, list]:
        """生成 INSERT trade 的 SQL + params"""
        trade_id = str(uuid.uuid4())
        return (
            """INSERT INTO agent.trades
               (id, portfolio_id, position_id, action, stock_code, stock_name,
                price, quantity, amount, reason, thesis, data_basis,
                risk_note, invalidation, triggered_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [trade_id, portfolio_id, position_id, ti.action, ti.stock_code,
             stock_name, exec_price, ti.quantity, round(amount, 2),
             ti.reason, ti.thesis, json.dumps(ti.data_basis, ensure_ascii=False),
             ti.risk_note, ti.invalidation, ti.triggered_by, now],
        )

    # ── Strategy CRUD ─────────────────────────────────

    async def create_strategy(
        self, portfolio_id: str, position_id: str, strategy_input: dict
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
                reasoning, details, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [strategy_id, position_id, position["holding_type"],
             strategy_input.get("take_profit"), strategy_input.get("stop_loss"),
             strategy_input.get("reasoning", ""),
             json.dumps(details, ensure_ascii=False) if details else None,
             new_version, now, now],
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
