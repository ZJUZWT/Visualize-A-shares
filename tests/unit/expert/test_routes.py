"""路由测试"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

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
