"""
DataEngine — 数据引擎门面类

统一管理行情拉取、DuckDB 持久化、公司概况查询。
对外提供单一接口，内部编排 collector + store + precomputed。
"""

import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from .asset_resolver import AssetResolver
from .collector import DataCollector
from .market_adapters.registry import MarketAdapterRegistry
from .store import DuckDBStore
from .precomputed import load_profiles


class DataEngine:
    """数据引擎 — 原始数据的获取、持久化、查询门面"""

    def __init__(self):
        self._collector = DataCollector()
        self._store = DuckDBStore()
        self._profiles = load_profiles()
        self._resolver = AssetResolver(self.get_profiles)
        self._market_registry = MarketAdapterRegistry(self)

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

    def get_snapshot_as_of(self, as_of_date: str) -> pd.DataFrame:
        """获取某个历史日期可用于截面预测的市场快照"""
        return self._store.get_snapshot_as_of(as_of_date)

    def save_snapshot(self, df: pd.DataFrame):
        """保存行情快照到 DuckDB"""
        self._store.save_snapshot(df)

    # ── 日线历史 ──

    @staticmethod
    def _count_trading_days_between(d1: datetime.date, d2: datetime.date) -> int:
        """估算 d1 到 d2 之间有多少个交易日（不含 d1、d2 本身）

        简单规则：排除周六日。不考虑节假日（节假日后首个交易日会多等1天，可接受）。
        """
        if d1 >= d2:
            return 0
        count = 0
        cur = d1 + datetime.timedelta(days=1)
        while cur < d2:
            if cur.weekday() < 5:  # 0=Mon … 4=Fri
                count += 1
            cur += datetime.timedelta(days=1)
        return count

    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        """获取个股日线，优先本地 DuckDB，缺失或过期则通过 collector 拉取"""
        df = self._store.get_daily(code, start, end)
        if df is not None and len(df) > 0:
            # ── 新鲜度检查：缓存最后一条到今天之间是否有遗漏的交易日 ──
            stale = False
            missed = 0
            try:
                date_col = "date" if "date" in df.columns else ("trade_date" if "trade_date" in df.columns else None)
                if date_col:
                    last_date = pd.to_datetime(df[date_col].iloc[-1]).date()
                    today = datetime.date.today()
                    now = datetime.datetime.now()
                    # 1) 中间有遗漏交易日（如缓存到周一、现在周三→遗漏了周二）
                    missed = self._count_trading_days_between(last_date, today)
                    if missed >= 1:
                        stale = True
                    # 2) 今天本身是交易日且已开盘(>9:30)，但缓存还不是今天
                    elif (today.weekday() < 5
                          and now.time() >= datetime.time(9, 30)
                          and last_date < today):
                        stale = True
                        missed = 1
            except Exception:
                pass
            if not stale:
                return df
            # 缓存过期，重新拉取
            logger.debug(f"📡 {code} 本地日线数据过期(遗漏{missed}个交易日)，重新拉取...")
        # 本地无数据或过期，尝试网络拉取
        fresh = self._collector.get_daily_history(code, start, end)
        if fresh is not None and len(fresh) > 0:
            # 补齐 save_daily 所需的列
            if "code" not in fresh.columns:
                fresh["code"] = code
            if "turnover_rate" not in fresh.columns:
                fresh["turnover_rate"] = 0.0
            self._store.save_daily(fresh)
            return fresh
        # 网络拉取失败，fallback 到本地缓存（有总比没有好）
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

    # ── 分钟级 K 线 ──

    def get_kline(
        self, code: str, frequency: str = "60m", days: int = 5
    ) -> pd.DataFrame:
        """
        通用 K 线查询 — 本地优先，缺失时远程拉取并缓存

        Args:
            code: 股票代码
            frequency: "60m"（当前仅支持）
            days: 回溯天数，默认 5
        """
        freq_key = frequency.replace("m", "")  # "60m" → "60"

        end = datetime.date.today()
        start = end - datetime.timedelta(days=days + 5)  # 多拉几天补偿非交易日

        # 1. 先查本地
        local = self._store.get_kline(
            code, frequency,
            start_datetime=start.isoformat(),
            end_datetime=end.isoformat() + " 23:59:59",
        )
        # 60min 约 4 条/交易日，但 days 包含周末/节假日
        # 用 days * 2 作为保守阈值，避免非交易日导致反复远程拉取
        if len(local) >= days * 2:
            return local

        # 2. 本地不足，远程拉取
        df = self._collector.get_intraday_history(
            code, freq_key, start.isoformat(), end.isoformat()
        )
        if df.empty:
            return local if not local.empty else pd.DataFrame()

        # 3. 缓存到 DuckDB
        df["code"] = code
        self._store.save_kline(df, frequency)

        return self._store.get_kline(
            code, frequency,
            start_datetime=start.isoformat(),
            end_datetime=end.isoformat() + " 23:59:59",
        )

    # ── 财务数据 ──

    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """获取季频财务数据（逐级降级）"""
        return self._collector.get_financial_data(code, year, quarter)

    # ── 新闻/公告 ──

    def get_news(self, code: str, limit: int = 50) -> pd.DataFrame:
        """获取个股新闻（原始数据，不含情感分析）"""
        return self._collector.get_stock_news(code, limit)

    def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
        """获取公司公告（原始数据）"""
        return self._collector.get_announcements(code, limit)

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

    def get_company_profile(self, code: str) -> dict | None:
        """兼容 ExpertTools 的旧调用名称。"""
        return self.get_profile(code)

    # ── 多市场统一入口 ──

    def resolve_asset(self, query: str, market_hint: str = ""):
        return self._resolver.resolve(query, market_hint=market_hint)

    def search_assets(self, query: str, market: str = "all", limit: int = 20) -> list[dict]:
        if market == "all":
            results: list[dict] = []
            for adapter in self._market_registry.list_adapters():
                try:
                    results.extend(adapter.search(query, limit=limit))
                except Exception as e:
                    logger.warning(f"搜索市场 {adapter.market} 失败: {e}")
            return results[:limit]
        return self._market_registry.get(market).search(query, limit=limit)

    def get_asset_profile(self, symbol: str, market: str) -> dict:
        return self._market_registry.get(market).get_profile(symbol)

    def get_asset_quote(self, symbol: str, market: str) -> dict:
        return self._market_registry.get(market).get_quote(symbol)

    def get_asset_daily_history(self, symbol: str, market: str, start: str, end: str) -> dict:
        return self._market_registry.get(market).get_daily_history(symbol, start, end)

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

    # ── 板块数据方法 ──

    def get_sector_board_list(self, board_type: str = "industry") -> pd.DataFrame:
        """获取板块列表 + 实时行情"""
        return self._collector.get_sector_board_list(board_type=board_type)

    def get_sector_board_history(
        self, board_name: str, board_code: str = "",
        board_type: str = "industry",
        start_date: str = "", end_date: str = "",
    ) -> pd.DataFrame:
        """获取板块历史 K 线（本地优先 + 远程回填）"""
        # 先查本地
        if board_code:
            local = self._store.get_sector_board_history(
                board_code, start_date=start_date, end_date=end_date
            )
            if not local.empty and len(local) >= 5:
                return local

        # 远程拉取
        df = self._collector.get_sector_board_history(
            board_name=board_name, board_type=board_type,
            start_date=start_date, end_date=end_date,
        )
        if not df.empty and board_code:
            df["board_code"] = board_code
            df["board_name"] = board_name
            df["board_type"] = board_type
            self._store.save_sector_board_daily(df)
        return df

    def get_sector_fund_flow_rank(
        self, indicator: str = "今日", sector_type: str = "行业资金流"
    ) -> pd.DataFrame:
        """获取板块资金流排行"""
        return self._collector.get_sector_fund_flow_rank(
            indicator=indicator, sector_type=sector_type
        )

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        """获取板块成分股"""
        return self._collector.get_sector_constituents(board_name=board_name)

    def save_sector_board_daily(self, df: pd.DataFrame):
        """保存板块日行情到 DuckDB"""
        self._store.save_sector_board_daily(df)

    def save_sector_fund_flow(self, df: pd.DataFrame):
        """保存板块资金流向到 DuckDB"""
        self._store.save_sector_fund_flow(df)
