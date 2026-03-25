from __future__ import annotations

from .base import BaseMarketAdapter


class FuturesMarketAdapter(BaseMarketAdapter):
    market = "futures"

    def _get_akshare(self):
        import akshare as ak  # type: ignore
        return ak

    def search(self, query: str, limit: int = 20) -> list[dict]:
        return [{"market": "futures", "asset_type": "future", "symbol": query.upper(), "name": query.upper()}] if query else []

    def get_profile(self, symbol: str) -> dict:
        return {"market": "futures", "asset_type": "future", "symbol": symbol.upper(), "name": symbol.upper()}

    def get_quote(self, symbol: str) -> dict:
        try:
            ak = self._get_akshare()
            df = ak.futures_zh_spot(symbol=symbol.upper(), market="CF", adjust=False)
            if df is None or getattr(df, "empty", False):
                return {"market": "futures", "asset_type": "future", "symbol": symbol.upper(), "error": f"Quote not found for {symbol}"}
            return {"market": "futures", "asset_type": "future", "symbol": symbol.upper(), "raw": df.iloc[0].to_dict()}
        except Exception as e:
            return {"market": "futures", "asset_type": "future", "symbol": symbol.upper(), "error": str(e)}

    def get_daily_history(self, symbol: str, start: str, end: str) -> dict:
        try:
            ak = self._get_akshare()
            df = ak.get_futures_daily(start_date=start.replace("-", ""), end_date=end.replace("-", ""), market="SHFE")
            records = df.to_dict("records")
            return {"market": "futures", "asset_type": "future", "symbol": symbol.upper(), "records": records, "count": len(records)}
        except Exception as e:
            return {"market": "futures", "asset_type": "future", "symbol": symbol.upper(), "records": [], "count": 0, "error": str(e)}
