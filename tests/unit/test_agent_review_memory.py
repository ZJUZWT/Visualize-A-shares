"""Agent Review/Memory 单元测试"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
import duckdb
import pytest
from unittest.mock import patch


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
