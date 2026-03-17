"""分析 API SSE 端点测试"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def test_client():
    """FastAPI TestClient"""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def test_analysis_endpoint_exists(test_client):
    """确认 /api/v1/analysis 路由已注册"""
    # POST 无 body 应该返回 422（参数验证失败），而非 404
    resp = test_client.post("/api/v1/analysis")
    assert resp.status_code != 404
