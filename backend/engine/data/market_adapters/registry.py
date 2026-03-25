from __future__ import annotations

from .cn_adapter import CNMarketAdapter
from .fund_adapter import FundMarketAdapter
from .futures_adapter import FuturesMarketAdapter
from .hk_adapter import HKMarketAdapter
from .us_adapter import USMarketAdapter


class MarketAdapterRegistry:
    def __init__(self, data_engine):
        self._adapters = {
            "cn": CNMarketAdapter(data_engine),
            "hk": HKMarketAdapter(),
            "us": USMarketAdapter(),
            "fund": FundMarketAdapter(),
            "futures": FuturesMarketAdapter(),
        }

    def get(self, market: str):
        key = (market or "cn").lower()
        if key not in self._adapters:
            raise ValueError(f"Unsupported market: {market}")
        return self._adapters[key]

    def list_adapters(self):
        return list(self._adapters.values())
