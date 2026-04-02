"""路由测试"""

import asyncio
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import duckdb
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from engine.expert.routes import router, _init_db, get_expert_agent
from engine.expert.schemas import (
    ExpertChatRequest,
    ExpertResumeRequest,
    FeedbackReportCreateRequest,
    FeedbackReportDetail,
    FeedbackReportSummary,
    FeedbackResolveRequest,
    FeedbackResolveResponse,
    FeedbackSubmitResponse,
)


@pytest.fixture
def client():
    """创建测试客户端"""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_beliefs(client):
    """测试获取信念"""
    with patch("engine.expert.routes.get_expert_agent") as mock_get_agent:
        mock_agent = Mock()
        mock_agent.get_beliefs.return_value = []
        mock_get_agent.return_value = mock_agent

        response = client.get("/api/v1/expert/beliefs")
        assert response.status_code == 200
        assert "beliefs" in response.json()


def test_get_stances(client):
    """测试获取立场"""
    with patch("engine.expert.routes.get_expert_agent") as mock_get_agent:
        mock_agent = Mock()
        mock_agent.get_stances.return_value = []
        mock_get_agent.return_value = mock_agent

        response = client.get("/api/v1/expert/stances")
        assert response.status_code == 200
        assert "stances" in response.json()


def test_clarify_rag_returns_summary_and_skip_option(client):
    """深度思考模式应先返回 clarification 选项卡数据"""
    with patch("engine.expert.routes.get_expert_agent") as mock_get_agent:
        mock_agent = Mock()
        mock_agent.clarify = AsyncMock(return_value={
            "should_clarify": True,
            "question_summary": "你想先判断这只股票值不值得参与，以及应该按什么角度分析。",
            "reasoning": "原问题较宽，先确认关注重点。",
            "options": [
                {
                    "id": "valuation",
                    "label": "A",
                    "title": "先看估值与安全边际",
                    "description": "适合长线判断值不值。",
                    "focus": "估值、安全边际、风险收益比",
                }
            ],
            "skip_option": {
                "id": "skip",
                "label": "S",
                "title": "跳过，直接分析",
                "description": "不做澄清，直接进入完整分析。",
                "focus": "完整分析",
            },
        })
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/v1/expert/clarify/rag",
            json={"message": "宁德时代值不值得买？"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["should_clarify"] is True
        assert data["question_summary"]
        assert data["options"][0]["label"] == "A"
        assert data["skip_option"]["id"] == "skip"


def test_clarify_short_term_uses_short_term_persona(client):
    with patch("engine.expert.routes.get_expert_agent") as mock_get_agent:
        mock_agent = Mock()
        mock_agent.clarify = AsyncMock(return_value={
            "should_clarify": True,
            "question_summary": "你想判断这笔交易的短线节奏和执行窗口。",
            "reasoning": "短线问题需要先确认关注点。",
            "options": [],
            "skip_option": {
                "id": "skip",
                "label": "S",
                "title": "跳过，直接分析",
                "description": "直接进入完整分析。",
                "focus": "完整分析",
            },
        })
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/api/v1/expert/clarify/short_term",
            json={"message": "今天有没有短线机会？"},
        )

        assert response.status_code == 200
        mock_agent.clarify.assert_awaited_once_with(
            "今天有没有短线机会？",
            history=[],
            persona="short_term",
            previous_selections=[],
        )


def test_clarify_rag_empty_options_falls_back_to_safe_options(client, tmp_path):
    from engine.expert.agent import ExpertAgent

    class _MockLLM:
        async def chat_stream(self, messages):
            _ = messages
            yield (
                '{"should_clarify": true, "question_summary": "还需要进一步聚焦", '
                '"multi_select": false, "options": [], "reasoning": "需要继续确认重点", '
                '"needs_more": true}'
            )

    mock_tools = Mock()
    mock_tools.llm_engine = _MockLLM()
    mock_tools.execute = AsyncMock(return_value="tool result")
    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    with patch("engine.expert.routes.get_expert_agent", return_value=agent):
        response = client.post(
            "/api/v1/expert/clarify/rag",
            json={
                "message": "继续帮我细化分析角度",
                "previous_selections": [
                    {
                        "round": 1,
                        "selections": [
                            {
                                "option_id": "valuation",
                                "label": "A",
                                "title": "先看估值",
                                "focus": "估值、安全边际",
                                "skip": False,
                            }
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["should_clarify"] is True
    assert data["round"] == 2
    assert len(data["options"]) >= 3
    assert data["skip_option"]["id"] == "skip"
    assert data["multi_select"] is True


def _init_test_expert_db(
    db_path: Path,
    session_id: str = "session-1",
    expert_type: str = "data",
    session_user_id: str = "anonymous",
) -> None:
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA expert")
    con.execute(
        """
        CREATE TABLE expert.sessions (
            id VARCHAR PRIMARY KEY,
            expert_type VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            user_id VARCHAR DEFAULT 'anonymous',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE expert.messages (
            id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            role VARCHAR NOT NULL,
            content VARCHAR NOT NULL DEFAULT '',
            thinking JSON,
            status VARCHAR DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE expert.feedback_reports (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            session_id VARCHAR NOT NULL,
            message_id VARCHAR NOT NULL,
            expert_type VARCHAR NOT NULL,
            report_source VARCHAR NOT NULL,
            issue_type VARCHAR NOT NULL,
            user_note VARCHAR DEFAULT '',
            user_message VARCHAR NOT NULL,
            assistant_content VARCHAR NOT NULL,
            message_status VARCHAR DEFAULT 'completed',
            thinking_json JSON,
            context_json JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolver VARCHAR,
            resolution_note VARCHAR DEFAULT ''
        )
        """
    )
    con.execute(
        "INSERT INTO expert.sessions (id, expert_type, title, user_id) VALUES (?, ?, ?, ?)",
        [session_id, expert_type, "测试会话", session_user_id],
    )
    con.close()


async def _collect_stream_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


@pytest.mark.asyncio
async def test_expert_chat_persists_partial_message_when_stream_cancelled(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat.duckdb"
    session_id = "session-cancelled"
    _init_test_expert_db(db_path, session_id=session_id, expert_type="data")

    mock_expert = Mock()

    async def cancelled_stream(*args, **kwargs):
        yield {"event": "reply_token", "data": {"token": "半截内容"}}
        raise asyncio.CancelledError()

    mock_expert.chat = cancelled_stream

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        with patch.dict(routes_module._engine_experts, {"data": mock_expert}, clear=True):
            response = await routes_module.expert_chat_by_type(
                "data",
                ExpertChatRequest(message="测试中断保存", session_id=session_id),
            )

            with pytest.raises(asyncio.CancelledError):
                async for _chunk in response.body_iterator:
                    pass

    con = duckdb.connect(str(db_path))
    rows = con.execute(
        "SELECT role, content, status FROM expert.messages WHERE session_id = ? ORDER BY created_at",
        [session_id],
    ).fetchall()
    con.close()

    assert rows == [("expert", "半截内容", "partial")]


@pytest.mark.asyncio
async def test_data_expert_concept_question_routes_to_direct_reply_without_tool_chat():
    from engine.expert import routes as routes_module

    async def _direct_reply(message, history=None):
        assert message == "什么是市盈率？"
        assert history == []
        yield {"event": "reasoning_summary", "data": {"summary": "已切换到概念讲解模式"}}
        yield {"event": "reply_token", "data": {"token": "市盈率是股价与每股收益的比值。"}}
        yield {
            "event": "reply_complete",
            "data": {"full_text": "市盈率是股价与每股收益的比值。"},
        }

    mock_expert = Mock()
    mock_expert.direct_reply = Mock(side_effect=_direct_reply)
    mock_expert.chat = Mock(side_effect=AssertionError("概念问题不应进入工具分析链"))

    with patch.dict(routes_module._engine_experts, {"data": mock_expert}, clear=True):
        response = await routes_module.expert_chat_by_type(
            "data",
            ExpertChatRequest(message="什么是市盈率？"),
        )
        body = await _collect_stream_text(response)

    assert "concept_mode" in body or "概念讲解模式" in body
    assert mock_expert.direct_reply.call_count == 1
    assert mock_expert.chat.call_count == 0


@pytest.mark.asyncio
async def test_rag_concept_question_routes_to_direct_reply_without_analysis_chat():
    from engine.expert import routes as routes_module

    async def _direct_reply(message, history=None, persona="rag", images=None):
        assert message == "什么是市盈率？"
        assert history == []
        assert persona == "rag"
        assert images == []
        yield {"event": "reasoning_summary", "data": {"summary": "已切换到概念讲解模式"}}
        yield {"event": "reply_token", "data": {"token": "市盈率常用来衡量估值高低。"}}
        yield {
            "event": "reply_complete",
            "data": {"full_text": "市盈率常用来衡量估值高低。"},
        }

    mock_agent = Mock()
    mock_agent.direct_reply = Mock(side_effect=_direct_reply)
    mock_agent.chat = Mock(side_effect=AssertionError("概念问题不应进入 Agent 分析链"))

    with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
        response = await routes_module.expert_chat_by_type(
            "rag",
            ExpertChatRequest(message="什么是市盈率？"),
        )
        body = await _collect_stream_text(response)

    assert "concept_mode" in body or "概念讲解模式" in body
    assert mock_agent.direct_reply.call_count == 1
    assert mock_agent.chat.call_count == 0


@pytest.mark.asyncio
async def test_rag_stock_question_keeps_analysis_chat_path():
    from engine.expert import routes as routes_module

    async def _chat(*args, **kwargs):
        yield {"event": "reply_token", "data": {"token": "建议先看量价配合。"}}
        yield {"event": "reply_complete", "data": {"full_text": "建议先看量价配合。"}}

    mock_agent = Mock()
    mock_agent.direct_reply = Mock(side_effect=AssertionError("个股分析不应走概念直答"))
    mock_agent.chat = Mock(side_effect=_chat)

    with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
        response = await routes_module.expert_chat_by_type(
            "rag",
            ExpertChatRequest(message="宁德时代现在能买吗？"),
        )
        body = await _collect_stream_text(response)

    assert "建议先看量价配合" in body
    assert mock_agent.chat.call_count == 1
    assert mock_agent.direct_reply.call_count == 0


def test_learning_profile_endpoint_aggregates_reviews_memories_and_reflections(client):
    from engine.expert import routes as routes_module

    mock_service = Mock()
    mock_service.list_review_records = AsyncMock(return_value=[
        {"id": "rr-1", "status": "win", "pnl_pct": 0.08},
        {"id": "rr-2", "status": "loss", "pnl_pct": -0.03},
    ])
    mock_service.get_review_stats = AsyncMock(return_value={
        "portfolio_id": "paper-1",
        "days": 60,
        "total_reviews": 2,
        "win_count": 1,
        "loss_count": 1,
        "holding_count": 0,
        "win_rate": 0.5,
        "total_pnl_pct": 0.05,
        "avg_pnl_pct": 0.025,
    })
    mock_service.list_memories = AsyncMock(return_value=[
        {
            "id": "mem-1",
            "rule_text": "放量突破前先确认成交额质量",
            "category": "data_validation",
            "confidence": 0.82,
            "verify_count": 4,
            "verify_win": 3,
            "status": "active",
        },
        {
            "id": "mem-2",
            "rule_text": "逆势追高容易放大回撤",
            "category": "risk",
            "confidence": 0.9,
            "verify_count": 5,
            "verify_win": 4,
            "status": "active",
        },
    ])
    mock_service.list_reflections = AsyncMock(return_value=[
        {
            "id": "ref-1",
            "kind": "daily",
            "date": "2026-04-01",
            "summary": "当日复盘提示追涨动作过急。",
            "metrics": {"win_rate": 0.5, "total_pnl_pct": 0.02},
            "details": {},
        }
    ])
    mock_db = Mock()
    mock_db.execute_read = AsyncMock(side_effect=[
        [{"user_id": "alice"}],
        [{"total": 0}],
    ])

    with patch.object(routes_module, "_get_agent_service", return_value=mock_service, create=True):
        with patch.object(routes_module.AgentDB, "get_instance", return_value=mock_db):
            resp = client.get(
                "/api/v1/expert/learning/profile?expert_type=data&portfolio_id=paper-1&days=60",
                headers={"X-User-Id": "alice"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["portfolio_id"] == "paper-1"
    assert data["expert_type"] == "data"
    assert len(data["score_cards"]) == 5
    assert data["verified_knowledge"]
    assert data["recent_lessons"]
    assert data["common_mistakes"]
    assert data["source_summary"]["review_count"] == 2
    assert data["source_summary"]["memory_count"] == 2


def test_learning_profile_endpoint_reorders_verified_knowledge_by_expert_focus(client):
    from engine.expert import routes as routes_module

    mock_service = Mock()
    mock_service.list_review_records = AsyncMock(return_value=[])
    mock_service.get_review_stats = AsyncMock(return_value={
        "portfolio_id": "paper-1",
        "days": 30,
        "total_reviews": 0,
        "win_count": 0,
        "loss_count": 0,
        "holding_count": 0,
        "win_rate": 0.0,
        "total_pnl_pct": 0.0,
        "avg_pnl_pct": 0.0,
    })
    mock_service.list_memories = AsyncMock(return_value=[
        {
            "id": "mem-risk",
            "rule_text": "短线不能逆势追高",
            "category": "risk",
            "confidence": 0.91,
            "verify_count": 6,
            "verify_win": 5,
            "status": "active",
        },
        {
            "id": "mem-data",
            "rule_text": "成交额不够时先别把突破当确认",
            "category": "data_validation",
            "confidence": 0.84,
            "verify_count": 5,
            "verify_win": 4,
            "status": "active",
        },
    ])
    mock_service.list_reflections = AsyncMock(return_value=[])
    mock_db = Mock()
    mock_db.execute_read = AsyncMock(side_effect=[
        [{"user_id": "alice"}],
        [{"total": 0}],
        [{"user_id": "alice"}],
        [{"total": 0}],
    ])

    with patch.object(routes_module, "_get_agent_service", return_value=mock_service, create=True):
        with patch.object(routes_module.AgentDB, "get_instance", return_value=mock_db):
            data_resp = client.get(
                "/api/v1/expert/learning/profile?expert_type=data&portfolio_id=paper-1",
                headers={"X-User-Id": "alice"},
            )
            short_resp = client.get(
                "/api/v1/expert/learning/profile?expert_type=short_term&portfolio_id=paper-1",
                headers={"X-User-Id": "alice"},
            )

    assert data_resp.status_code == 200
    assert short_resp.status_code == 200
    assert data_resp.json()["verified_knowledge"][0]["id"] == "mem-data"
    assert short_resp.json()["verified_knowledge"][0]["id"] == "mem-risk"


def test_learning_profile_endpoint_forbids_non_owner_portfolio_access(client):
    from engine.expert import routes as routes_module

    mock_service = Mock()
    mock_service.list_review_records = AsyncMock(return_value=[])
    mock_service.get_review_stats = AsyncMock(return_value={
        "portfolio_id": "paper-1",
        "days": 30,
        "total_reviews": 0,
        "win_count": 0,
        "loss_count": 0,
        "holding_count": 0,
        "win_rate": 0.0,
        "total_pnl_pct": 0.0,
        "avg_pnl_pct": 0.0,
    })
    mock_service.list_memories = AsyncMock(return_value=[])
    mock_service.list_reflections = AsyncMock(return_value=[])

    mock_db = Mock()
    mock_db.execute_read = AsyncMock(return_value=[{"user_id": "bob"}])

    with patch.object(routes_module, "_get_agent_service", return_value=mock_service, create=True):
        with patch.object(routes_module.AgentDB, "get_instance", return_value=mock_db):
            resp = client.get(
                "/api/v1/expert/learning/profile?expert_type=data&portfolio_id=paper-1",
                headers={"X-User-Id": "alice"},
            )

    assert resp.status_code == 403
    mock_service.list_review_records.assert_not_awaited()
    mock_service.get_review_stats.assert_not_awaited()


def test_default_admin_is_bootstrapped(tmp_path):
    db_path = tmp_path / "users.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE users (
            user_id VARCHAR PRIMARY KEY,
            password_hash VARCHAR NOT NULL,
            display_name VARCHAR,
            created_at TIMESTAMP DEFAULT current_timestamp,
            last_login_at TIMESTAMP
        )
        """
    )
    con.close()

    class _Store:
        def __init__(self, conn):
            self._conn = conn

    auth_module = importlib.import_module("auth")
    conn = duckdb.connect(str(db_path))
    with patch.object(auth_module, "_get_store", return_value=_Store(conn)):
        auth_module.ensure_default_admin()
        auth_module.ensure_default_admin()
    rows = conn.execute(
        "SELECT user_id, display_name FROM users WHERE user_id = 'Admin'"
    ).fetchall()
    conn.close()
    assert rows == [("Admin", "Admin")]


def test_feedback_report_is_persisted_with_full_context(client, tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat.duckdb"
    session_id = "session-feedback"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-1", session_id, "原始用户问题"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, ?, 'partial')
        """,
        ["e-1", session_id, "半截回复", '[{"type":"tool_call","data":{"engine":"expert","action":"data"}}]'],
    )
    con.close()

    payload = {
        "session_id": session_id,
        "message_id": "e-1",
        "expert_type": "rag",
        "report_source": "reply",
        "issue_type": "llm_truncated",
        "user_note": "像是被截断了",
        "context": {
            "raw_error": "load failed",
            "history": [
                {"role": "user", "content": "原始用户问题"},
                {"role": "expert", "content": "半截回复"},
            ],
        },
    }

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        resp = client.post(
            "/api/v1/expert/feedback",
            json=payload,
            headers={"X-User-Id": "alice"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["feedback_id"]
    con2 = duckdb.connect(str(db_path))
    rows = con2.execute(
        """
        SELECT user_id, user_message, assistant_content, message_status, context_json
        FROM expert.feedback_reports WHERE id = ?
        """,
        [data["feedback_id"]],
    ).fetchall()
    con2.close()
    assert len(rows) == 1
    assert rows[0][0] == "alice"
    assert rows[0][1] == "原始用户问题"
    assert rows[0][2] == "半截回复"
    assert rows[0][3] == "partial"
    assert "load failed" in str(rows[0][4])


def test_feedback_submit_forbidden_for_non_owner_session(client, tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat.duckdb"
    session_id = "session-owner-locked"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-owner", session_id, "owner 用户问题"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, '[]', 'partial')
        """,
        ["e-owner", session_id, "owner 的专家回复"],
    )
    con.close()

    payload = {
        "session_id": session_id,
        "message_id": "e-owner",
        "expert_type": "rag",
        "report_source": "reply",
        "issue_type": "llm_truncated",
        "user_note": "非 owner 尝试提交",
        "context": {"raw_error": "permission denied"},
    }

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        resp = client.post(
            "/api/v1/expert/feedback",
            json=payload,
            headers={"X-User-Id": "bob"},
        )

    assert resp.status_code == 403

    con2 = duckdb.connect(str(db_path))
    count = con2.execute("SELECT COUNT(*) FROM expert.feedback_reports").fetchone()[0]
    con2.close()
    assert count == 0


def test_feedback_admin_endpoint_requires_admin_user(client, tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat.duckdb"
    _init_test_expert_db(db_path, session_id="session-admin", expert_type="rag")

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        resp = client.get(
            "/api/v1/expert/feedback/admin",
            headers={"X-User-Id": "bob"},
        )
    assert resp.status_code == 403


def test_feedback_routes_declare_response_models(client):
    route_map = {
        route.path: route
        for route in client.app.routes
        if isinstance(route, APIRoute)
    }

    assert route_map["/api/v1/expert/feedback"].response_model is not None
    assert route_map["/api/v1/expert/feedback/admin"].response_model is not None
    assert route_map["/api/v1/expert/feedback/admin/{feedback_id}"].response_model is not None
    assert route_map["/api/v1/expert/feedback/admin/{feedback_id}/resolve"].response_model is not None


def test_feedback_admin_endpoints_support_list_detail_and_resolve(client, tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat.duckdb"
    session_id = "session-admin-success"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-admin", session_id, "管理员排查问题"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, ?, 'partial')
        """,
        ["e-admin", session_id, "管理员看到的半截回复", '[{"type":"tool_call","data":{"engine":"expert","action":"data"}}]'],
    )
    con.close()

    payload = {
        "session_id": session_id,
        "message_id": "e-admin",
        "expert_type": "rag",
        "report_source": "reply",
        "issue_type": "load_failed",
        "user_note": "管理后台回归",
        "context": {"raw_error": "load failed"},
    }

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        create_resp = client.post(
            "/api/v1/expert/feedback",
            json=payload,
            headers={"X-User-Id": "alice"},
        )
        assert create_resp.status_code == 200
        feedback_id = create_resp.json()["feedback_id"]

        list_resp = client.get(
            "/api/v1/expert/feedback/admin",
            headers={"X-User-Id": "Admin"},
        )
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data) == 1
        assert list_data[0]["id"] == feedback_id
        assert list_data[0]["issue_type"] == "load_failed"

        detail_resp = client.get(
            f"/api/v1/expert/feedback/admin/{feedback_id}",
            headers={"X-User-Id": "Admin"},
        )
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["id"] == feedback_id
        assert detail_data["assistant_content"] == "管理员看到的半截回复"
        assert detail_data["context_json"]["raw_error"] == "load failed"

        resolve_resp = client.post(
            f"/api/v1/expert/feedback/admin/{feedback_id}/resolve",
            json={"resolution_note": "已处理"},
            headers={"X-User-Id": "Admin"},
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["ok"] is True

    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT resolver, resolution_note, resolved_at FROM expert.feedback_reports WHERE id = ?",
        [feedback_id],
    ).fetchone()
    con2.close()
    assert row[0] == "Admin"
    assert row[1] == "已处理"
    assert row[2] is not None


@pytest.mark.asyncio
async def test_feedback_route_functions_return_response_models(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat.duckdb"
    session_id = "session-model-types"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-model", session_id, "模型类型校验问题"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, ?, 'partial')
        """,
        ["e-model", session_id, "模型类型校验半截回复", '[{"type":"tool_call","data":{"engine":"expert","action":"data"}}]'],
    )
    con.close()

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        submit_resp = await routes_module.submit_feedback(
            FeedbackReportCreateRequest(
                session_id=session_id,
                message_id="e-model",
                expert_type="rag",
                report_source="reply",
                issue_type="llm_truncated",
                user_note="类型测试",
                context={"raw_error": "load failed"},
            ),
            user_id="alice",
        )
        assert isinstance(submit_resp, FeedbackSubmitResponse)
        assert submit_resp.feedback_id

        list_resp = await routes_module.list_feedback_reports(
            unresolved_only=True,
            limit=10,
            user_id="Admin",
        )
        assert isinstance(list_resp, list)
        assert list_resp
        assert isinstance(list_resp[0], FeedbackReportSummary)
        feedback_id = list_resp[0].id

        detail_resp = await routes_module.get_feedback_report(
            feedback_id=feedback_id,
            user_id="Admin",
        )
        assert isinstance(detail_resp, FeedbackReportDetail)
        assert detail_resp.assistant_content == "模型类型校验半截回复"

        resolve_resp = await routes_module.resolve_feedback_report(
            feedback_id=feedback_id,
            req=FeedbackResolveRequest(resolution_note="已核实"),
            user_id="Admin",
        )
        assert isinstance(resolve_resp, FeedbackResolveResponse)
        assert resolve_resp.ok is True


@pytest.mark.asyncio
async def test_resume_marks_message_completed_when_completion_check_says_complete(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat_resume_complete.duckdb"
    session_id = "session-resume-complete"
    message_id = "e-resume-complete"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-resume-complete", session_id, "这个回复是不是已经完整了？"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, '[]', 'partial')
        """,
        [message_id, session_id, "结论：继续持有，等待业绩验证。"],
    )
    con.close()

    async def _unexpected_resume_reply(*args, **kwargs):
        yield {"event": "resume_complete", "data": {"continuation": "不应该被续写"}}

    mock_agent = Mock()
    mock_agent.check_resume_completion = AsyncMock(return_value={
        "is_complete": True,
        "reason": "末尾已经是完整结论",
        "confidence": 0.96,
    })
    mock_agent.resume_reply = Mock(side_effect=_unexpected_resume_reply)

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
            response = await routes_module.expert_chat_resume(
                ExpertResumeRequest(session_id=session_id, message_id=message_id)
            )
            async for _ in response.body_iterator:
                pass

    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT content, status FROM expert.messages WHERE id = ?",
        [message_id],
    ).fetchone()
    con2.close()

    assert row == ("结论：继续持有，等待业绩验证。", "completed")
    mock_agent.check_resume_completion.assert_awaited_once()
    assert mock_agent.resume_reply.call_count == 0


@pytest.mark.asyncio
async def test_resume_calls_resume_reply_when_completion_check_says_incomplete(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat_resume_incomplete.duckdb"
    session_id = "session-resume-incomplete"
    message_id = "e-resume-incomplete"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-resume-incomplete", session_id, "这段回复没写完，帮我续上"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, '[]', 'partial')
        """,
        [message_id, session_id, "结论：短期看震荡，"],
    )
    con.close()

    async def _resume_reply(*args, **kwargs):
        yield {"event": "resume_token", "data": {"token": "建议等待回踩确认后再分批。"}}
        yield {"event": "resume_complete", "data": {"continuation": "建议等待回踩确认后再分批。"}}

    mock_agent = Mock()
    mock_agent.check_resume_completion = AsyncMock(return_value={
        "is_complete": False,
        "reason": "句子未结束",
        "confidence": 0.95,
    })
    mock_agent.resume_reply = Mock(side_effect=_resume_reply)

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
            response = await routes_module.expert_chat_resume(
                ExpertResumeRequest(session_id=session_id, message_id=message_id)
            )
            async for _ in response.body_iterator:
                pass

    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT content, status FROM expert.messages WHERE id = ?",
        [message_id],
    ).fetchone()
    con2.close()

    assert row == ("结论：短期看震荡，建议等待回踩确认后再分批。", "completed")
    mock_agent.check_resume_completion.assert_awaited_once()
    assert mock_agent.resume_reply.call_count == 1


@pytest.mark.asyncio
async def test_resume_completed_message_with_check_completed_marks_completed_when_check_says_complete(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat_resume_completed_check_complete.duckdb"
    session_id = "session-resume-completed-check-complete"
    message_id = "e-resume-completed-check-complete"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-resume-completed-check-complete", session_id, "这条完成状态消息是不是已经完整？"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, '[]', 'completed')
        """,
        [message_id, session_id, "结论：业绩与估值匹配，继续跟踪即可。"],
    )
    con.close()

    async def _unexpected_resume_reply(*args, **kwargs):
        yield {"event": "resume_complete", "data": {"continuation": "不应该续写"}}

    mock_agent = Mock()
    mock_agent.check_resume_completion = AsyncMock(return_value={
        "is_complete": True,
        "reason": "内容完整",
        "confidence": 0.97,
        "check_failed": False,
    })
    mock_agent.resume_reply = Mock(side_effect=_unexpected_resume_reply)

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
            response = await routes_module.expert_chat_resume(
                ExpertResumeRequest(session_id=session_id, message_id=message_id, check_completed=True)
            )
            stream_text = await _collect_stream_text(response)

    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT content, status FROM expert.messages WHERE id = ?",
        [message_id],
    ).fetchone()
    con2.close()

    assert "event: resume_completion_check" in stream_text
    assert "event: resume_complete" in stream_text
    assert row == ("结论：业绩与估值匹配，继续跟踪即可。", "completed")
    mock_agent.check_resume_completion.assert_awaited_once()
    assert mock_agent.resume_reply.call_count == 0


@pytest.mark.asyncio
async def test_resume_completed_message_with_check_completed_calls_resume_when_check_says_incomplete(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat_resume_completed_check_incomplete.duckdb"
    session_id = "session-resume-completed-check-incomplete"
    message_id = "e-resume-completed-check-incomplete"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-resume-completed-check-incomplete", session_id, "这条是不是被截断了？"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, '[]', 'completed')
        """,
        [message_id, session_id, "结论：关注成交量放大后，"],
    )
    con.close()

    async def _resume_reply(*args, **kwargs):
        yield {"event": "resume_token", "data": {"token": "再考虑加仓。"}}
        yield {"event": "resume_complete", "data": {"continuation": "再考虑加仓。"}}

    mock_agent = Mock()
    mock_agent.check_resume_completion = AsyncMock(return_value={
        "is_complete": False,
        "reason": "末尾语义未闭合",
        "confidence": 0.93,
        "check_failed": False,
    })
    mock_agent.resume_reply = Mock(side_effect=_resume_reply)

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
            response = await routes_module.expert_chat_resume(
                ExpertResumeRequest(session_id=session_id, message_id=message_id, check_completed=True)
            )
            await _collect_stream_text(response)

    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT content, status FROM expert.messages WHERE id = ?",
        [message_id],
    ).fetchone()
    con2.close()

    assert row == ("结论：关注成交量放大后，再考虑加仓。", "completed")
    mock_agent.check_resume_completion.assert_awaited_once()
    assert mock_agent.resume_reply.call_count == 1


@pytest.mark.asyncio
async def test_resume_keeps_original_message_when_completion_check_failed(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat_resume_check_failed.duckdb"
    session_id = "session-resume-check-failed"
    message_id = "e-resume-check-failed"
    original_content = "结论：短线关注量价配合，若"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        ["u-resume-check-failed", session_id, "这段是不是断了？"],
    )
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'expert', ?, '[]', 'partial')
        """,
        [message_id, session_id, original_content],
    )
    con.close()

    async def _unexpected_resume_reply(*args, **kwargs):
        yield {"event": "resume_complete", "data": {"continuation": "不应该续写"}}

    mock_agent = Mock()
    mock_agent.check_resume_completion = AsyncMock(return_value={
        "is_complete": False,
        "reason": "完整性检查失败，模型返回内容无法解析",
        "confidence": 0.0,
        "check_failed": True,
    })
    mock_agent.resume_reply = Mock(side_effect=_unexpected_resume_reply)

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
            response = await routes_module.expert_chat_resume(
                ExpertResumeRequest(session_id=session_id, message_id=message_id)
            )
            stream_text = await _collect_stream_text(response)

    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT content, status FROM expert.messages WHERE id = ?",
        [message_id],
    ).fetchone()
    con2.close()

    assert "event: resume_completion_check" in stream_text
    assert "event: error" in stream_text
    assert "完整性检查失败" in stream_text
    assert row == (original_content, "partial")
    mock_agent.check_resume_completion.assert_awaited_once()
    assert mock_agent.resume_reply.call_count == 0


@pytest.mark.asyncio
async def test_resume_rejects_completed_non_expert_message_even_with_check_completed(tmp_path):
    from engine.expert import routes as routes_module

    db_path = tmp_path / "expert_chat_resume_non_expert_completed.duckdb"
    session_id = "session-resume-non-expert-completed"
    message_id = "u-completed-message"
    _init_test_expert_db(
        db_path,
        session_id=session_id,
        expert_type="rag",
        session_user_id="alice",
    )
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        INSERT INTO expert.messages (id, session_id, role, content, thinking, status)
        VALUES (?, ?, 'user', ?, '[]', 'completed')
        """,
        [message_id, session_id, "我是用户消息，不应进入续写"],
    )
    con.close()

    mock_agent = Mock()
    mock_agent.check_resume_completion = AsyncMock(return_value={
        "is_complete": False,
        "reason": "不应执行",
        "confidence": 0.0,
        "check_failed": False,
    })
    mock_agent.resume_reply = Mock()

    with patch.object(routes_module, "_get_db", side_effect=lambda: duckdb.connect(str(db_path))):
        with patch.object(routes_module, "get_expert_agent", return_value=mock_agent):
            response = await routes_module.expert_chat_resume(
                ExpertResumeRequest(session_id=session_id, message_id=message_id, check_completed=True)
            )
            stream_text = await _collect_stream_text(response)

    assert "event: error" in stream_text
    assert "仅支持续写 expert 消息" in stream_text
    assert mock_agent.check_resume_completion.await_count == 0
    assert mock_agent.resume_reply.call_count == 0
