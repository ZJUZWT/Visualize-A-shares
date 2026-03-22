"""Agent wake/data hunger schema and service tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from engine.agent.models import BrainRun


class TestDataHungerModels:
    def test_brain_run_supports_digest_link_fields(self):
        run = BrainRun(
            id="run-1",
            portfolio_id="portfolio-1",
            started_at="2026-03-22T10:00:00",
            info_digest_ids=["digest-1"],
            triggered_signal_ids=["signal-1"],
        )

        assert run.info_digest_ids == ["digest-1"]
        assert run.triggered_signal_ids == ["signal-1"]
