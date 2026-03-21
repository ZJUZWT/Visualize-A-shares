"""
Execution ledger 协调器
"""
from __future__ import annotations

from datetime import date

from loguru import logger

from engine.agent.models import TradeInput, TradePlanInput


class ExecutionCoordinator:
    """唯一的账本写入口：plan / trade / strategy"""

    def __init__(self, portfolio_id: str, service):
        self.portfolio_id = portfolio_id
        self.service = service

    async def create_plan_from_decision(self, run_id: str, decision: dict) -> dict:
        action = decision.get("action", "")
        direction = "buy" if action in ("buy", "add") else "sell"
        return await self.service.create_plan(
            TradePlanInput(
                stock_code=decision["stock_code"],
                stock_name=decision.get("stock_name", decision["stock_code"]),
                direction=direction,
                entry_price=decision.get("price"),
                position_pct=decision.get("position_pct"),
                take_profit=decision.get("take_profit"),
                stop_loss=decision.get("stop_loss"),
                stop_loss_method=decision.get("stop_loss_method"),
                take_profit_method=decision.get("take_profit_method"),
                reasoning=decision.get("reasoning", "Agent 自动决策"),
                risk_note=decision.get("risk_note"),
                invalidation=decision.get("invalidation"),
                source_type="agent",
            ),
            source_run_id=run_id,
        )

    async def execute_plan(self, run_id: str, plan_id: str, decision: dict) -> dict:
        action = decision.get("action", "")
        position_id = None
        holding_type = decision.get("holding_type", "mid_term")

        if action in ("sell", "reduce", "add"):
            positions = await self.service.get_positions(self.portfolio_id, "open")
            for position in positions:
                if position["stock_code"] == decision["stock_code"]:
                    position_id = position["id"]
                    holding_type = position.get("holding_type", holding_type)
                    break

        if action in ("sell", "reduce") and not position_id:
            logger.warning(f"🧾 跳过 {action} {decision['stock_code']}：未找到持仓")
            return {
                "plan_id": plan_id,
                "trade_id": None,
                "strategy_id": None,
                "position_id": None,
                "skipped": True,
            }

        trade_input = TradeInput(
            action=action,
            stock_code=decision["stock_code"],
            price=decision.get("price", 0),
            quantity=decision.get("quantity", 100),
            holding_type=holding_type if action == "buy" else None,
            reason=decision.get("reasoning", "Agent 自动决策"),
            thesis=decision.get("reasoning", ""),
            data_basis=["agent_brain_analysis"],
            risk_note=decision.get("risk_note", ""),
            invalidation=decision.get("invalidation", ""),
            triggered_by="agent",
        )

        trade_result = await self.service.execute_trade(
            self.portfolio_id,
            trade_input,
            date.today().isoformat(),
            position_id=position_id,
            stock_name=decision.get("stock_name"),
            source_run_id=run_id,
            source_plan_id=plan_id,
        )

        trade = trade_result.get("trade")
        position = trade_result.get("position")
        strategy_id = None

        if position and self._should_write_strategy(decision):
            strategy = await self.service.create_strategy(
                self.portfolio_id,
                position["id"],
                {
                    "take_profit": decision.get("take_profit"),
                    "stop_loss": decision.get("stop_loss"),
                    "reasoning": decision.get("reasoning", "Agent 自动策略"),
                    "details": {"source": "agent_execution"},
                },
                source_run_id=run_id,
            )
            strategy_id = strategy["id"]
            if trade:
                await self.service.update_trade_sources(
                    trade["id"],
                    source_strategy_id=strategy["id"],
                    source_strategy_version=strategy["version"],
                )

        await self.service.update_plan(plan_id, {"status": "executing"})

        return {
            "plan_id": plan_id,
            "trade_id": trade["id"] if trade else None,
            "strategy_id": strategy_id,
            "position_id": position["id"] if position else position_id,
            "skipped": False,
        }

    def _should_write_strategy(self, decision: dict) -> bool:
        return any(
            decision.get(field) is not None
            for field in ("take_profit", "stop_loss", "reasoning")
        )
