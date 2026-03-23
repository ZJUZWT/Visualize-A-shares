"""Agent DB bootstrap regressions."""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_config_uses_non_conflicting_agent_db_filename():
    from config import AGENT_DB_PATH

    assert AGENT_DB_PATH.name == "main_agent.duckdb"


def test_agent_db_init_migrates_legacy_agent_db_file():
    import duckdb
    import engine.agent.db as agent_db_module

    temp_dir = Path(tempfile.mkdtemp())
    legacy_path = temp_dir / "agent.duckdb"
    new_path = temp_dir / "main_agent.duckdb"

    conn = duckdb.connect(str(legacy_path))
    conn.close()

    with patch.object(agent_db_module, "AGENT_DB_PATH", new_path), patch.object(
        agent_db_module, "AGENT_DB_LEGACY_PATH", legacy_path
    ):
        agent_db_module.AgentDB._instance = None
        db = agent_db_module.AgentDB.init_instance()

        rows = run(
            db.execute_read(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = 'agent'
                """
            )
        )

        assert new_path.exists()
        assert rows[0]["schema_name"] == "agent"
        db.close()
