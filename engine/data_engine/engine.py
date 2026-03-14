"""
DataEngine — 数据引擎门面类

统一管理行情拉取、DuckDB 持久化、公司概况查询。
对外提供单一接口，内部编排 collector + store + precomputed。
"""

import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from .collector import DataCollector
from .store import DuckDBStore
from .precomputed import load_profiles


class DataEngine:
    """数据引擎 — 原始数据的获取、持久化、查询门面"""

    def __init__(self):
        self._collector = DataCollector()
        self._store = DuckDBStore()
        self._profiles = load_profiles()

    @property
    def store(self) -> DuckDBStore:
        """暴露 store 给需要直接访问的模块（如聚类引擎存储聚类结果）"""
        return self._store

    @property
    def collector(self) -> DataCollector:
        """暴露 collector 给需要直接访问的模块"""
        return self._collector

    @property
    def available_sources(self) -> list[str]:
        return self._collector.available_sources

    # ── 行情数据 ──

    def get_realtime_quotes(self) -> pd.DataFrame:
        """拉取全市场实时行情（网络请求）"""
        return self._collector.get_realtime_quotes()

    def get_snapshot(self) -> pd.DataFrame:
        """获取 DuckDB 中最新快照（本地查询）"""
        return self._store.get_snapshot()

    def save_snapshot(self, df: pd.DataFrame):
        """保存行情快照到 DuckDB"""
        self._store.save_snapshot(df)

    # ── 日线历史 ──

    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        """获取个股日线，优先本地 DuckDB，缺失则通过 collector 拉取"""
        df = self._store.get_daily(code, start, end)
        if df is not None and len(df) > 0:
            return df
        # 本地无数据，尝试网络拉取
        df = self._collector.get_daily_history(code, start, end)
        if df is not None and len(df) > 0:
            self._store.save_daily(df)
        return df if df is not None else pd.DataFrame()

    def get_daily_history_batch(
        self, snapshot: pd.DataFrame, min_days: int = 20
    ) -> dict[str, pd.DataFrame]:
        """
        批量获取日线历史（从本地 DuckDB 缓存）
        纯本地查询，不触发网络请求。
        """
        if snapshot.empty or "code" not in snapshot.columns:
            return {}

        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")

        codes = snapshot["code"].astype(str).tolist()
        daily_map: dict[str, pd.DataFrame] = {}
        matched = 0

        for code in codes:
            try:
                df = self._store.get_daily(code, start_date, end_date)
                if df is not None and len(df) >= min_days:
                    daily_map[code] = df
                    matched += 1
            except Exception:
                continue

        logger.info(f"📈 日线历史读取: {matched}/{len(codes)} 只股票有 ≥{min_days} 日数据")
        return daily_map

    def get_market_history_streaming(
        self,
        codes: list[str],
        days: int = 7,
        on_progress: Optional["callable"] = None,
        on_batch_done: Optional["callable"] = None,
    ) -> dict[str, pd.DataFrame]:
        """流式批量拉取全市场历史日线（网络请求，带进度回调）"""
        return self._collector.get_market_history_streaming(
            codes, days, on_progress, on_batch_done
        )

    # ── 财务数据 ──

    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """获取季频财务数据（逐级降级）"""
        return self._collector.get_financial_data(code, year, quarter)

    # ── 快照历史（回放用）──

    def get_snapshot_daily_dates(self) -> list[str]:
        return self._store.get_snapshot_daily_dates()

    def get_snapshot_daily_range(self, days: int = 7) -> dict[str, pd.DataFrame]:
        return self._store.get_snapshot_daily_range(days)

    def save_history_as_snapshots(self, history_by_date: dict):
        self._store.save_history_as_snapshots(history_by_date)

    # ── 公司基础信息 ──

    def get_profiles(self) -> dict[str, dict]:
        """获取全量公司概况"""
        return self._profiles

    def get_profile(self, code: str) -> dict | None:
        """获取单只股票概况"""
        return self._profiles.get(code)

    # ── 元信息 ──

    def get_stock_count(self) -> int:
        return self._store.get_stock_count()

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "data_sources": {s: True for s in self.available_sources},
            "stock_count": self.get_stock_count(),
            "profiles_count": len(self._profiles),
        }
