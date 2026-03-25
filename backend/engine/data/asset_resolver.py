"""多市场资产识别器。"""

from __future__ import annotations

import re
from typing import Callable

from .market_types import AssetIdentity


class AssetResolver:
    """根据用户输入推断市场和资产类型。"""

    _FUTURES_SYMBOLS = {
        "CL", "SC", "AU", "AU0", "AG", "CU", "AL", "ZN", "RB", "HC", "IF", "IH", "IC",
    }

    def __init__(self, profile_lookup: Callable[[], dict[str, dict]] | None = None):
        self._profile_lookup = profile_lookup

    def resolve(self, raw: str, market_hint: str = "") -> AssetIdentity:
        text = (raw or "").strip().upper()
        if market_hint:
            return self._from_market_hint(raw, market_hint)

        if re.fullmatch(r"\d{5}", text):
            return AssetIdentity(market="hk", asset_type="stock", symbol=text, exchange="HKEX", currency="HKD")

        if re.fullmatch(r"\d{6}", text):
            if text.startswith(("0", "3", "6", "8", "4")):
                return AssetIdentity(market="cn", asset_type="stock", symbol=text, exchange="CN", currency="CNY")
            if text.startswith(("1", "5")):
                return AssetIdentity(market="fund", asset_type="fund", symbol=text, exchange="CN", currency="CNY")

        if text in self._FUTURES_SYMBOLS or re.fullmatch(r"[A-Z]{1,3}\d{0,2}", text) and text[:2] in self._FUTURES_SYMBOLS:
            return AssetIdentity(market="futures", asset_type="future", symbol=text, exchange="FUTURES", currency="CNY")

        if re.fullmatch(r"[A-Z][A-Z.\-]{0,9}", text):
            return AssetIdentity(market="us", asset_type="stock", symbol=text, exchange="NASDAQ/NYSE", currency="USD")

        profile = self._resolve_by_profile_name(raw)
        if profile:
            return profile

        return AssetIdentity(market="cn", asset_type="stock", symbol=(raw or "").strip(), exchange="CN", currency="CNY")

    def _from_market_hint(self, raw: str, market_hint: str) -> AssetIdentity:
        market = market_hint.lower()
        asset_type = "stock"
        currency = "CNY"
        exchange = market.upper()
        if market == "fund":
            asset_type = "fund"
        elif market == "futures":
            asset_type = "future"
        elif market == "hk":
            currency = "HKD"
            exchange = "HKEX"
        elif market == "us":
            currency = "USD"
            exchange = "NASDAQ/NYSE"
        return AssetIdentity(market=market, asset_type=asset_type, symbol=(raw or "").strip().upper(), currency=currency, exchange=exchange)

    def _resolve_by_profile_name(self, raw: str) -> AssetIdentity | None:
        if not self._profile_lookup:
            return None
        profiles = self._profile_lookup() or {}
        text = (raw or "").strip()
        for code, profile in profiles.items():
            if text and profile.get("name") == text:
                return AssetIdentity(
                    market="cn",
                    asset_type="stock",
                    symbol=code,
                    display_name=profile.get("name", text),
                    exchange="CN",
                    currency="CNY",
                )
        return None
