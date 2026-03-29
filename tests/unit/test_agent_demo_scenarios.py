"""Demo agent scenario seeding tests."""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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


class TestDemoAgentScenarioSeeder:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_prepare_scenario_creates_deterministic_baseline(self):
        from engine.agent.demo_scenarios import DemoAgentScenarioSeeder

        seeder = DemoAgentScenarioSeeder(service=self.svc, db=self.db)
        summary = run(seeder.prepare_scenario("demo-evolution"))

        portfolio = run(self.svc.get_portfolio(summary["portfolio_id"]))
        state = run(self.svc.get_agent_state(summary["portfolio_id"]))
        watchlist_rows = run(
            self.db.execute_read(
                "SELECT * FROM agent.watchlist WHERE added_by = 'demo-seed' ORDER BY stock_code"
            )
        )
        memory_rows = run(
            self.db.execute_read(
                """
                SELECT *
                FROM agent.agent_memories
                WHERE source_run_id = ?
                ORDER BY id
                """,
                [summary["seed_run_id"]],
            )
        )
        review_rows = run(self.svc.list_review_records(summary["portfolio_id"], days=3650))

        assert summary["scenario_id"] == "demo-evolution"
        assert portfolio["config"]["mode"] == "training"
        assert state["market_view"]["stance"] == "risk-off"
        assert len(watchlist_rows) == 2
        assert {row["portfolio_id"] for row in watchlist_rows} == {summary["portfolio_id"]}
        assert len(memory_rows) == 1
        assert memory_rows[0]["status"] == "active"
        assert len(review_rows) == 2
        assert all(row["status"] == "loss" for row in review_rows)

    def test_prepare_scenario_is_idempotent(self):
        from engine.agent.demo_scenarios import DemoAgentScenarioSeeder

        seeder = DemoAgentScenarioSeeder(service=self.svc, db=self.db)
        first = run(seeder.prepare_scenario("demo-evolution"))
        second = run(seeder.prepare_scenario("demo-evolution"))

        watchlist_count = run(
            self.db.execute_read("SELECT COUNT(*) AS count FROM agent.watchlist WHERE added_by = 'demo-seed'")
        )[0]["count"]
        memory_count = run(
            self.db.execute_read(
                "SELECT COUNT(*) AS count FROM agent.agent_memories WHERE source_run_id = ?",
                [second["seed_run_id"]],
            )
        )[0]["count"]
        review_count = len(run(self.svc.list_review_records(second["portfolio_id"], days=3650)))

        assert first["portfolio_id"] == second["portfolio_id"]
        assert watchlist_count == 2
        assert memory_count == 1
        assert review_count == 2
