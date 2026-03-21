"""Agent Review/Memory 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
import duckdb
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


class TestReviewEngine:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, _ = _make_db(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_daily_review_placeholder(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        engine = ReviewEngine(db=self.db, memory_mgr=MemoryManager(self.db))

        result = run(engine.daily_review())

        assert result["review_type"] == "daily"
        assert result["records_created"] == 0
        assert result["status"] == "pending"

    def test_weekly_review_placeholder(self):
        from engine.agent.memory import MemoryManager
        from engine.agent.review import ReviewEngine

        engine = ReviewEngine(db=self.db, memory_mgr=MemoryManager(self.db))

        result = run(engine.weekly_review())

        assert result["review_type"] == "weekly"
        assert result["new_rules"] == []
        assert result["status"] == "pending"
