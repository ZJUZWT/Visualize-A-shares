import json
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
    from main import app
    return TestClient(app)

def test_history_returns_list(client):
    resp = client.get("/api/v1/debate/history?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

def test_history_item_schema(client):
    """如果有记录，验证字段结构"""
    resp = client.get("/api/v1/debate/history?limit=1")
    data = resp.json()
    if data:
        item = data[0]
        assert "debate_id" in item
        assert "target" in item
        assert "created_at" in item

def test_replay_not_found(client):
    resp = client.get("/api/v1/debate/nonexistent_id")
    assert resp.status_code == 404

def test_replay_schema(client):
    """先查 history，再用第一条 id 查 replay"""
    hist = client.get("/api/v1/debate/history?limit=1").json()
    if not hist:
        pytest.skip("无辩论记录，跳过")
    debate_id = hist[0]["debate_id"]
    resp = client.get(f"/api/v1/debate/{debate_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "blackboard_json" in data
    assert "judge_verdict_json" in data
