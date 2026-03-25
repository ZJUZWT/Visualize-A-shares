from __future__ import annotations

import pandas as pd

from .base import BaseMarketAdapter


class CNMarketAdapter(BaseMarketAdapter):
    market = "cn"

    def __init__(self, data_engine):
        self._data = data_engine

    def search(self, query: str, limit: int = 20) -> list[dict]:
        profiles = self._data.get_profiles()
        q = (query or "").lower()
        results = []
        for code, item in profiles.items():
            name = item.get("name", "")
            if q in code.lower() or q in name.lower() or q in item.get("industry", "").lower():
                results.append({
                    "market": "cn",
                    "asset_type": "stock",
                    "symbol": code,
                    "name": name,
                    "industry": item.get("industry", ""),
                })
            if len(results) >= limit:
                break
        return results

    def get_profile(self, symbol: str) -> dict:
        profile = self._data.get_profile(symbol) or {}
        return {
            "market": "cn",
            "asset_type": "stock",
            "symbol": symbol,
            "name": profile.get("name", symbol),
            "industry": profile.get("industry", ""),
            "profile": profile,
        }

    def get_quote(self, symbol: str) -> dict:
        snapshot = self._data.get_snapshot()
        if snapshot is None or getattr(snapshot, "empty", False):
            return {"market": "cn", "asset_type": "stock", "symbol": symbol, "error": "No snapshot data"}
        row = snapshot[snapshot["code"].astype(str) == str(symbol)]
        if row.empty:
            return {"market": "cn", "asset_type": "stock", "symbol": symbol, "error": f"Quote not found for {symbol}"}
        item = row.iloc[0].to_dict()
        return {
            "market": "cn",
            "asset_type": "stock",
            "symbol": symbol,
            "name": item.get("name", symbol),
            "price": float(item.get("price", 0) or 0),
            "pct_chg": float(item.get("pct_chg", 0) or 0),
            "raw": item,
        }

    def get_daily_history(self, symbol: str, start: str, end: str) -> dict:
        df = self._data.get_daily_history(symbol, start, end)
        if df is None or getattr(df, "empty", False):
            return {"market": "cn", "asset_type": "stock", "symbol": symbol, "records": [], "count": 0}
        if isinstance(df, pd.DataFrame):
            records = df.to_dict("records")
        else:
            records = []
        return {"market": "cn", "asset_type": "stock", "symbol": symbol, "records": records, "count": len(records)}
