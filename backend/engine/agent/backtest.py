"""Agent backtest bootstrap orchestration."""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from engine.agent.brain import AgentBrain
from engine.agent.db import AgentDB
from engine.agent.execution import ExecutionCoordinator
from engine.agent.memory import MemoryManager
from engine.agent.review import ReviewEngine
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
        engine = get_data_engine()
        store = getattr(engine, "store", None)
        if store is not None and hasattr(store, "get_daily"):
            df = await asyncio.to_thread(
                store.get_daily,
                stock_code,
                start_day.isoformat(),
                end_day.isoformat(),
            )
        else:
            df = await asyncio.to_thread(
                engine.get_daily_history,
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
        position_rows = await self.db.execute_read(
            """
            SELECT DISTINCT stock_code
            FROM agent.positions
            WHERE portfolio_id = ?
            """,
            [portfolio_id],
        )
        trade_rows = await self.db.execute_read(
            """
            SELECT DISTINCT stock_code
            FROM agent.trades
            WHERE portfolio_id = ?
            """,
            [portfolio_id],
        )
        codes = {
            row["stock_code"]
            for row in [*position_rows, *trade_rows]
            if row.get("stock_code")
        }
        if not codes:
            return []

        trading_days: set[str] = set()
        for code in sorted(codes):
            for row in await self._get_history_rows(code, start_day, end_day):
                trading_days.add(row["date"])
        if not trading_days:
            return []

        return [date.fromisoformat(day) for day in sorted(trading_days)]

    @staticmethod
    def _merge_unique(existing: list[str], added: list[str]) -> list[str]:
        merged: list[str] = []
        for item in [*existing, *added]:
            if item and item not in merged:
                merged.append(item)
        return merged

    @staticmethod
    @contextmanager
    def _with_historical_market_context(as_of_date: str):
        import engine.data as data_module
        from engine.expert.tools import ExpertTools
        from engine.quant import get_quant_engine

        base_engine = get_data_engine()

        class HistoricalDataEngineAdapter:
            def __init__(self, engine, frozen_end: str):
                self._engine = engine
                self._frozen_end = frozen_end

            def get_daily_history(self, code: str, start: str, end: str):
                clamped_end = min(str(end)[:10], self._frozen_end)
                return self._engine.get_daily_history(code, start, clamped_end)

            def get_snapshot(self):
                # Current snapshot leaks future context during backtest; disable it.
                try:
                    import pandas as pd

                    return pd.DataFrame()
                except Exception:
                    return self._engine.get_snapshot()

            def __getattr__(self, name: str):
                return getattr(self._engine, name)

        adapter = HistoricalDataEngineAdapter(base_engine, as_of_date)
        original_factory = data_module.get_data_engine
        original_quant_caller = ExpertTools._call_quant_engine

        async def historical_quant_caller(self, action: str, params: dict):
            if action == "get_technical_indicators":
                code = params.get("code", "")
                end = _coerce_date(as_of_date)
                start = end - timedelta(days=120)
                daily = await asyncio.to_thread(
                    adapter.get_daily_history,
                    code,
                    start.isoformat(),
                    end.isoformat(),
                )
                if daily is None or daily.empty:
                    return {"error": f"股票 {code} 无日线数据"}
                indicators = get_quant_engine().compute_indicators(daily)
                return {
                    "code": code,
                    "data_days": len(daily),
                    "indicators": indicators,
                    "as_of_date": as_of_date,
                }
            return await original_quant_caller(self, action, params)

        data_module.get_data_engine = lambda: adapter
        ExpertTools._call_quant_engine = historical_quant_caller
        try:
            yield adapter
        finally:
            data_module.get_data_engine = original_factory
            ExpertTools._call_quant_engine = original_quant_caller

    async def _collect_memory_counts(self, portfolio_id: str) -> dict[str, int]:
        run_rows = await self.db.execute_read(
            """
            SELECT id
            FROM agent.brain_runs
            WHERE portfolio_id = ?
            """,
            [portfolio_id],
        )
        source_run_ids = [row["id"] for row in run_rows if row.get("id")]
        predicates = ["source_run_id LIKE 'weekly:%'"]
        params: list[str] = []
        if source_run_ids:
            placeholders = ", ".join("?" for _ in source_run_ids)
            predicates.append(f"source_run_id IN ({placeholders})")
            params.extend(source_run_ids)

        rows = await self.db.execute_read(
            f"""
            SELECT status, COUNT(*) AS count
            FROM agent.agent_memories
            WHERE {" OR ".join(predicates)}
            GROUP BY status
            """,
            params,
        )
        counts = {
            "total": 0,
            "active": 0,
            "retired": 0,
        }
        for row in rows:
            status = row.get("status")
            count = int(row.get("count") or 0)
            counts["total"] += count
            if status in counts:
                counts[status] = count
        return counts

    @staticmethod
    def _compute_memory_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
        keys = sorted(set(before.keys()) | set(after.keys()))
        return {
            key: int(after.get(key, 0) or 0) - int(before.get(key, 0) or 0)
            for key in keys
        }

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
        # Fill pricing is the intentional look-ahead layer for backtest execution.
        # Historical context freezing only applies to analysis/review data paths.
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
        brain_run_id: str | None = None,
        review_created: bool = False,
        memory_delta: dict[str, int] | None = None,
    ) -> None:
        await self.db.execute_write(
            """
            INSERT INTO agent.backtest_days (
                id, run_id, portfolio_id, trade_date, brain_run_id, review_created, memory_delta, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid.uuid4()),
                run_id,
                portfolio_id,
                trade_day,
                brain_run_id,
                review_created,
                json.dumps(memory_delta or {}, ensure_ascii=False),
                datetime.now().isoformat(),
            ],
        )

    @staticmethod
    def _compute_max_drawdown(equity_points: list[float]) -> float:
        if not equity_points:
            return 0.0
        peak = equity_points[0]
        max_drawdown = 0.0
        for equity in equity_points:
            peak = max(peak, equity)
            if peak <= 0:
                continue
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)
        return round(max_drawdown, 6)

    async def _compute_buy_and_hold_return(self, run_record: dict) -> float:
        start_day = _coerce_date(run_record["start_date"])
        end_day = _coerce_date(run_record["end_date"])
        source_portfolio_id = run_record["source_portfolio_id"]
        position_rows = await self.db.execute_read(
            """
            SELECT DISTINCT stock_code
            FROM agent.positions
            WHERE portfolio_id = ?
            """,
            [source_portfolio_id],
        )
        trade_rows = await self.db.execute_read(
            """
            SELECT DISTINCT stock_code
            FROM agent.trades
            WHERE portfolio_id = ?
            """,
            [source_portfolio_id],
        )
        codes = sorted(
            {
                row["stock_code"]
                for row in [*position_rows, *trade_rows]
                if row.get("stock_code")
            }
        )
        if not codes:
            return 0.0

        rows = await self._get_history_rows(codes[0], start_day, end_day)
        if len(rows) < 2:
            return 0.0
        start_close = rows[0].get("close")
        end_close = rows[-1].get("close")
        if start_close in (None, 0) or end_close is None:
            return 0.0
        return round((float(end_close) - float(start_close)) / float(start_close), 6)

    async def list_run_days(self, run_id: str) -> list[dict]:
        run_rows = await self.db.execute_read(
            "SELECT id FROM agent.backtest_runs WHERE id = ?",
            [run_id],
        )
        if not run_rows:
            raise ValueError(f"回测 {run_id} 不存在")
        return await self.db.execute_read(
            """
            SELECT *
            FROM agent.backtest_days
            WHERE run_id = ?
            ORDER BY trade_date
            """,
            [run_id],
        )

    async def get_run_summary(self, run_id: str) -> dict:
        run_rows = await self.db.execute_read(
            "SELECT * FROM agent.backtest_runs WHERE id = ?",
            [run_id],
        )
        if not run_rows:
            raise ValueError(f"回测 {run_id} 不存在")
        run_record = run_rows[0]
        portfolio = await self.service.get_portfolio(run_record["backtest_portfolio_id"])
        timeline = await self.service.get_equity_timeline(
            run_record["backtest_portfolio_id"],
            start_date=str(run_record["start_date"])[:10],
            end_date=str(run_record["end_date"])[:10],
        )
        mark_to_market = timeline.get("mark_to_market") or []
        equity_points = [float(item.get("equity") or 0.0) for item in mark_to_market]
        initial_capital = float(portfolio["config"]["initial_capital"])
        final_equity = equity_points[-1] if equity_points else initial_capital
        total_return = round((final_equity - initial_capital) / initial_capital, 6) if initial_capital else 0.0

        trade_rows = await self.db.execute_read(
            """
            SELECT id
            FROM agent.trades
            WHERE portfolio_id = ?
            ORDER BY created_at, id
            """,
            [run_record["backtest_portfolio_id"]],
        )
        review_rows = await self.db.execute_read(
            """
            SELECT rr.trade_id, rr.status, rr.review_date, rr.created_at
            FROM agent.review_records rr
            JOIN agent.brain_runs br
              ON rr.brain_run_id = br.id
            WHERE br.portfolio_id = ?
            ORDER BY rr.review_date DESC, rr.created_at DESC, rr.trade_id DESC
            """,
            [run_record["backtest_portfolio_id"]],
        )
        latest_by_trade: dict[str, dict] = {}
        for row in review_rows:
            trade_id = row.get("trade_id")
            if trade_id and trade_id not in latest_by_trade:
                latest_by_trade[trade_id] = row
        settled = [
            row for row in latest_by_trade.values()
            if row.get("status") in {"win", "loss"}
        ]
        win_count = len([row for row in settled if row.get("status") == "win"])
        win_rate = round((win_count / len(settled)), 6) if settled else 0.0

        day_rows = await self.list_run_days(run_id)
        review_count = sum(1 for row in day_rows if row.get("review_created")) + sum(
            1
            for row in day_rows
            if _coerce_date(row["trade_date"]).weekday() == 4
        )
        memory_added = 0
        memory_updated = 0
        memory_retired = 0
        for row in day_rows:
            delta = row.get("memory_delta") or {}
            memory_added += max(int(delta.get("total", 0) or 0), 0)
            memory_updated += 0
            memory_retired += max(int(delta.get("retired", 0) or 0), 0)

        return {
            "run_id": run_id,
            "status": run_record["status"],
            "source_portfolio_id": run_record["source_portfolio_id"],
            "backtest_portfolio_id": run_record["backtest_portfolio_id"],
            "start_date": str(run_record["start_date"])[:10],
            "end_date": str(run_record["end_date"])[:10],
            "total_return": total_return,
            "max_drawdown": self._compute_max_drawdown(equity_points),
            "trade_count": len(trade_rows),
            "win_rate": win_rate,
            "review_count": review_count,
            "memory_added": memory_added,
            "memory_updated": memory_updated,
            "memory_retired": memory_retired,
            "buy_and_hold_return": await self._compute_buy_and_hold_return(run_record),
        }

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
        review_engine = ReviewEngine(self.db, MemoryManager(self.db))
        days: list[dict] = []
        trades: list[dict] = []
        review_count = 0
        memory_delta_totals = {"total": 0, "active": 0, "retired": 0}
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
            with self._with_historical_market_context(trade_day_iso):
                await brain.execute(brain_run["id"])

            run_state = await self.service.get_brain_run(brain_run["id"])
            day_trade_rows: list[dict] = []
            day_plan_ids: list[str] = []
            day_trade_ids: list[str] = []
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
                day_plan_ids.append(plan["id"])
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
                day_trade_ids.append(trade_id)
                trade_rows = await self.db.execute_read(
                    "SELECT * FROM agent.trades WHERE id = ?",
                    [trade_id],
                )
                if trade_rows:
                    day_trade_rows.append(trade_rows[0])
                    trades.append(trade_rows[0])

            merged_plan_ids = self._merge_unique(run_state.get("plan_ids") or [], day_plan_ids)
            merged_trade_ids = self._merge_unique(run_state.get("trade_ids") or [], day_trade_ids)
            execution_summary = dict(run_state.get("execution_summary") or {})
            execution_summary["plan_count"] = len(merged_plan_ids)
            execution_summary["trade_count"] = len(merged_trade_ids)
            await self.service.update_brain_run(
                brain_run["id"],
                {
                    "plan_ids": merged_plan_ids,
                    "trade_ids": merged_trade_ids,
                    "execution_summary": execution_summary,
                },
            )

            memory_before = await self._collect_memory_counts(backtest_portfolio_id)
            daily_review_result = await review_engine.daily_review(as_of_date=trade_day_iso)
            weekly_review_result = None
            review_count += 1
            if trade_day.weekday() == 4:
                weekly_review_result = await review_engine.weekly_review(as_of_date=trade_day_iso)
                review_count += 1
            memory_after = await self._collect_memory_counts(backtest_portfolio_id)
            memory_delta = self._compute_memory_delta(memory_before, memory_after)
            for key, value in memory_delta.items():
                memory_delta_totals[key] = memory_delta_totals.get(key, 0) + value

            review_created = bool(daily_review_result.get("daily_review_id"))
            if weekly_review_result and weekly_review_result.get("summary_id"):
                review_created = True

            await self._insert_backtest_day(
                run_id,
                backtest_portfolio_id,
                trade_day_iso,
                brain_run_id=brain_run["id"],
                review_created=review_created,
                memory_delta=memory_delta,
            )
            days.append(
                {
                    "date": trade_day_iso,
                    "trade_count": len(day_trade_rows),
                    "review_created": review_created,
                    "memory_delta": memory_delta,
                }
            )

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
            "review_count": review_count,
            "memory_delta": memory_delta_totals,
        }
