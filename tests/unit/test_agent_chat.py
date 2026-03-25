"""Mounted agent chat contract tests."""
import asyncio
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeChatRuntime:
    async def stream_reply(self, *, portfolio_id, session_id, message, history):
        yield {
            "event": "reply_token",
            "data": {"content": "你好"},
        }
        yield {
            "event": "reply_token",
            "data": {"content": "，维持观察。"},
        }
        yield {
            "event": "reply_complete",
            "data": {
                "full_text": "你好，维持观察。",
                "thinking": [
                    {
                        "event": "reply_complete",
                        "data": {
                            "at": datetime(2026, 3, 22, 15, 0, 0),
                            "anchor_day": date(2026, 3, 22),
                        },
                    }
                ],
            },
        }


class CapturingChatRuntime:
    def __init__(self):
        self.last_history = None

    async def stream_reply(self, *, portfolio_id, session_id, message, history):
        self.last_history = history
        yield {
            "event": "reply_complete",
            "data": {
                "full_text": "收到上下文",
            },
        }


def _install_fake_runtime():
    try:
        import engine.agent.chat as chat_module
    except ModuleNotFoundError:
        return

    chat_module.DefaultAgentChatRuntime = FakeChatRuntime


def _make_app(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB

        AgentDB._instance = None
        db = AgentDB.init_instance()

    _install_fake_runtime()

    from engine.agent.routes import create_agent_router

    app = FastAPI()
    app.include_router(create_agent_router(), prefix="/api/v1/agent")
    return app, db


class TestMountedAgentChatRoutes:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _make_app(self._tmp)
        self.client = TestClient(self.app)
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "live", "mode": "live", "initial_capital": 1000000.0},
        )
        self.client.post(
            "/api/v1/agent/portfolio",
            json={"id": "paper", "mode": "sim", "initial_capital": 500000.0},
        )

    def teardown_method(self):
        self.db.close()

    def test_canonical_mounted_session_endpoints_work(self):
        legacy = self.client.get("/api/v1/agent/sessions", params={"portfolio_id": "live"})
        assert legacy.status_code == 404

        create_resp = self.client.post(
            "/api/v1/agent/chat/sessions",
            json={"portfolio_id": "live", "title": "Live Session"},
        )
        assert create_resp.status_code == 200

        list_resp = self.client.get(
            "/api/v1/agent/chat/sessions",
            params={"portfolio_id": "live"},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert len(data) == 1
        assert data[0]["portfolio_id"] == "live"
        assert data[0]["title"] == "Live Session"

    def test_chat_session_endpoints_require_existing_portfolio(self):
        create_resp = self.client.post(
            "/api/v1/agent/chat/sessions",
            json={"portfolio_id": "missing", "title": "No Portfolio"},
        )
        assert create_resp.status_code == 404

        list_resp = self.client.get(
            "/api/v1/agent/chat/sessions",
            params={"portfolio_id": "missing"},
        )
        assert list_resp.status_code == 404

    def test_delete_session_uses_canonical_mounted_route(self):
        create_resp = self.client.post(
            "/api/v1/agent/chat/sessions",
            json={"portfolio_id": "live", "title": "Delete Me"},
        )
        session_id = create_resp.json()["id"]

        delete_resp = self.client.delete(
            f"/api/v1/agent/chat/sessions/{session_id}",
            params={"portfolio_id": "live"},
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json() == {"ok": True}

        list_resp = self.client.get(
            "/api/v1/agent/chat/sessions",
            params={"portfolio_id": "live"},
        )
        assert list_resp.status_code == 200
        assert list_resp.json() == []

    def test_post_chat_streams_reply_token_then_reply_complete(self):
        create_resp = self.client.post(
            "/api/v1/agent/chat/sessions",
            json={"portfolio_id": "live", "title": "Agent Chat"},
        )
        session_id = create_resp.json()["id"]

        with self.client.stream(
            "POST",
            "/api/v1/agent/chat",
            json={
                "portfolio_id": "live",
                "session_id": session_id,
                "message": "现在怎么看茅台？",
            },
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())

        assert body.index("event: reply_token") < body.index("event: reply_complete")
        assert "event: error" not in body

    def test_get_messages_returns_persisted_user_and_assistant_messages(self):
        create_resp = self.client.post(
            "/api/v1/agent/chat/sessions",
            json={"portfolio_id": "live", "title": "Agent Chat"},
        )
        session_id = create_resp.json()["id"]

        self.client.post(
            "/api/v1/agent/chat",
            json={
                "portfolio_id": "live",
                "session_id": session_id,
                "message": "现在怎么看茅台？",
            },
        )

        resp = self.client.get(
            f"/api/v1/agent/chat/sessions/{session_id}/messages",
            params={"portfolio_id": "live"},
        )
        assert resp.status_code == 200
        messages = resp.json()
        assert [item["role"] for item in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "现在怎么看茅台？"
        assert messages[1]["content"] == "你好，维持观察。"
        assert messages[1]["thinking"] == [
            {
                "event": "reply_complete",
                "data": {
                    "at": "2026-03-22T15:00:00",
                    "anchor_day": "2026-03-22",
                },
            }
        ]

    def test_stream_chat_events_injects_latest_industry_digest_context(self):
        from engine.agent.chat import AgentChatService

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
                    "digest-ctx-1",
                    "live",
                    "run-ctx-1",
                    "600519",
                    "wake",
                    "{}",
                    '{"summary":"标的 600519 | industry=饮料制造 | cycle=高位震荡","key_evidence":["industry_cycle=高位震荡","capital=北向增持"]}',
                    "monitor only",
                    "minor_adjust",
                    "[]",
                    "2026-03-22T10:01:00",
                ],
            )
        )

        runtime = CapturingChatRuntime()
        svc = AgentChatService(db=self.db, chat_runtime=runtime)
        session = run(svc.create_session("live", "Industry Context"))

        async def collect():
            events = []
            async for event in svc.stream_chat_events(
                portfolio_id="live",
                session_id=session["id"],
                message="现在怎么看茅台？",
            ):
                events.append(event)
            return events

        events = run(collect())

        assert events[-1]["data"]["full_text"] == "收到上下文"
        assert runtime.last_history is not None
        assert any(item["role"] == "system" for item in runtime.last_history)
        system_messages = [item["content"] for item in runtime.last_history if item["role"] == "system"]
        assert any("饮料制造" in content for content in system_messages)
        assert any("高位震荡" in content for content in system_messages)
