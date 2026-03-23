"""Agent backtest bootstrap orchestration."""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta

from engine.agent.brain import AgentBrain
from engine.agent.db import AgentDB
from engine.agent.execution import ExecutionCoordinator
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator
from engine.data import get_data_engine


def _coerce_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


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

    @staticmethod
    def _iter_days(start_day: date, end_day: date) -> list[date]:
        days: list[date] = []
        current = start_day
        while current <= end_day:
            days.append(current)
            current += timedelta(days=1)
        return days

    async def _get_history_rows(self, stock_code: str, start_day: date, end_day: date) -> list[dict]:
        df = await asyncio.to_thread(
            get_data_engine().get_daily_history,
            stock_code,
            start_day.isoformat(),
            end_day.isoformat(),
        )
        if df is None or df.empty:
            return []
        rows: list[dict] = []
        for row in df.to_dict("records"):
            day = str(row.get("date", ""))[:10]
            if not day:
                continue
            rows.append(
                {
                    "date": day,
                    "open": row.get("open"),
                    "close": row.get("close"),
                }
        )
        rows.sort(key=lambda item: item["date"])
        return rows

    async def _resolve_trading_days(
        self,
        portfolio_id: str,
        start_day: date,
        end_day: date,
    ) -> list[date]:
        code_rows = await self.db.execute_read(
            """
            SELECT DISTINCT stock_code
            FROM agent.watchlist
            WHERE stock_code IS NOT NULL
            """,
        )
        position_rows = await self.db.execute_read(
            """
            SELECT DISTINCT stock_code
            FROM agent.positions
            WHERE portfolio_id = ?
            """,
            [portfolio_id],
        )
        codes = {
            row["stock_code"]
            for row in [*code_rows, *position_rows]
            if row.get("stock_code")
        }
        if not codes:
            return self._iter_days(start_day, end_day)

        trading_days: set[str] = set()
        for code in sorted(codes):
            for row in await self._get_history_rows(code, start_day, end_day):
                trading_days.add(row["date"])
        if not trading_days:
            return self._iter_days(start_day, end_day)

        return [date.fromisoformat(day) for day in sorted(trading_days)]

    async def _resolve_fill(
        self,
        decision: dict,
        as_of_day: date,
        execution_price_mode: str,
        end_day: date,
    ) -> tuple[str, float] | None:
        stock_code = decision.get("stock_code")
        if not stock_code:
            return None

        rows = await self._get_history_rows(
            stock_code,
            as_of_day,
            end_day + timedelta(days=7),
        )
        as_of_iso = as_of_day.isoformat()

        if execution_price_mode == "same_close":
            for row in rows:
                if row["date"] == as_of_iso and row.get("close") is not None:
                    return as_of_iso, float(row["close"])
            return None

        if execution_price_mode == "next_open":
            for row in rows:
                if row["date"] > as_of_iso and row.get("open") is not None:
                    return row["date"], float(row["open"])
            return None

        raise ValueError(f"不支持的 execution_price_mode: {execution_price_mode}")

    async def _insert_backtest_day(
        self,
        run_id: str,
        portfolio_id: str,
        trade_day: str,
    ) -> None:
        await self.db.execute_write(
            """
            INSERT INTO agent.backtest_days (id, run_id, portfolio_id, trade_date, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [str(uuid.uuid4()), run_id, portfolio_id, trade_day, datetime.now().isoformat()],
        )

    async def run_backtest(
        self,
        portfolio_id: str,
        start_date: str,
        end_date: str,
        execution_price_mode: str = "next_open",
    ) -> dict:
        start_day = _coerce_date(start_date)
        end_day = _coerce_date(end_date)
        if end_day < start_day:
            raise ValueError("结束日期不能早于开始日期")

        run_record = await self.start_run(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            execution_price_mode=execution_price_mode,
        )
        run_id = run_record["id"]
        backtest_portfolio_id = run_record["backtest_portfolio_id"]

        execution = ExecutionCoordinator(backtest_portfolio_id, self.service)
        days: list[dict] = []
        trades: list[dict] = []
        trading_days = await self._resolve_trading_days(
            portfolio_id=portfolio_id,
            start_day=start_day,
            end_day=end_day,
        )

        for trade_day in trading_days:
            trade_day_iso = trade_day.isoformat()
            await self.db.execute_write(
                """
                UPDATE agent.portfolio_config
                SET sim_current_date = ?
                WHERE id = ?
                """,
                [trade_day_iso, backtest_portfolio_id],
            )

            brain_run = await self.service.create_brain_run(
                backtest_portfolio_id,
                run_type="backtest",
            )
            brain = AgentBrain(backtest_portfolio_id)
            setattr(brain, "_skip_execution", True)
            await brain.execute(brain_run["id"])

            run_state = await self.service.get_brain_run(brain_run["id"])
            day_trade_rows: list[dict] = []
            for decision in run_state.get("decisions") or []:
                action = decision.get("action", "")
                if action in ("hold", "ignore", ""):
                    continue
                fill = await self._resolve_fill(decision, trade_day, execution_price_mode, end_day)
                if not fill:
                    continue

                fill_date, fill_price = fill
                decision_with_fill = dict(decision)
                decision_with_fill["price"] = fill_price

                plan = await execution.create_plan_from_decision(brain_run["id"], decision_with_fill)
                execute_result = await execution.execute_plan(
                    brain_run["id"],
                    plan["id"],
                    decision_with_fill,
                    trade_date=fill_date,
                    price_override=fill_price,
                )
                trade_id = execute_result.get("trade_id")
                if not trade_id:
                    continue
                trade_rows = await self.db.execute_read(
                    "SELECT * FROM agent.trades WHERE id = ?",
                    [trade_id],
                )
                if trade_rows:
                    day_trade_rows.append(trade_rows[0])
                    trades.append(trade_rows[0])

            await self._insert_backtest_day(run_id, backtest_portfolio_id, trade_day_iso)
            days.append({"date": trade_day_iso, "trade_count": len(day_trade_rows)})

        await self.db.execute_write(
            "UPDATE agent.backtest_runs SET status = ? WHERE id = ?",
            ["completed", run_id],
        )
        final_rows = await self.db.execute_read(
            "SELECT * FROM agent.backtest_runs WHERE id = ?",
            [run_id],
        )
        return {
            "id": run_id,
            "status": (final_rows[0]["status"] if final_rows else "completed"),
            "days": days,
            "trades": trades,
        }
