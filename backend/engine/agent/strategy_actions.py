"""Agent strategy action contract and rehydration service."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime

from engine.agent.db import AgentDB
from engine.agent.memory import MemoryManager
from engine.agent.models import AdoptStrategyRequest, RejectStrategyRequest, TradeInput, TradePlanInput
from engine.agent.service import AgentService


class StrategyActionService:
    """Canonical adopt/reject write path with stable UI rehydration fields."""

    def __init__(
        self,
        db: AgentDB,
        agent_service: AgentService,
        memory_mgr: MemoryManager,
    ):
        self.db = db
        self.agent_service = agent_service
        self.memory_mgr = memory_mgr

    async def list_actions(self, session_id: str) -> list[dict]:
        await self._ensure_actions_table()
        rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.strategy_actions
            WHERE session_id = ?
            ORDER BY created_at DESC, updated_at DESC
            """,
            [session_id],
        )
        return [await self._normalize_action_row(row) for row in rows]

    async def adopt_strategy(self, payload: dict | AdoptStrategyRequest) -> dict:
        await self._ensure_actions_table()
        request = payload if isinstance(payload, AdoptStrategyRequest) else AdoptStrategyRequest(**payload)

        existing = await self._get_existing_action(
            request.session_id,
            request.message_id,
            request.strategy_key,
            request.plan.stock_code,
        )
        if existing:
            return existing

        plan = request.plan
        position = await self._find_open_position(request.portfolio_id, plan.stock_code)
        portfolio = await self.agent_service.get_portfolio(request.portfolio_id)
        trade_action, quantity = self._derive_trade_action_and_quantity(plan, position, portfolio)
        price = self._resolve_price(plan)

        created_plan = await self.agent_service.create_plan(
            TradePlanInput(
                stock_code=plan.stock_code,
                stock_name=plan.stock_name,
                current_price=plan.current_price,
                direction=plan.direction,
                entry_price=plan.entry_price,
                entry_method=plan.entry_method,
                position_pct=plan.position_pct,
                take_profit=plan.take_profit,
                take_profit_method=plan.take_profit_method,
                stop_loss=plan.stop_loss,
                stop_loss_method=plan.stop_loss_method,
                reasoning=plan.reasoning,
                risk_note=plan.risk_note,
                invalidation=plan.invalidation,
                valid_until=plan.valid_until,
                source_type="agent",
                source_conversation_id=request.session_id,
            ),
            source_run_id=request.source_run_id,
        )
        await self.agent_service.update_plan(created_plan["id"], {"status": "executing"})

        trade_result = await self.agent_service.execute_trade(
            request.portfolio_id,
            TradeInput(
                action=trade_action,
                stock_code=plan.stock_code,
                price=price,
                quantity=quantity,
                holding_type=plan.holding_type if trade_action == "buy" else None,
                reason=plan.reasoning,
                thesis=plan.reasoning,
                data_basis=[plan.reasoning],
                risk_note=plan.risk_note or "",
                invalidation=plan.invalidation or "",
                triggered_by="agent",
            ),
            trade_date=date.today().isoformat(),
            position_id=position["id"] if position else None,
            stock_name=plan.stock_name,
            source_run_id=request.source_run_id,
            source_plan_id=created_plan["id"],
        )

        linked_position = trade_result["position"]
        linked_trade = trade_result["trade"]
        linked_strategy = None
        if linked_position:
            linked_strategy = await self.agent_service.create_strategy(
                request.portfolio_id,
                linked_position["id"],
                {
                    "take_profit": plan.take_profit,
                    "stop_loss": plan.stop_loss,
                    "reasoning": plan.reasoning,
                    "details": {
                        "origin": "agent_adopt",
                        "strategy_key": request.strategy_key,
                        "session_id": request.session_id,
                        "message_id": request.message_id,
                    },
                },
                source_run_id=request.source_run_id,
            )
            linked_trade = await self.agent_service.update_trade_sources(
                linked_trade["id"],
                source_strategy_id=linked_strategy["id"],
                source_strategy_version=linked_strategy["version"],
            )

        return await self._insert_action(
            portfolio_id=request.portfolio_id,
            session_id=request.session_id,
            message_id=request.message_id,
            strategy_key=request.strategy_key,
            stock_code=plan.stock_code,
            stock_name=plan.stock_name,
            decision="adopted",
            trade_action=trade_action,
            reason=None,
            source_run_id=request.source_run_id,
            plan_id=created_plan["id"],
            trade_id=linked_trade["id"] if linked_trade else None,
            position_id=linked_position["id"] if linked_position else None,
            strategy_id=linked_strategy["id"] if linked_strategy else None,
            strategy_version=linked_strategy["version"] if linked_strategy else None,
            plan_snapshot=plan.model_dump(),
        )

    async def reject_strategy(self, payload: dict | RejectStrategyRequest) -> dict:
        await self._ensure_actions_table()
        request = payload if isinstance(payload, RejectStrategyRequest) else RejectStrategyRequest(**payload)

        existing = await self._get_existing_action(
            request.session_id,
            request.message_id,
            request.strategy_key,
            request.plan.stock_code,
        )
        if existing:
            return existing

        action = await self._insert_action(
            portfolio_id=request.portfolio_id,
            session_id=request.session_id,
            message_id=request.message_id,
            strategy_key=request.strategy_key,
            stock_code=request.plan.stock_code,
            stock_name=request.plan.stock_name,
            decision="rejected",
            trade_action=None,
            reason=request.reason,
            source_run_id=request.source_run_id,
            plan_id=None,
            trade_id=None,
            position_id=None,
            strategy_id=None,
            strategy_version=None,
            plan_snapshot=request.plan.model_dump(),
        )

        if request.reason:
            await self.memory_mgr.add_rules(
                [
                    {
                        "rule_text": f"{request.plan.stock_name}: {request.reason}",
                        "category": "strategy_feedback",
                    }
                ],
                source_run_id=request.source_run_id,
            )

        return action

    async def _ensure_actions_table(self):
        await self.db.execute_write(
            """
            CREATE TABLE IF NOT EXISTS agent.strategy_actions (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                session_id VARCHAR NOT NULL,
                message_id VARCHAR NOT NULL,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR,
                decision VARCHAR NOT NULL,
                trade_action VARCHAR,
                reason TEXT,
                source_run_id VARCHAR,
                plan_id VARCHAR,
                trade_id VARCHAR,
                position_id VARCHAR,
                strategy_id VARCHAR,
                strategy_version INTEGER,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now(),
                UNIQUE (session_id, message_id, stock_code)
            )
            """
        )
        for sql in (
            "ALTER TABLE agent.strategy_actions ADD COLUMN IF NOT EXISTS strategy_key VARCHAR",
            "ALTER TABLE agent.strategy_actions ADD COLUMN IF NOT EXISTS status VARCHAR",
            "ALTER TABLE agent.strategy_actions ADD COLUMN IF NOT EXISTS plan_snapshot JSON",
        ):
            await self.db.execute_write(sql)

    async def _get_existing_action(
        self,
        session_id: str,
        message_id: str,
        strategy_key: str,
        stock_code: str,
    ) -> dict | None:
        rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.strategy_actions
            WHERE session_id = ? AND message_id = ?
            ORDER BY created_at DESC
            """,
            [session_id, message_id],
        )
        for row in rows:
            row_strategy_key = row.get("strategy_key")
            if row_strategy_key and row_strategy_key == strategy_key:
                return await self._normalize_action_row(row)
            if row.get("stock_code") == stock_code:
                return await self._normalize_action_row(row)
        return None

    async def _find_open_position(self, portfolio_id: str, stock_code: str) -> dict | None:
        rows = await self.db.execute_read(
            """
            SELECT *
            FROM agent.positions
            WHERE portfolio_id = ? AND stock_code = ? AND status = 'open'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [portfolio_id, stock_code],
        )
        return rows[0] if rows else None

    def _derive_trade_action_and_quantity(
        self,
        plan,
        position: dict | None,
        portfolio: dict,
    ) -> tuple[str, int]:
        if plan.direction == "buy":
            action = "add" if position else "buy"
            quantity = self._derive_buy_quantity(plan, float(portfolio["total_asset"]))
            return action, quantity

        if not position:
            raise ValueError(f"股票 {plan.stock_code} 没有可卖出的持仓")

        quantity = self._derive_sell_quantity(plan, int(position["current_qty"]))
        action = "sell" if quantity >= int(position["current_qty"]) else "reduce"
        return action, quantity

    def _derive_buy_quantity(self, plan, total_asset: float) -> int:
        price = self._resolve_price(plan)
        position_pct = plan.position_pct if plan.position_pct is not None else 0.1
        target_amount = total_asset * position_pct
        board_lots = int(target_amount / price // 100)
        return max(board_lots, 1) * 100

    def _derive_sell_quantity(self, plan, current_qty: int) -> int:
        if plan.position_pct is None or plan.position_pct >= 1:
            return current_qty
        lots = int(current_qty * plan.position_pct // 100)
        quantity = max(lots, 1) * 100
        return min(quantity, current_qty)

    def _resolve_price(self, plan) -> float:
        price = plan.entry_price or plan.current_price
        if price is None or price <= 0:
            raise ValueError("策略卡缺少有效价格")
        return float(price)

    async def _insert_action(
        self,
        *,
        portfolio_id: str,
        session_id: str,
        message_id: str,
        strategy_key: str,
        stock_code: str,
        stock_name: str | None,
        decision: str,
        trade_action: str | None,
        reason: str | None,
        source_run_id: str | None,
        plan_id: str | None,
        trade_id: str | None,
        position_id: str | None,
        strategy_id: str | None,
        strategy_version: int | None,
        plan_snapshot: dict,
    ) -> dict:
        action_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        try:
            await self.db.execute_write(
                """
                INSERT INTO agent.strategy_actions (
                    id, portfolio_id, session_id, message_id, strategy_key, stock_code, stock_name,
                    decision, status, trade_action, reason, source_run_id, plan_id, trade_id,
                    position_id, strategy_id, strategy_version, plan_snapshot, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    action_id,
                    portfolio_id,
                    session_id,
                    message_id,
                    strategy_key,
                    stock_code,
                    stock_name,
                    decision,
                    decision,
                    trade_action,
                    reason,
                    source_run_id,
                    plan_id,
                    trade_id,
                    position_id,
                    strategy_id,
                    strategy_version,
                    json.dumps(plan_snapshot, ensure_ascii=False),
                    now,
                    now,
                ],
            )
        except Exception:
            existing = await self._get_existing_action(session_id, message_id, strategy_key, stock_code)
            if existing:
                return existing
            raise

        row = (
            await self.db.execute_read(
                "SELECT * FROM agent.strategy_actions WHERE id = ?",
                [action_id],
            )
        )[0]
        return await self._normalize_action_row(row)

    async def _normalize_action_row(self, row: dict) -> dict:
        normalized = dict(row)
        plan_snapshot = self._decode_plan_snapshot(normalized.get("plan_snapshot"))
        strategy_key = normalized.get("strategy_key")
        if not strategy_key and plan_snapshot:
            strategy_key = build_strategy_key(plan_snapshot)
        if not strategy_key and normalized.get("plan_id"):
            plan_rows = await self.db.execute_read(
                "SELECT * FROM agent.trade_plans WHERE id = ?",
                [normalized["plan_id"]],
            )
            if plan_rows:
                strategy_key = build_strategy_key(plan_rows[0])

        normalized["strategy_key"] = strategy_key
        normalized["status"] = normalized.get("status") or normalized.get("decision")
        normalized["plan_snapshot"] = plan_snapshot
        return normalized

    def _decode_plan_snapshot(self, payload):
        if payload is None or isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None
        return None


def build_strategy_key(plan: dict) -> str:
    def numeric_part(value):
        if value is None:
            return ""
        return f"{float(value):.4f}"

    return "|".join(
        [
            str(plan["stock_code"]).strip().upper(),
            str(plan["direction"]),
            numeric_part(plan.get("entry_price")),
            numeric_part(plan.get("take_profit")),
            numeric_part(plan.get("stop_loss")),
            str(plan.get("valid_until") or "").strip(),
        ]
    )
