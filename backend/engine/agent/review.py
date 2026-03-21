"""Agent 复盘引擎骨架"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta

from engine.agent.db import AgentDB
from engine.agent.memory import MemoryManager


class ReviewEngine:
    """日复盘 / 周复盘最小可用骨架。"""

    def __init__(self, db: AgentDB, memory_mgr: MemoryManager):
        self.db = db
        self.memory_mgr = memory_mgr

    async def daily_review(self, as_of_date: str | None = None) -> dict:
        review_day = self._coerce_date(as_of_date)
        trade_ids = await self._get_recent_completed_trade_ids(review_day)
        records_created = 0
        daily_records: list[dict] = []

        for trade_id in trade_ids:
            existing = await self.db.execute_read(
                """
                SELECT id
                FROM agent.review_records
                WHERE trade_id = ? AND review_date = ?
                """,
                [trade_id, review_day.isoformat()],
            )
            if existing:
                continue

            trade_rows = await self.db.execute_read(
                "SELECT * FROM agent.trades WHERE id = ?",
                [trade_id],
            )
            if not trade_rows:
                continue

            trade = trade_rows[0]
            position_rows = await self.db.execute_read(
                "SELECT status FROM agent.positions WHERE id = ?",
                [trade["position_id"]],
            )
            position_status = position_rows[0]["status"] if position_rows else "closed"
            created_at = self._coerce_datetime(trade["created_at"])
            holding_days = max((review_day - created_at.date()).days, 0)
            review_price = trade["price"]
            pnl_pct = 0.0
            review_status = "holding" if position_status == "open" else "win"
            brain_run_id = await self._find_brain_run_id_for_trade(trade_id)

            await self.db.execute_write(
                """
                INSERT INTO agent.review_records (
                    id, brain_run_id, trade_id, stock_code, stock_name, action,
                    decision_price, review_price, pnl_pct, holding_days,
                    status, review_date, review_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'daily')
                """,
                [
                    str(uuid.uuid4()),
                    brain_run_id,
                    trade_id,
                    trade["stock_code"],
                    trade["stock_name"],
                    trade["action"],
                    trade["price"],
                    review_price,
                    pnl_pct,
                    holding_days,
                    review_status,
                    review_day.isoformat(),
                ],
            )
            records_created += 1
            daily_records.append(
                {
                    "trade_id": trade_id,
                    "status": review_status,
                    "pnl_pct": pnl_pct,
                }
            )

        if records_created > 0:
            active_rules = await self.memory_mgr.get_active_rules()
            win_count = sum(1 for record in daily_records if record["status"] == "win")
            loss_count = sum(1 for record in daily_records if record["status"] == "loss")
            validated = win_count >= loss_count
            for rule in active_rules:
                await self.memory_mgr.update_verification(rule["id"], validated)

        return {
            "status": "completed",
            "review_type": "daily",
            "review_date": review_day.isoformat(),
            "records_created": records_created,
        }

    async def weekly_review(self, as_of_date: str | None = None) -> dict:
        anchor_day = self._coerce_date(as_of_date)
        week_start = anchor_day - timedelta(days=anchor_day.weekday())
        week_end = week_start + timedelta(days=4)

        existing = await self.db.execute_read(
            "SELECT * FROM agent.weekly_summaries WHERE week_start = ?",
            [week_start.isoformat()],
        )
        if existing:
            return {
                "status": "completed",
                "review_type": "weekly",
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "new_rules": [],
                "retired_rules": [],
                "summary_id": existing[0]["id"],
            }

        records = await self.db.execute_read(
            """
            SELECT *
            FROM agent.review_records
            WHERE review_date >= ? AND review_date <= ?
            ORDER BY review_date, trade_id
            """,
            [week_start.isoformat(), week_end.isoformat()],
        )

        total_trades = len(records)
        win_records = [record for record in records if record["status"] == "win"]
        loss_records = [record for record in records if record["status"] == "loss"]
        win_count = len(win_records)
        loss_count = len(loss_records)
        win_rate = (win_count / total_trades) if total_trades else 0.0
        total_pnl_pct = sum(float(record.get("pnl_pct") or 0.0) for record in records)
        best_trade = max(records, key=lambda record: record.get("pnl_pct") or 0.0) if records else None
        worst_trade = min(records, key=lambda record: record.get("pnl_pct") or 0.0) if records else None

        new_rules: list[dict] = []
        if loss_count > win_count:
            new_rules.append(
                {
                    "rule_text": "本周亏损交易偏多，优先控制仓位并减少逆势买入",
                    "category": "risk",
                }
            )

        retired_rules = [
            rule["id"]
            for rule in await self.memory_mgr.get_active_rules(limit=100)
            if (rule.get("verify_count") or 0) >= 3 and (rule.get("confidence") or 0.0) < 0.5
        ]

        if new_rules:
            await self.memory_mgr.add_rules(new_rules, source_run_id=f"weekly:{week_start.isoformat()}")
        if retired_rules:
            await self.memory_mgr.retire_rules(retired_rules)

        insights = (
            f"本周共复盘 {total_trades} 笔交易，胜 {win_count} 笔，负 {loss_count} 笔，"
            f"总收益率 {round(total_pnl_pct * 100, 2)}%。"
        )
        summary_id = str(uuid.uuid4())
        await self.db.execute_write(
            """
            INSERT INTO agent.weekly_summaries (
                id, week_start, week_end, total_trades, win_count, loss_count,
                win_rate, total_pnl_pct, best_trade_id, worst_trade_id, insights
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                summary_id,
                week_start.isoformat(),
                week_end.isoformat(),
                total_trades,
                win_count,
                loss_count,
                win_rate,
                total_pnl_pct,
                best_trade["trade_id"] if best_trade else None,
                worst_trade["trade_id"] if worst_trade else None,
                insights,
            ],
        )

        return {
            "status": "completed",
            "review_type": "weekly",
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "new_rules": new_rules,
            "retired_rules": retired_rules,
            "summary_id": summary_id,
        }

    @staticmethod
    def _coerce_date(value: str | None) -> date:
        if value is None:
            return date.today()
        return date.fromisoformat(value)

    @staticmethod
    def _coerce_datetime(value) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    async def _get_recent_completed_trade_ids(self, review_day: date) -> list[str]:
        recent_from = review_day - timedelta(days=5)
        runs = await self.db.execute_read(
            """
            SELECT id, trade_ids
            FROM agent.brain_runs
            WHERE status = 'completed' AND started_at >= ?
            ORDER BY started_at DESC
            """,
            [recent_from.isoformat()],
        )
        trade_ids: list[str] = []
        seen: set[str] = set()
        for run in runs:
            raw_trade_ids = run.get("trade_ids")
            if raw_trade_ids is None:
                continue
            if isinstance(raw_trade_ids, str):
                parsed = json.loads(raw_trade_ids)
            else:
                parsed = raw_trade_ids
            for trade_id in parsed or []:
                if trade_id not in seen:
                    seen.add(trade_id)
                    trade_ids.append(trade_id)
        return trade_ids

    async def _find_brain_run_id_for_trade(self, trade_id: str) -> str | None:
        runs = await self.db.execute_read(
            "SELECT id, trade_ids FROM agent.brain_runs WHERE status = 'completed' ORDER BY started_at DESC"
        )
        for run in runs:
            raw_trade_ids = run.get("trade_ids")
            if raw_trade_ids is None:
                continue
            if isinstance(raw_trade_ids, str):
                parsed = json.loads(raw_trade_ids)
            else:
                parsed = raw_trade_ids
            if trade_id in (parsed or []):
                return run["id"]
        return None
