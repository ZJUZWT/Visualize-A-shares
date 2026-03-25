from __future__ import annotations

from .base import BaseMarketAdapter


class FundMarketAdapter(BaseMarketAdapter):
    market = "fund"

    def _get_akshare(self):
        import akshare as ak  # type: ignore
        return ak

    def search(self, query: str, limit: int = 20) -> list[dict]:
        return [{"market": "fund", "asset_type": "fund", "symbol": query, "name": query}] if query else []

    def get_profile(self, symbol: str) -> dict:
        return {"market": "fund", "asset_type": "fund", "symbol": symbol, "name": symbol}

    def get_quote(self, symbol: str) -> dict:
        try:
            ak = self._get_akshare()
            df = ak.fund_open_fund_daily_em()
            row = df[df.iloc[:, 0].astype(str) == str(symbol)]
            if row.empty:
                return {"market": "fund", "asset_type": "fund", "symbol": symbol, "error": f"Quote not found for {symbol}"}
            return {"market": "fund", "asset_type": "fund", "symbol": symbol, "raw": row.iloc[0].to_dict()}
        except Exception as e:
            return {"market": "fund", "asset_type": "fund", "symbol": symbol, "error": str(e)}

    def get_daily_history(self, symbol: str, start: str, end: str) -> dict:
        try:
            ak = self._get_akshare()
            df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
            records = df.to_dict("records")
            return {"market": "fund", "asset_type": "fund", "symbol": symbol, "records": records, "count": len(records)}
        except Exception as e:
            return {"market": "fund", "asset_type": "fund", "symbol": symbol, "records": [], "count": 0, "error": str(e)}
