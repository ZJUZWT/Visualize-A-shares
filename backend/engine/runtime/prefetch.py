from __future__ import annotations

import asyncio
import re
from typing import Callable

from loguru import logger

from .context import ExecutionContext


class QueryPrefetcher:
    """根据用户输入提前拉取低成本股票上下文。"""

    def __init__(
        self,
        data_engine=None,
        *,
        stock_name_lookup: Callable[[], dict[str, str]] | None = None,
    ):
        self._data_engine = data_engine
        self._stock_name_lookup = stock_name_lookup

    def detect_entities(self, message: str) -> tuple[list[str], list[str]]:
        codes = list(dict.fromkeys(re.findall(r"(?<!\d)(\d{6})(?!\d)", message or "")))
        names: list[str] = []

        if self._stock_name_lookup:
            try:
                name_map = self._stock_name_lookup() or {}
            except Exception as e:
                logger.warning(f"预取股票名称映射失败: {e}")
                name_map = {}
            for name in sorted(name_map, key=len, reverse=True):
                if len(name) >= 2 and name in message:
                    names.append(name)
                    code = name_map[name]
                    if code not in codes:
                        codes.append(code)

        return codes, names

    async def prefetch(self, message: str, context: ExecutionContext) -> ExecutionContext:
        codes, names = self.detect_entities(message)
        context.entities.stock_codes = codes
        context.entities.stock_names = names

        if not codes or self._data_engine is None:
            return context

        for code in codes:
            try:
                profile = await asyncio.to_thread(self._data_engine.get_company_profile, code)
                if profile:
                    context.prefetch.profiles[code] = (
                        profile if isinstance(profile, dict) else {"profile": str(profile)}
                    )
            except Exception as e:
                context.prefetch.errors.append(f"profile:{code}:{e}")
                logger.warning(f"预取公司概况失败 {code}: {e}")

            try:
                records = await asyncio.to_thread(self._fetch_history_records, code)
                if records:
                    context.prefetch.history[code] = records
            except Exception as e:
                context.prefetch.errors.append(f"history:{code}:{e}")
                logger.warning(f"预取日线失败 {code}: {e}")

        return context

    def _fetch_history_records(self, code: str) -> list[dict]:
        import datetime

        end = datetime.date.today().strftime("%Y-%m-%d")
        start = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
        df = self._data_engine.get_daily_history(code, start, end)
        if df is None or getattr(df, "empty", False):
            return []
        return df.tail(30).to_dict("records")
