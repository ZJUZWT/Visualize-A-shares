from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch


def _make_client():
    from engine.data.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_assets_search_route_returns_results():
    client = _make_client()

    class FakeDataEngine:
        def search_assets(self, query, market="all", limit=20):
            return [{"market": "hk", "symbol": "00700", "name": "腾讯控股"}]

    with patch("engine.data.routes.get_data_engine", return_value=FakeDataEngine()):
        resp = client.get("/api/v1/data/assets/search?q=腾讯&market=hk")

    assert resp.status_code == 200
    assert resp.json()["results"][0]["market"] == "hk"


def test_assets_profile_route_returns_profile():
    client = _make_client()

    class FakeDataEngine:
        def get_asset_profile(self, symbol, market):
            return {"market": market, "symbol": symbol, "name": "Apple"}

    with patch("engine.data.routes.get_data_engine", return_value=FakeDataEngine()):
        resp = client.get("/api/v1/data/assets/profile?symbol=AAPL&market=us")

    assert resp.status_code == 200
    assert resp.json()["market"] == "us"
