"""量化引擎 — REST API 测试"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


@pytest.fixture
def app():
    """创建测试 FastAPI 应用"""
    from quant_engine.routes import router
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestQuantHealth:
    def test_health(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            mock_qe = MagicMock()
            mock_qe.health_check.return_value = {
                "status": "ok",
                "predictor": "v2.0",
                "factor_count": 13,
                "weight_source": "default",
            }
            mock_get.return_value = mock_qe
            resp = client.get("/api/v1/quant/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


class TestFactorWeights:
    def test_get_weights(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            mock_qe = MagicMock()
            mock_qe.get_factor_weights.return_value = ({"reversal": 0.15}, "default")
            mock_qe.get_factor_defs.return_value = []
            mock_get.return_value = mock_qe
            resp = client.get("/api/v1/quant/factor/weights")
            assert resp.status_code == 200
            assert resp.json()["weight_source"] == "default"


class TestIndicators:
    def test_get_indicators(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get, \
             patch("quant_engine.routes.get_data_engine") as mock_data:
            mock_qe = MagicMock()
            mock_qe.compute_indicators.return_value = {"rsi_14": 55.0, "macd": 0.5}
            mock_get.return_value = mock_qe

            import pandas as pd
            mock_de = MagicMock()
            mock_de.get_daily_history.return_value = pd.DataFrame({
                "close": [10, 11, 12],
                "high": [10.5, 11.5, 12.5],
                "low": [9.5, 10.5, 11.5],
                "pct_chg": [0, 10, 9],
            })
            mock_data.return_value = mock_de

            resp = client.get("/api/v1/quant/indicators/000001")
            assert resp.status_code == 200
            assert "rsi_14" in resp.json()["indicators"]

    def test_get_indicators_not_found(self, client):
        """股票无日线数据时返回 404"""
        with patch("quant_engine.routes.get_quant_engine") as mock_get, \
             patch("quant_engine.routes.get_data_engine") as mock_data:
            import pandas as pd
            mock_de = MagicMock()
            mock_de.get_daily_history.return_value = pd.DataFrame()
            mock_data.return_value = mock_de
            mock_get.return_value = MagicMock()

            resp = client.get("/api/v1/quant/indicators/999999")
            assert resp.status_code == 404


class TestBacktest:
    def test_run_backtest(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            mock_qe = MagicMock()
            mock_result = MagicMock()
            mock_result.backtest_days = 10
            mock_result.total_stocks_avg = 500
            mock_result.computation_time_ms = 123.4
            mock_result.icir_weights = {"reversal": 0.2}
            mock_result.factor_reports = {}
            mock_qe.run_backtest.return_value = mock_result
            mock_get.return_value = mock_qe

            resp = client.post("/api/v1/quant/factor/backtest?rolling_window=20")
            assert resp.status_code == 200
            assert resp.json()["backtest_days"] == 10
            assert resp.json()["weights_injected"] is True


class TestFactorDefs:
    def test_get_defs(self, client):
        with patch("quant_engine.routes.get_quant_engine") as mock_get:
            from quant_engine.predictor import FactorDef
            mock_qe = MagicMock()
            mock_qe.get_factor_defs.return_value = [
                FactorDef("test_factor", "col", 1, "group", 0.1, "测试因子")
            ]
            mock_get.return_value = mock_qe

            resp = client.get("/api/v1/quant/factor/defs")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
            assert resp.json()[0]["name"] == "test_factor"
