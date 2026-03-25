from unittest.mock import Mock


def test_data_engine_search_assets_dispatches_to_registry():
    from engine.data.engine import DataEngine

    engine = DataEngine.__new__(DataEngine)
    engine._resolver = Mock()
    engine._market_registry = Mock()

    cn_adapter = Mock()
    hk_adapter = Mock()
    cn_adapter.search.return_value = [{"market": "cn", "symbol": "600519"}]
    hk_adapter.search.return_value = [{"market": "hk", "symbol": "00700"}]
    engine._market_registry.list_adapters.return_value = [cn_adapter, hk_adapter]

    results = engine.search_assets("腾讯", market="all", limit=10)

    assert len(results) == 2
    assert {item["market"] for item in results} == {"cn", "hk"}


def test_data_engine_get_asset_profile_uses_specific_adapter():
    from engine.data.engine import DataEngine

    engine = DataEngine.__new__(DataEngine)
    engine._market_registry = Mock()
    adapter = Mock()
    adapter.get_profile.return_value = {"market": "us", "symbol": "AAPL", "name": "Apple"}
    engine._market_registry.get.return_value = adapter

    result = engine.get_asset_profile("AAPL", "us")

    assert result["market"] == "us"
    adapter.get_profile.assert_called_once_with("AAPL")
