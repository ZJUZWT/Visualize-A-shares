"""路由测试"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock

from engine.expert.routes import router, _init_db, get_expert_agent
from engine.expert.schemas import ExpertChatRequest


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
        )
