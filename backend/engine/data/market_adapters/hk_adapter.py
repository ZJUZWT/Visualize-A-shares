from __future__ import annotations

import pandas as pd

from .base import BaseMarketAdapter


class HKMarketAdapter(BaseMarketAdapter):
    market = "hk"

    def _get_akshare(self):
        import akshare as ak  # type: ignore
        return ak

    def search(self, query: str, limit: int = 20) -> list[dict]:
        return [{"market": "hk", "asset_type": "stock", "symbol": query.upper(), "name": query}] if query else []

    def get_profile(self, symbol: str) -> dict:
        return {"market": "hk", "asset_type": "stock", "symbol": symbol, "name": symbol}

    def get_quote(self, symbol: str) -> dict:
        try:
            ak = self._get_akshare()
            df = ak.stock_hk_spot_em()
            row = df[df.iloc[:, 1].astype(str) == str(symbol)]
            if row.empty:
                return {"market": "hk", "asset_type": "stock", "symbol": symbol, "error": f"Quote not found for {symbol}"}
            item = row.iloc[0].to_dict()
            return {"market": "hk", "asset_type": "stock", "symbol": symbol, "raw": item}
        except Exception as e:
            return {"market": "hk", "asset_type": "stock", "symbol": symbol, "error": str(e)}

    def get_daily_history(self, symbol: str, start: str, end: str) -> dict:
        try:
            ak = self._get_akshare()
            df = ak.stock_hk_hist(symbol=symbol, start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="")
            records = df.to_dict("records") if isinstance(df, pd.DataFrame) else []
            return {"market": "hk", "asset_type": "stock", "symbol": symbol, "records": records, "count": len(records)}
        except Exception as e:
            return {"market": "hk", "asset_type": "stock", "symbol": symbol, "records": [], "count": 0, "error": str(e)}
