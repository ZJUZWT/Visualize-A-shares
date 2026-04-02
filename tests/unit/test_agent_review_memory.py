"""Agent Review/Memory 单元测试"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
import duckdb
import pytest
from unittest.mock import AsyncMock, patch


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_db(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()
    return db, db_path


def _make_service(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.service import AgentService
    from engine.agent.validator import TradeValidator

    svc = AgentService(db=db, validator=TradeValidator())
    return db, svc


class TestReviewMemoryTables:
    def test_review_memory_tables_exist(self, tmp_path):
        db, db_path = _make_db(tmp_path)

        conn = duckdb.connect(str(db_path))
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='agent'"
        ).fetchall()
        conn.close()
        db.close()

        table_names = {row[0] for row in tables}
        assert "review_records" in table_names
        assert "weekly_summaries" in table_names
        assert "agent_memories" in table_names

    def test_reflection_journals_have_info_review_columns(self, tmp_path):
        db, db_path = _make_db(tmp_path)

        conn = duckdb.connect(str(db_path))

        def columns_for(table_name: str) -> set[str]:
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema='agent' AND table_name=?
                """,
                [table_name],
            ).fetchall()
            return {row[0] for row in rows}

        daily_columns = columns_for("daily_reviews")
        weekly_columns = columns_for("weekly_reflections")

        conn.close()
        db.close()

        assert "info_review_summary" in daily_columns
        assert "info_review_details" in daily_columns
        assert "info_review_summary" in weekly_columns
        assert "info_review_details" in weekly_columns


class TestReviewMemoryModels:
    def test_agent_memory_defaults(self):
        from engine.agent.models import AgentMemory

        record = AgentMemory(
            id="rule-1",
            rule_text="回调再买",
            category="timing",
            source_run_id="run-1",
            created_at="2026-03-22T15:45:00",
        )

        assert record.status == "active"
        assert record.confidence == 0.5
        assert record.verify_count == 0
        assert record.verify_win == 0
        assert record.retired_at is None

    def test_reflection_models_allow_info_review_fields(self):
        from engine.agent.models import DailyReview, WeeklyReflection

        daily = DailyReview(
            id="daily-1",
            review_date="2026-03-22",
            info_review_summary="当日共审计 2 条 digest，其中 1 条有效。",
            info_review_details={"digest_count": 2, "useful_count": 1},
            created_at="2026-03-22T15:45:00",
        )
        weekly = WeeklyReflection(
            id="weekly-1",
            week_start="2026-03-16",
            week_end="2026-03-20",
            info_review_summary="本周 digest 总体偏噪音。",
            info_review_details={"digest_count": 8, "misleading_count": 2},
            created_at="2026-03-20T16:00:00",
        )

        assert daily.info_review_summary is not None
        assert daily.info_review_details == {"digest_count": 2, "useful_count": 1}
        assert weekly.info_review_summary is not None
        assert weekly.info_review_details == {"digest_count": 8, "misleading_count": 2}


class TestMemoryManager:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, _ = _make_db(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_add_rules_and_get_active_rules(self):
        from engine.agent.memory import MemoryManager

        mgr = MemoryManager(self.db)
        created_ids = run(
            mgr.add_rules(
                [
                    {"rule_text": "不要追高", "category": "timing"},
                    {"rule_text": "单票仓位不要过重", "category": "risk"},
                ],
                source_run_id="run-1",
            )
        )

        rules = run(mgr.get_active_rules(limit=10))

        assert len(created_ids) == 2
        assert len(rules) == 2
        assert {rule["status"] for rule in rules} == {"active"}
        assert {rule["source_run_id"] for rule in rules} == {"run-1"}

    def test_update_verification_updates_confidence(self):
        from engine.agent.memory import MemoryManager

        mgr = MemoryManager(self.db)
        rule_id = run(
            mgr.add_rules(
                [{"rule_text": "止损必须执行", "category": "risk"}],
                source_run_id="run-1",
            )
        )[0]

        run(mgr.update_verification(rule_id, validated=True))
        updated = run(mgr.list_rules(status="active"))[0]

        assert updated["id"] == rule_id
        assert updated["verify_count"] == 1
        assert updated["verify_win"] == 1
        assert updated["confidence"] == 1.0
        assert updated["status"] == "active"

    def test_list_rules_returns_json_safe_timestamps(self):
        from engine.agent.memory import MemoryManager

        mgr = MemoryManager(self.db)
        run(
            mgr.add_rules(
                [{"rule_text": "等待回调再买", "category": "timing"}],
                source_run_id="run-1",
            )
        )

        rules = run(mgr.list_rules())

        assert isinstance(rules[0]["created_at"], str)
        json.dumps(rules)

    def test_update_verification_auto_retires_low_confidence_rule(self):
        from engine.agent.memory import MemoryManager

        mgr = MemoryManager(self.db)
        rule_id = run(
            mgr.add_rules(
                [{"rule_text": "连涨三天不要追", "category": "timing"}],
                source_run_id="run-1",
            )
        )[0]

        for _ in range(5):
            run(mgr.update_verification(rule_id, validated=False))

        retired = run(mgr.list_rules(status="retired"))[0]

        assert retired["id"] == rule_id
        assert retired["verify_count"] == 5
        assert retired["verify_win"] == 0
        assert retired["confidence"] == 0.0
        assert retired["status"] == "retired"
        assert retired["retired_at"] is not None

    def test_add_rules_is_atomic_when_rule_payload_invalid(self):
        from engine.agent.memory import MemoryManager

        mgr = MemoryManager(self.db)

        with pytest.raises(KeyError, match="category"):
            run(
                mgr.add_rules(
                    [
                        {"rule_text": "第一条有效规则", "category": "timing"},
                        {"rule_text": "第二条缺字段"},
                    ],
                    source_run_id="run-1",
                )
            )

        rows = run(self.db.execute_read("SELECT * FROM agent.agent_memories"))
        assert rows == []


class TestReviewEngine:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("live", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_daily_review_writes_records_idempotently_and_updates_memory_verification(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        memory_mgr = MemoryManager(self.db)
        rule_id = run(
            memory_mgr.add_rules(
                [{"rule_text": "买入后先观察，不追涨加仓", "category": "risk"}],
                source_run_id="seed-run",
            )
        )[0]
        trade = run(
            self.svc.execute_trade(
                "live",
                self._make_trade_input(),
                "2026-03-20",
                source_run_id="run-1",
            )
        )["trade"]
        run_record = run(self.svc.create_brain_run("live", "manual"))
        run(
            self.svc.update_brain_run(
                run_record["id"],
                {"status": "completed", "trade_ids": [trade["id"]]},
            )
        )

        engine = ReviewEngine(db=self.db, memory_mgr=memory_mgr)

        first = run(engine.daily_review())
        second = run(engine.daily_review())

        records = run(
            self.db.execute_read(
                "SELECT * FROM agent.review_records WHERE trade_id = ?",
                [trade["id"]],
            )
        )
        updated_rule = run(memory_mgr.list_rules(status="active"))[0]

        assert first["review_type"] == "daily"
        assert first["status"] == "completed"
        assert first["records_created"] == 1
        assert second["records_created"] == 0
        assert len(records) == 1
        assert records[0]["brain_run_id"] == run_record["id"]
        assert records[0]["review_type"] == "daily"
        assert records[0]["status"] == "holding"
        assert updated_rule["id"] == rule_id
        assert updated_rule["verify_count"] == 1
        assert updated_rule["verify_win"] == 1

    def test_daily_review_persists_info_review_summary_and_details(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        memory_mgr = MemoryManager(self.db)
        trade = run(
            self.svc.execute_trade(
                "live",
                self._make_trade_input(),
                "2026-03-20",
                source_run_id="run-info-1",
            )
        )["trade"]
        run_record = run(self.svc.create_brain_run("live", "manual"))
        run(
            self.svc.update_brain_run(
                run_record["id"],
                {
                    "status": "completed",
                    "trade_ids": [trade["id"]],
                    "thinking_process": {
                        "gate_result": {
                            "requires_wait": False,
                            "accepted_count": 1,
                            "rejected_count": 0,
                            "rejections": [],
                        }
                    },
                    "execution_summary": {"trade_count": 1},
                },
            )
        )
        run(
            self.db.execute_write(
                "UPDATE agent.brain_runs SET started_at = ? WHERE id = ?",
                ["2026-03-22T10:00:00", run_record["id"]],
            )
        )
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.info_digests (
                    id, portfolio_id, run_id, stock_code, digest_type,
                    raw_summary, structured_summary, strategy_relevance,
                    impact_assessment, missing_sources, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    "digest-1",
                    "live",
                    run_record["id"],
                    "600519",
                    "wake",
                    json.dumps({"news": []}, ensure_ascii=False),
                    json.dumps({"summary": "白酒需求回暖"}, ensure_ascii=False),
                    "watch signal triggered",
                    "minor_adjust",
                    json.dumps([], ensure_ascii=False),
                    "2026-03-22T10:01:00",
                ],
            )
        )

        engine = ReviewEngine(db=self.db, memory_mgr=memory_mgr)
        run(engine.daily_review(as_of_date="2026-03-22"))

        journal = run(
            self.db.execute_read(
                "SELECT info_review_summary, info_review_details FROM agent.daily_reviews WHERE review_date = ?",
                ["2026-03-22"],
            )
        )[0]

        assert journal["info_review_summary"] is not None
        assert "digest" in journal["info_review_summary"]
        assert journal["info_review_details"]["digest_count"] == 1
        assert journal["info_review_details"]["useful_count"] == 1
        assert journal["info_review_details"]["misleading_count"] == 0
        assert journal["info_review_details"]["items"][0]["review_label"] == "useful"

    def test_weekly_review_writes_summary_and_updates_memories(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        memory_mgr = MemoryManager(self.db)
        retiring_rule_id = run(
            memory_mgr.add_rules(
                [{"rule_text": "低置信度旧规则", "category": "risk"}],
                source_run_id="seed-run",
            )
        )[0]
        for _ in range(3):
            run(memory_mgr.update_verification(retiring_rule_id, validated=False))

        run(
            self.db.execute_write(
                """
                INSERT INTO agent.review_records (
                    id, brain_run_id, trade_id, stock_code, stock_name, action,
                    decision_price, review_price, pnl_pct, holding_days,
                    status, review_date, review_type
                )
                VALUES
                    ('review-1', 'run-1', 'trade-1', '600519', '贵州茅台', 'buy',
                     1800.0, 1764.0, -0.02, 3, 'loss', '2026-03-16', 'daily'),
                    ('review-2', 'run-2', 'trade-2', '601318', '中国平安', 'buy',
                     50.0, 49.0, -0.02, 2, 'loss', '2026-03-18', 'daily'),
                    ('review-3', 'run-3', 'trade-3', '000858', '五粮液', 'buy',
                     140.0, 142.8, 0.02, 2, 'win', '2026-03-19', 'daily')
                """
            )
        )

        engine = ReviewEngine(db=self.db, memory_mgr=memory_mgr)

        result = run(engine.weekly_review(as_of_date="2026-03-20"))
        summary_rows = run(
            self.db.execute_read("SELECT * FROM agent.weekly_summaries WHERE week_start = '2026-03-16'")
        )
        active_rules = run(memory_mgr.list_rules(status="active"))
        retired_rules = run(memory_mgr.list_rules(status="retired"))

        assert result["review_type"] == "weekly"
        assert result["status"] == "completed"
        assert result["new_rules"] != []
        assert result["retired_rules"] == [retiring_rule_id]
        assert len(summary_rows) == 1
        assert summary_rows[0]["total_trades"] == 3
        assert summary_rows[0]["loss_count"] == 2
        assert summary_rows[0]["win_count"] == 1
        assert summary_rows[0]["best_trade_id"] == "trade-3"
        assert summary_rows[0]["worst_trade_id"] == "trade-1"
        assert any(rule["source_run_id"] == "weekly:2026-03-16" for rule in active_rules)
        assert retired_rules[0]["id"] == retiring_rule_id

    def test_weekly_review_aggregates_info_review_from_daily_journals(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        run(
            self.db.execute_write(
                """
                INSERT INTO agent.daily_reviews (
                    id, review_date, total_reviews, win_count, loss_count,
                    holding_count, total_pnl_pct, summary,
                    info_review_summary, info_review_details
                )
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?),
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    "daily-info-1",
                    "2026-03-16",
                    1,
                    1,
                    0,
                    0,
                    0.01,
                    "首日复盘",
                    "首日信息复盘",
                    json.dumps(
                        {
                            "digest_count": 2,
                            "useful_count": 1,
                            "misleading_count": 0,
                            "inconclusive_count": 1,
                            "noted_count": 0,
                            "top_missing_sources": ["filing", "macro"],
                            "items": [],
                        },
                        ensure_ascii=False,
                    ),
                    "daily-info-2",
                    "2026-03-18",
                    1,
                    0,
                    1,
                    0,
                    -0.02,
                    "次日复盘",
                    "次日信息复盘",
                    json.dumps(
                        {
                            "digest_count": 3,
                            "useful_count": 1,
                            "misleading_count": 1,
                            "inconclusive_count": 0,
                            "noted_count": 1,
                            "top_missing_sources": ["filing", "channel"],
                            "items": [],
                        },
                        ensure_ascii=False,
                    ),
                ],
            )
        )
        run(
            self.db.execute_write(
                """
                INSERT INTO agent.review_records (
                    id, brain_run_id, trade_id, stock_code, stock_name, action,
                    decision_price, review_price, pnl_pct, holding_days,
                    status, review_date, review_type
                )
                VALUES
                    ('review-1', 'run-1', 'trade-1', '600519', '贵州茅台', 'buy',
                     1800.0, 1818.0, 0.01, 2, 'win', '2026-03-16', 'daily'),
                    ('review-2', 'run-2', 'trade-2', '601318', '中国平安', 'buy',
                     50.0, 49.0, -0.02, 1, 'loss', '2026-03-18', 'daily')
                """
            )
        )

        engine = ReviewEngine(db=self.db, memory_mgr=MemoryManager(self.db))

        result = run(engine.weekly_review(as_of_date="2026-03-20"))
        reflection = run(
            self.db.execute_read(
                """
                SELECT info_review_summary, info_review_details
                FROM agent.weekly_reflections
                WHERE week_start = ?
                """,
                ["2026-03-16"],
            )
        )[0]

        assert result["review_type"] == "weekly"
        assert reflection["info_review_summary"] is not None
        assert reflection["info_review_details"]["digest_count"] == 5
        assert reflection["info_review_details"]["useful_count"] == 2
        assert reflection["info_review_details"]["misleading_count"] == 1
        assert reflection["info_review_details"]["inconclusive_count"] == 1
        assert reflection["info_review_details"]["noted_count"] == 1
        assert reflection["info_review_details"]["top_missing_sources"] == ["filing", "channel", "macro"]

    @staticmethod
    def _make_trade_input():
        from engine.agent.models import TradeInput

        return TradeInput(
            action="buy",
            stock_code="600519",
            price=1800.0,
            quantity=100,
            holding_type="mid_term",
            reason="景气修复",
            thesis="基本面改善",
            data_basis=["营收修复"],
            risk_note="估值偏高",
            invalidation="景气转弱",
            triggered_by="agent",
        )


class TestPlanReviewIsolation:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_plan_review_does_not_write_review_records(self):
        from engine.agent.models import TradePlanInput

        created = run(
            self.svc.create_plan(
                TradePlanInput(
                    stock_code="600519",
                    stock_name="贵州茅台",
                    current_price=102.0,
                    direction="buy",
                    entry_price="100 / 98",
                    take_profit="110 / 115",
                    stop_loss=95.0,
                    reasoning="等待回踩后再看修复",
                    valid_until="2026-04-10",
                )
            )
        )
        run(
            self.db.execute_write(
                "UPDATE agent.trade_plans SET created_at = ?, updated_at = ? WHERE id = ?",
                ["2026-04-01T09:30:00", "2026-04-01T09:30:00", created["id"]],
            )
        )

        with patch.object(
            self.svc,
            "_load_price_history",
            AsyncMock(
                return_value={
                    "600519": {
                        "2026-04-01": 102.0,
                        "2026-04-02": 99.0,
                        "2026-04-03": 108.0,
                        "2026-04-04": 112.0,
                    }
                }
            ),
        ):
            review = run(
                self.svc.review_plan(
                    created["id"],
                    review_date="2026-04-04",
                    review_window=5,
                )
            )

        review_rows = run(self.db.execute_read("SELECT * FROM agent.review_records"))
        plan_review_rows = run(self.db.execute_read("SELECT * FROM agent.plan_reviews"))

        assert review["outcome_label"] == "useful"
        assert review_rows == []
        assert len(plan_review_rows) == 1
