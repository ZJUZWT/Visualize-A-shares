from unittest.mock import Mock

import pandas as pd


def test_market_registry_returns_expected_adapters():
    from engine.data.market_adapters.registry import MarketAdapterRegistry

    registry = MarketAdapterRegistry(data_engine=Mock())

    assert registry.get("cn").market == "cn"
    assert registry.get("hk").market == "hk"
    assert registry.get("us").market == "us"
    assert registry.get("fund").market == "fund"
    assert registry.get("futures").market == "futures"


def test_cn_adapter_uses_existing_data_engine_contract():
    from engine.data.market_adapters.cn_adapter import CNMarketAdapter

    data_engine = Mock()
    data_engine.get_profile.return_value = {"code": "600519", "name": "贵州茅台", "industry": "饮料制造"}
    data_engine.get_snapshot.return_value = pd.DataFrame([
        {"code": "600519", "name": "贵州茅台", "price": 1700.0, "pct_chg": 1.2}
    ])
    data_engine.get_daily_history.return_value = pd.DataFrame([
        {"date": "2026-03-20", "close": 1688.0},
        {"date": "2026-03-23", "close": 1700.0},
    ])
    data_engine.get_profiles.return_value = {"600519": {"code": "600519", "name": "贵州茅台", "industry": "饮料制造"}}

    adapter = CNMarketAdapter(data_engine)

    profile = adapter.get_profile("600519")
    quote = adapter.get_quote("600519")
    history = adapter.get_daily_history("600519", "2026-03-01", "2026-03-24")

    assert profile["market"] == "cn"
    assert quote["symbol"] == "600519"
    assert len(history["records"]) == 2


def test_us_adapter_gracefully_degrades_when_dependency_missing(monkeypatch):
    from engine.data.market_adapters.us_adapter import USMarketAdapter

    adapter = USMarketAdapter()

    monkeypatch.setattr(adapter, "_get_yfinance", lambda: (_ for _ in ()).throw(ModuleNotFoundError("yfinance")))

    result = adapter.get_quote("AAPL")

    assert result["market"] == "us"
    assert "error" in result
