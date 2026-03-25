from unittest.mock import Mock, patch

from engine.expert.tools import ExpertTools


def test_expert_tools_search_asset_uses_unified_data_methods():
    data_engine = Mock()
    data_engine.search_assets.return_value = [
        {"market": "us", "symbol": "AAPL", "name": "Apple"}
    ]
    tools = ExpertTools(data_engine=data_engine, cluster_engine=None, llm_engine=None)

    result = tools._call_data_engine("search_asset", {"query": "AAPL", "market": "us"})

    assert result["results"][0]["market"] == "us"


def test_expert_tools_bridge_market_assets_uses_industry_engine():
    tools = ExpertTools(data_engine=Mock(), cluster_engine=None, llm_engine=None)

    class FakeIndustryEngine:
        def bridge_market_assets(self, target, market="", limit=10):
            return {
                "target_asset": {"market": "cn", "symbol": target},
                "bridge_type": "industry",
                "reason": "主题映射",
                "related_assets": [{"market": "hk", "symbol": "00700"}],
            }

    with patch("engine.expert.tools.get_industry_engine", return_value=FakeIndustryEngine()):
        result = tools._call_bridge_market_assets({"target": "新能源", "market": "cn"})

    assert result["bridge_type"] == "industry"
