from __future__ import annotations

import pandas as pd

from .base import BaseMarketAdapter


class USMarketAdapter(BaseMarketAdapter):
    market = "us"

    def _get_yfinance(self):
        import yfinance as yf  # type: ignore
        return yf

    def search(self, query: str, limit: int = 20) -> list[dict]:
        if not query:
            return []
        return [{"market": "us", "asset_type": "stock", "symbol": query.upper(), "name": query.upper()}]

    def get_profile(self, symbol: str) -> dict:
        try:
            yf = self._get_yfinance()
            ticker = yf.Ticker(symbol)
            info = getattr(ticker, "info", {}) or {}
            return {
                "market": "us",
                "asset_type": "stock",
                "symbol": symbol.upper(),
                "name": info.get("shortName", symbol.upper()),
                "industry": info.get("industry", ""),
                "profile": info,
            }
        except Exception as e:
            return {"market": "us", "asset_type": "stock", "symbol": symbol.upper(), "error": str(e)}

    def get_quote(self, symbol: str) -> dict:
        try:
            yf = self._get_yfinance()
            ticker = yf.Ticker(symbol)
            info = getattr(ticker, "info", {}) or {}
            return {
                "market": "us",
                "asset_type": "stock",
                "symbol": symbol.upper(),
                "price": info.get("regularMarketPrice"),
                "pct_chg": info.get("regularMarketChangePercent"),
                "name": info.get("shortName", symbol.upper()),
            }
        except Exception as e:
            return {"market": "us", "asset_type": "stock", "symbol": symbol.upper(), "error": str(e)}

    def get_daily_history(self, symbol: str, start: str, end: str) -> dict:
        try:
            yf = self._get_yfinance()
            history = yf.Ticker(symbol).history(start=start, end=end)
            if history is None or getattr(history, "empty", False):
                return {"market": "us", "asset_type": "stock", "symbol": symbol.upper(), "records": [], "count": 0}
            df = history.reset_index()
            records = df.to_dict("records") if isinstance(df, pd.DataFrame) else []
            return {"market": "us", "asset_type": "stock", "symbol": symbol.upper(), "records": records, "count": len(records)}
        except Exception as e:
            return {"market": "us", "asset_type": "stock", "symbol": symbol.upper(), "records": [], "count": 0, "error": str(e)}
