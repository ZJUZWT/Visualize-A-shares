"""跨市场桥接规则。"""

from __future__ import annotations


class CrossMarketBridge:
    _RULES = {
        "新能源": {
            "bridge_type": "industry",
            "reason": "新能源主题在中美港市场均有高相关资产",
            "related_assets": [
                {"market": "hk", "asset_type": "stock", "symbol": "00968", "name": "信义光能"},
                {"market": "us", "asset_type": "stock", "symbol": "TSLA", "name": "Tesla"},
                {"market": "fund", "asset_type": "fund", "symbol": "161028", "name": "新能源主题基金"},
            ],
        },
        "原油": {
            "bridge_type": "chain",
            "reason": "原油价格通过化工与能源链条传导到股票与ETF",
            "related_assets": [
                {"market": "futures", "asset_type": "future", "symbol": "SC", "name": "原油期货"},
                {"market": "cn", "asset_type": "stock", "symbol": "600028", "name": "中国石化"},
                {"market": "us", "asset_type": "stock", "symbol": "XOM", "name": "Exxon Mobil"},
            ],
        },
        "黄金": {
            "bridge_type": "proxy",
            "reason": "黄金命题通常由期货、贵金属股和海外黄金ETF共同表达",
            "related_assets": [
                {"market": "futures", "asset_type": "future", "symbol": "AU", "name": "沪金"},
                {"market": "cn", "asset_type": "stock", "symbol": "600489", "name": "中金黄金"},
                {"market": "us", "asset_type": "stock", "symbol": "GLD", "name": "SPDR Gold Shares"},
            ],
        },
    }

    def bridge(self, target: str, market: str = "", limit: int = 10) -> dict:
        key = (target or "").strip()
        for theme, payload in self._RULES.items():
            if theme in key or key in theme:
                return {
                    "target_asset": {"market": market or "cn", "symbol": target},
                    "bridge_type": payload["bridge_type"],
                    "reason": payload["reason"],
                    "related_assets": payload["related_assets"][:limit],
                }
        return {
            "target_asset": {"market": market or "cn", "symbol": target},
            "bridge_type": "industry",
            "reason": "未命中显式规则，返回空桥接结果",
            "related_assets": [],
        }
