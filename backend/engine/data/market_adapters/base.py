"""多市场统一适配器接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseMarketAdapter(ABC):
    market: str = "base"

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[dict]:
        ...

    @abstractmethod
    def get_profile(self, symbol: str) -> dict:
        ...

    @abstractmethod
    def get_quote(self, symbol: str) -> dict:
        ...

    @abstractmethod
    def get_daily_history(self, symbol: str, start: str, end: str) -> dict:
        ...
