"""Agent wake/data hunger schema and service tests."""
import sys
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.agent.models import BrainRun


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


def _create_test_app(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()

    from engine.agent.routes import create_agent_router

    app = FastAPI()
    app.include_router(create_agent_router(), prefix="/api/v1/agent")
    return app, db


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


class TestWatchSignalService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("p1", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_create_and_list_watch_signals(self):
        from engine.agent.models import WatchSignalInput

        created = run(self.svc.create_watch_signal(
            "p1",
            WatchSignalInput(
                stock_code="600519",
                signal_description="白酒景气度回升",
                check_engine="info",
                keywords=["白酒", "回升"],
                if_triggered="考虑加仓",
            ),
        ))

        rows = run(self.svc.list_watch_signals("p1"))
        assert rows[0]["id"] == created["id"]
        assert rows[0]["portfolio_id"] == "p1"

    def test_update_watch_signal_status(self):
        from engine.agent.models import WatchSignalInput

        created = run(self.svc.create_watch_signal(
            "p1",
            WatchSignalInput(
                stock_code="600519",
                signal_description="白酒景气度回升",
                check_engine="info",
                keywords=["白酒", "回升"],
            ),
        ))

        updated = run(self.svc.update_watch_signal(created["id"], {"status": "triggered"}))
        assert updated["status"] == "triggered"


class TestWatchSignalRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "p1", "mode": "live", "initial_capital": 1000000.0},
        )

    def teardown_method(self):
        self.db.close()

    def test_watch_signal_routes(self):
        resp = self.client.post(
            "/api/v1/agent/watch-signals",
            json={
                "portfolio_id": "p1",
                "stock_code": "600519",
                "signal_description": "白酒景气度回升",
                "check_engine": "info",
                "keywords": ["白酒", "回升"],
                "if_triggered": "考虑加仓",
            },
        )
        assert resp.status_code == 200
        signal_id = resp.json()["id"]

        resp = self.client.get("/api/v1/agent/watch-signals?portfolio_id=p1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = self.client.patch(
            f"/api/v1/agent/watch-signals/{signal_id}",
            json={"status": "triggered"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"


class TestInfoDigestRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "p1", "mode": "live", "initial_capital": 1000000.0},
        )

        from engine.agent.service import AgentService
        from engine.agent.validator import TradeValidator

        self.svc = AgentService(db=self.db, validator=TradeValidator())
        run(self.svc.create_info_digest(
            portfolio_id="p1",
            run_id="run-1",
            stock_code="600519",
            digest_type="wake",
            raw_summary={"news": [{"title": "白酒回暖"}]},
            structured_summary={"summary": "白酒需求回暖"},
            strategy_relevance="watch signal triggered",
            impact_assessment="minor_adjust",
            missing_sources=["announcements"],
        ))
        run(self.svc.create_info_digest(
            portfolio_id="p1",
            run_id="run-2",
            stock_code="000858",
            digest_type="wake",
            raw_summary={"news": [{"title": "渠道改善"}]},
            structured_summary={"summary": "渠道反馈改善"},
            strategy_relevance="monitor only",
            impact_assessment="noted",
            missing_sources=[],
        ))

    def teardown_method(self):
        self.db.close()

    def test_get_info_digests_route_filters_by_run(self):
        resp = self.client.get("/api/v1/agent/info-digests?portfolio_id=p1&run_id=run-1")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) == 1
        assert payload[0]["run_id"] == "run-1"
        assert payload[0]["stock_code"] == "600519"

    def test_get_info_digests_route_returns_json_safe_fields(self):
        resp = self.client.get("/api/v1/agent/info-digests?portfolio_id=p1&limit=5")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload[0]["structured_summary"]["summary"]
        assert isinstance(payload[0]["missing_sources"], list)


class _FakeInfoEngine:
    def __init__(self, *, news=None, announcements=None, announcement_error: Exception | None = None):
        self._news = news or []
        self._announcements = announcements or []
        self._announcement_error = announcement_error

    async def get_news(self, code: str, limit: int = 20):
        return self._news

    async def get_announcements(self, code: str, limit: int = 10):
        if self._announcement_error is not None:
            raise self._announcement_error
        return self._announcements


class _FakeIndustryEngine:
    def __init__(self, cognition, capital_structure):
        self._cognition = cognition
        self._capital_structure = capital_structure

    async def analyze(self, target: str, as_of_date: str = "", force_refresh: bool = False):
        return self._cognition

    async def get_capital_structure(self, code: str, as_of_date: str = ""):
        return self._capital_structure


class TestDataHungerService:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)
        run(self.svc.create_portfolio("p1", "live", 1000000.0))

    def teardown_method(self):
        self.db.close()

    def test_query_industry_context_returns_normalized_payload(self):
        from engine.agent.data_hunger import DataHungerService
        from engine.industry.schemas import CapitalStructure, IndustryCognition

        hunger = DataHungerService(
            db=self.db,
            agent_service=self.svc,
            info_engine=_FakeInfoEngine(),
            industry_engine=_FakeIndustryEngine(
                IndustryCognition(
                    industry="饮料制造",
                    target="600519",
                    cycle_position="高位震荡",
                    catalysts=["旺季提价"],
                    risks=["需求放缓"],
                    core_drivers=["消费复苏"],
                    as_of_date="2026-03-22",
                ),
                CapitalStructure(
                    code="600519",
                    as_of_date="2026-03-22",
                    structure_summary="北向增持，主力净流入",
                ),
            ),
            daily_history_fetcher=lambda code: {"code": code, "history": []},
            technical_indicator_fetcher=lambda code: {"macd": "golden_cross"},
        )

        result = run(hunger.query_industry_context("600519"))
        assert result["industry"] == "饮料制造"
        assert result["cycle_position"] == "高位震荡"
        assert result["capital_summary"] == "北向增持，主力净流入"

    def test_scan_watch_signals_matches_keywords(self):
        from engine.agent.data_hunger import DataHungerService
        from engine.agent.models import WatchSignalInput
        from engine.industry.schemas import CapitalStructure, IndustryCognition

        run(self.svc.create_watch_signal(
            "p1",
            WatchSignalInput(
                stock_code="600519",
                signal_description="白酒景气度回升",
                check_engine="info",
                keywords=["白酒", "回升"],
            ),
        ))

        hunger = DataHungerService(
            db=self.db,
            agent_service=self.svc,
            info_engine=_FakeInfoEngine(
                news=[{"title": "白酒需求回升，龙头股走强", "content": "渠道反馈改善"}],
            ),
            industry_engine=_FakeIndustryEngine(
                IndustryCognition(industry="饮料制造", target="600519"),
                CapitalStructure(code="600519"),
            ),
            daily_history_fetcher=lambda code: {"code": code, "history": []},
            technical_indicator_fetcher=lambda code: {"macd": "golden_cross"},
        )

        hits = run(hunger.scan_watch_signals("p1"))
        assert hits[0]["signal_id"]
        assert hits[0]["stock_code"] == "600519"
        assert hits[0]["matched_keywords"] == ["白酒", "回升"]

    def test_execute_and_digest_marks_missing_sources(self):
        from engine.agent.data_hunger import DataHungerService
        from engine.industry.schemas import CapitalStructure, IndustryCognition

        hunger = DataHungerService(
            db=self.db,
            agent_service=self.svc,
            info_engine=_FakeInfoEngine(
                news=[{"title": "白酒龙头获资金关注", "content": "成交放大"}],
                announcement_error=RuntimeError("announcements unavailable"),
            ),
            industry_engine=_FakeIndustryEngine(
                IndustryCognition(
                    industry="饮料制造",
                    target="600519",
                    cycle_position="高位震荡",
                    catalysts=["旺季提价"],
                    risks=["需求放缓"],
                    core_drivers=["消费复苏"],
                    as_of_date="2026-03-22",
                ),
                CapitalStructure(
                    code="600519",
                    as_of_date="2026-03-22",
                    structure_summary="北向增持，主力净流入",
                ),
            ),
            daily_history_fetcher=lambda code: {"code": code, "history": [{"close": 1800.0}]},
            technical_indicator_fetcher=lambda code: {"macd": "golden_cross", "rsi": 61.5},
        )

        digest = run(hunger.execute_and_digest("p1", "run-1", "600519", triggers=[]))
        assert digest["impact_assessment"] in {"none", "noted", "minor_adjust", "reassess"}
        assert digest["missing_sources"] == ["announcements"]
