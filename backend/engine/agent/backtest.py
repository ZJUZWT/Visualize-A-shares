"""Agent backtest bootstrap orchestration."""
from __future__ import annotations

import uuid
from datetime import datetime

from engine.agent.db import AgentDB
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator


class AgentBacktestEngine:
    """Backtest engine bootstrap for isolated portfolio runs."""

    def __init__(
        self,
        db: AgentDB | None = None,
        service: AgentService | None = None,
    ):
        self.db = db or AgentDB.get_instance()
        self.service = service or AgentService(db=self.db, validator=TradeValidator())

    async def start_run(
        self,
        portfolio_id: str,
        start_date: str,
        end_date: str,
        execution_price_mode: str = "next_open",
    ) -> dict:
        source_rows = await self.db.execute_read(
            "SELECT * FROM agent.portfolio_config WHERE id = ?",
            [portfolio_id],
        )
        if not source_rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")

        source = source_rows[0]
        run_id = str(uuid.uuid4())
        backtest_portfolio_id = f"bt:{run_id}"
        now = datetime.now().isoformat()

        await self.db.execute_transaction(
            [
                (
                    """
                    INSERT INTO agent.portfolio_config
                    (id, mode, initial_capital, cash_balance, sim_start_date, sim_current_date, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        backtest_portfolio_id,
                        "training",
                        source["initial_capital"],
                        source["cash_balance"],
                        source["sim_start_date"],
                        source["sim_current_date"],
                        now,
                    ],
                ),
                (
                    """
                    INSERT INTO agent.backtest_runs
                    (
                        id,
                        source_portfolio_id,
                        backtest_portfolio_id,
                        start_date,
                        end_date,
                        execution_price_mode,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
                    """,
                    [
                        run_id,
                        portfolio_id,
                        backtest_portfolio_id,
                        start_date,
                        end_date,
                        execution_price_mode,
                        now,
                    ],
                ),
            ]
        )

        rows = await self.db.execute_read(
            "SELECT * FROM agent.backtest_runs WHERE id = ?",
            [run_id],
        )
        return rows[0]
