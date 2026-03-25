from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_cross_market_bridge_returns_related_assets():
    from engine.industry.market_bridge import CrossMarketBridge

    bridge = CrossMarketBridge()
    result = bridge.bridge("新能源", market="cn")

    assert result["bridge_type"] in {"industry", "proxy", "chain"}
    assert len(result["related_assets"]) > 0


def test_industry_bridge_route_returns_structured_results():
    from engine.industry.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    class FakeIndustryEngine:
        def bridge_market_assets(self, target, market="", limit=10):
            return {
                "target_asset": {"market": "cn", "symbol": target},
                "bridge_type": "industry",
                "reason": "主题映射",
                "related_assets": [{"market": "us", "symbol": "TSLA"}],
            }

    with patch("engine.industry.get_industry_engine", return_value=FakeIndustryEngine()):
        resp = client.get("/api/v1/industry/bridge/新能源?market=cn")

    assert resp.status_code == 200
    assert resp.json()["bridge_type"] == "industry"
