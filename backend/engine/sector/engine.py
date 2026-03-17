"""板块研究引擎 — 数据编排 + 信号合成"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
import pandas as pd

# 用于去重：去掉板块名末尾的罗马数字后缀（Ⅰ Ⅱ Ⅲ Ⅳ 等）
_ROMAN_SUFFIX = re.compile(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$")


def _base_board_name(name: str) -> str:
    """去掉板块名末尾的罗马数字后缀，返回基础名用于去重"""
    return _ROMAN_SUFFIX.sub("", name).strip()

from engine.data import get_data_engine
from engine.sector.schemas import (
    SectorBoardItem, SectorHistoryItem, SectorFundFlowItem,
    ConstituentItem, HeatmapCell, RotationMatrixRow,
    SectorBoardsResponse, SectorHistoryResponse,
    SectorHeatmapResponse, SectorRotationResponse,
    SectorConstituentsResponse, SectorPredictionItem,
    StockSectorInfo, StockSectorsResponse,
)


# ─── 内存缓存（避免短时间并发重复请求 AKShare 被封）────────
CACHE_TTL = 60  # 秒（板块列表等高频变化数据）
CONSTITUENTS_CACHE_TTL = 86400  # 24 小时（成分股极少变化）
CONSTITUENTS_DB_MAX_AGE_DAYS = 7  # DuckDB 成分股数据 7 天内视为有效


@dataclass
class _CacheEntry:
    data: Any
    ttl: float = CACHE_TTL
    ts: float = field(default_factory=time.monotonic)

    def expired(self) -> bool:
        return (time.monotonic() - self.ts) > self.ttl


class SectorEngine:
    """板块研究引擎"""

    def __init__(self):
        self._data = get_data_engine()
        self._predictor = None  # 延迟初始化
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}  # 防并发击穿

    def _get_cache(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry and not entry.expired():
            logger.debug(f"[SectorEngine] 缓存命中: {key}")
            return entry.data
        return None

    def _set_cache(self, key: str, data: Any, ttl: float = CACHE_TTL):
        self._cache[key] = _CacheEntry(data=data, ttl=ttl)

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _get_predictor(self):
        if self._predictor is None:
            from engine.sector.predictor import SectorPredictor
            self._predictor = SectorPredictor()
        return self._predictor

    async def get_boards(
        self, board_type: str = "industry", date: str = "",
    ) -> SectorBoardsResponse:
        """获取板块列表 + 实时行情 + 资金流 + 预测信号"""
        cache_key = f"boards:{board_type}:{date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        # 并发锁：防止多个请求同时击穿缓存
        lock = self._get_lock(cache_key)
        async with lock:
            # double-check
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached
            return await self._fetch_boards(board_type, date, cache_key)

    async def _fetch_boards(
        self, board_type: str, date: str, cache_key: str,
    ) -> SectorBoardsResponse:
        """实际拉取板块数据（带缓存写入 + 自动持久化到 DuckDB）
        
        降级策略：远程 API → DuckDB 本地缓存
        """
        t0 = time.monotonic()

        # 串行获取板块列表和资金流排行（减少东财并发压力，避免 RemoteDisconnected）
        sector_type = "行业资金流" if board_type == "industry" else "概念资金流"
        board_list_df = await asyncio.to_thread(
            self._data.get_sector_board_list, board_type
        )
        fund_flow_df = pd.DataFrame()
        if not board_list_df.empty:
            # 板块列表成功才去拉资金流（节省一次请求）
            fund_flow_df = await asyncio.to_thread(
                self._data.get_sector_fund_flow_rank, "今日", sector_type
            )

        # ── 远程 API 全部失败 → 降级到 DuckDB 本地数据 ──
        if board_list_df.empty:
            logger.warning(
                f"[SectorEngine] 远程 API 全部失败，降级到 DuckDB 本地数据 ({board_type})"
            )
            try:
                board_list_df = self._data.store.get_sector_board_daily(
                    board_type=board_type
                )
                if not board_list_df.empty:
                    # DuckDB 中的数据可能有多天，只取最近一天
                    if "date" in board_list_df.columns:
                        latest_date = board_list_df["date"].max()
                        board_list_df = board_list_df[
                            board_list_df["date"] == latest_date
                        ]
                    logger.info(
                        f"[SectorEngine] DuckDB 降级成功: {len(board_list_df)} 个板块 "
                        f"(date={board_list_df['date'].iloc[0] if 'date' in board_list_df.columns and len(board_list_df) > 0 else '?'})"
                    )
                    # 也尝试从 DuckDB 读资金流
                    fund_flow_df = self._data.store.get_sector_fund_flow(
                        board_type=board_type
                    )
                    if not fund_flow_df.empty and "date" in fund_flow_df.columns:
                        latest_date = fund_flow_df["date"].max()
                        fund_flow_df = fund_flow_df[
                            fund_flow_df["date"] == latest_date
                        ]
            except Exception as e:
                logger.warning(f"[SectorEngine] DuckDB 降级也失败: {e}")

        # ── 自动持久化到 DuckDB（仅远程数据成功时）──
        if not board_list_df.empty and "date" not in board_list_df.columns:
            # 远程数据没有 date 字段 → 说明是新鲜数据，需要持久化
            self._auto_persist(board_list_df, fund_flow_df, board_type)

        # 合并资金流数据
        items: list[SectorBoardItem] = []
        fund_flow_map: dict[str, dict] = {}
        if not fund_flow_df.empty and "board_name" in fund_flow_df.columns:
            for _, row in fund_flow_df.iterrows():
                name = row.get("board_name", "")
                fund_flow_map[name] = {
                    "main_force_net_inflow": self._safe_float(row.get("main_force_net_inflow")),
                    "main_force_net_ratio": self._safe_float(row.get("main_force_net_ratio")),
                }

        if not board_list_df.empty:
            seen_base_names: set[str] = set()
            for _, row in board_list_df.iterrows():
                name = row.get("board_name", "")
                # 去重：按基础名（去掉末尾罗马数字Ⅰ/Ⅱ/Ⅲ）去重
                base = _base_board_name(name)
                if base in seen_base_names:
                    continue
                seen_base_names.add(base)
                flow = fund_flow_map.get(name, {})
                items.append(SectorBoardItem(
                    board_code=str(row.get("board_code", "")),
                    board_name=name,
                    board_type=board_type,
                    close=self._safe_float(row.get("close")),
                    pct_chg=self._safe_float(row.get("pct_chg")),
                    volume=self._safe_float(row.get("volume")),
                    amount=self._safe_float(row.get("amount")),
                    turnover_rate=self._safe_float(row.get("turnover_rate")),
                    total_mv=self._safe_float(row.get("total_mv")),
                    rise_count=int(row.get("rise_count", 0) or 0),
                    fall_count=int(row.get("fall_count", 0) or 0),
                    leading_stock=str(row.get("leading_stock", "")),
                    leading_pct_chg=self._safe_float(row.get("leading_pct_chg")),
                    main_force_net_inflow=flow.get("main_force_net_inflow"),
                    main_force_net_ratio=flow.get("main_force_net_ratio"),
                ))

        # 尝试加载预测信号（如果有足够历史数据）
        try:
            board_hist = self._data.store.get_sector_board_daily(board_type=board_type)
            flow_hist = self._data.store.get_sector_fund_flow(board_type=board_type)
            if not board_hist.empty and len(board_hist) > 20:
                pred = self._get_predictor().predict(board_hist, flow_hist)
                for item in items:
                    if item.board_code in pred.predictions:
                        item.prediction_score = pred.predictions[item.board_code]
                        item.prediction_signal = pred.signals.get(item.board_code, "neutral")
        except Exception as e:
            logger.warning(f"板块预测失败（不影响数据展示）: {e}")

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.get_boards({board_type}) 耗时 {elapsed:.1f}s, "
            f"{len(items)} 个板块"
        )

        result = SectorBoardsResponse(
            boards=items,
            date=date or datetime.now().strftime("%Y-%m-%d"),
            board_type=board_type,
            total=len(items),
        )
        # 如果是 DuckDB 降级数据，缓存更久（10 分钟）避免反复打不可用的东财
        is_from_duckdb = not board_list_df.empty and "date" in board_list_df.columns
        cache_ttl = 600 if is_from_duckdb else CACHE_TTL
        self._set_cache(cache_key, result, ttl=cache_ttl)
        return result

    async def get_history(
        self, board_code: str, board_name: str,
        board_type: str = "industry",
        start_date: str = "", end_date: str = "",
    ) -> SectorHistoryResponse:
        """获取单个板块的历史行情 + 资金流时序"""
        t0 = time.monotonic()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # 串行拉取 K 线和资金流历史（减少东财并发压力）
        hist_df = await asyncio.to_thread(
            self._data.get_sector_board_history,
            board_name=board_name, board_code=board_code,
            board_type=board_type,
            start_date=start_date, end_date=end_date,
        )
        flow_df = await asyncio.to_thread(
            self._data.store.get_sector_fund_flow_history,
            board_code=board_code,
            start_date=start_date, end_date=end_date,
        )

        history = []
        if not hist_df.empty:
            for _, row in hist_df.iterrows():
                history.append(SectorHistoryItem(
                    date=str(row.get("date", "")),
                    open=self._safe_float(row.get("open")),
                    high=self._safe_float(row.get("high")),
                    low=self._safe_float(row.get("low")),
                    close=self._safe_float(row.get("close")),
                    pct_chg=self._safe_float(row.get("pct_chg")),
                    volume=self._safe_float(row.get("volume")),
                    amount=self._safe_float(row.get("amount")),
                    turnover_rate=self._safe_float(row.get("turnover_rate")),
                ))

        fund_flow_history = []
        if not flow_df.empty:
            for _, row in flow_df.iterrows():
                fund_flow_history.append(SectorFundFlowItem(
                    date=str(row.get("date", "")),
                    board_code=board_code,
                    board_name=board_name,
                    main_force_net_inflow=self._safe_float(row.get("main_force_net_inflow")),
                    main_force_net_ratio=self._safe_float(row.get("main_force_net_ratio")),
                    super_large_net_inflow=self._safe_float(row.get("super_large_net_inflow")),
                    large_net_inflow=self._safe_float(row.get("large_net_inflow")),
                    medium_net_inflow=self._safe_float(row.get("medium_net_inflow")),
                    small_net_inflow=self._safe_float(row.get("small_net_inflow")),
                ))

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.get_history({board_name}) 耗时 {elapsed:.1f}s, "
            f"K线 {len(history)} 条, 资金流 {len(fund_flow_history)} 条"
        )

        return SectorHistoryResponse(
            board_code=board_code, board_name=board_name,
            history=history, fund_flow_history=fund_flow_history,
        )

    async def get_heatmap(
        self, board_type: str = "industry", date: str = "",
    ) -> SectorHeatmapResponse:
        """获取热力图数据（复用 boards 缓存，不会额外请求 AKShare）"""
        t0 = time.monotonic()
        resp = await self.get_boards(board_type=board_type, date=date)
        cells = [
            HeatmapCell(
                board_code=b.board_code, board_name=b.board_name,
                pct_chg=b.pct_chg,
                main_force_net_inflow=b.main_force_net_inflow or 0.0,
                main_force_net_ratio=b.main_force_net_ratio or 0.0,
            )
            for b in resp.boards
        ]
        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ SectorEngine.get_heatmap({board_type}) 耗时 {elapsed:.1f}s")
        return SectorHeatmapResponse(
            cells=cells, date=resp.date, board_type=board_type,
        )

    async def get_constituents(
        self, board_name: str, board_code: str = "",
    ) -> SectorConstituentsResponse:
        """获取板块成分股（三层缓存：内存24h → DuckDB 7天 → 远程拉取+回填）"""
        t0 = time.monotonic()
        cache_key = f"constituents:{board_name}"

        # ── L1: 内存缓存（24h TTL）──
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        # 并发锁防击穿
        lock = self._get_lock(cache_key)
        async with lock:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached

            items: list[ConstituentItem] = []

            # ── L2: DuckDB 本地（7 天内有效）──
            db_age = self._data.store.get_sector_constituents_age(board_name)
            if db_age is not None and db_age <= CONSTITUENTS_DB_MAX_AGE_DAYS:
                local_df = self._data.store.get_sector_constituents(board_name)
                if not local_df.empty:
                    for _, row in local_df.iterrows():
                        items.append(ConstituentItem(
                            code=str(row.get("code", "")),
                            name=str(row.get("name", "")),
                            # DuckDB 只缓存 code/name，实时行情字段为 0
                            price=0.0, pct_chg=0.0, volume=0.0,
                            amount=0.0, turnover_rate=0.0,
                        ))
                    elapsed = time.monotonic() - t0
                    logger.info(
                        f"⏱️ SectorEngine.get_constituents({board_name}) "
                        f"DuckDB 命中(age={db_age}d) 耗时 {elapsed:.3f}s, "
                        f"{len(items)} 只成分股"
                    )
                    result = SectorConstituentsResponse(
                        board_code=board_code, board_name=board_name,
                        constituents=items, total=len(items),
                    )
                    self._set_cache(cache_key, result, ttl=CONSTITUENTS_CACHE_TTL)
                    return result

            # ── L3: 远程拉取 + 自动回填 DuckDB ──
            df = await asyncio.to_thread(
                self._data.get_sector_constituents, board_name
            )
            if not df.empty:
                for _, row in df.iterrows():
                    items.append(ConstituentItem(
                        code=str(row.get("code", "")),
                        name=str(row.get("name", "")),
                        price=self._safe_float(row.get("price")),
                        pct_chg=self._safe_float(row.get("pct_chg")),
                        volume=self._safe_float(row.get("volume")),
                        amount=self._safe_float(row.get("amount")),
                        turnover_rate=self._safe_float(row.get("turnover_rate")),
                        pe_ttm=self._safe_float(row.get("pe_ttm")) or None,
                        pb=self._safe_float(row.get("pb")) or None,
                    ))
                # 回填 DuckDB
                try:
                    self._data.store.save_sector_constituents(board_name, df)
                except Exception as e:
                    logger.warning(f"成分股回填 DuckDB 失败({board_name}): {e}")

            elapsed = time.monotonic() - t0
            logger.info(
                f"⏱️ SectorEngine.get_constituents({board_name}) "
                f"远程拉取 耗时 {elapsed:.1f}s, {len(items)} 只成分股"
            )

            result = SectorConstituentsResponse(
                board_code=board_code, board_name=board_name,
                constituents=items, total=len(items),
            )
            self._set_cache(cache_key, result, ttl=CONSTITUENTS_CACHE_TTL)
            return result

    async def get_rotation(
        self, days: int = 10, board_type: str = "industry",
    ) -> SectorRotationResponse:
        """获取板块轮动预测"""
        t0 = time.monotonic()

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        flow_df = self._data.store.get_sector_fund_flow(
            board_type=board_type, start_date=start_date, end_date=end_date,
        )

        matrix: list[RotationMatrixRow] = []
        if not flow_df.empty and "board_code" in flow_df.columns:
            for code, group in flow_df.groupby("board_code"):
                group = group.sort_values("date").tail(days)
                flows = group["main_force_net_inflow"].tolist()
                dates = [str(d) for d in group["date"].tolist()]
                name = group["board_name"].iloc[0] if "board_name" in group.columns else ""

                trend = self._calc_trend_signal(flows)

                matrix.append(RotationMatrixRow(
                    board_code=str(code), board_name=str(name),
                    daily_flows=flows, daily_dates=dates,
                    trend_signal=trend,
                ))

        # 排序：按最近日资金流入
        matrix.sort(key=lambda r: r.daily_flows[-1] if r.daily_flows else 0, reverse=True)

        top_bullish = [
            SectorPredictionItem(board_code=r.board_code, board_name=r.board_name, signal="bullish")
            for r in matrix[:5] if r.trend_signal == "bullish"
        ]
        top_bearish = [
            SectorPredictionItem(board_code=r.board_code, board_name=r.board_name, signal="bearish")
            for r in reversed(matrix) if r.trend_signal == "bearish"
        ][:5]

        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ SectorEngine.get_rotation(days={days}) 耗时 {elapsed:.1f}s")

        return SectorRotationResponse(
            matrix=matrix, days=days, board_type=board_type,
            top_bullish=top_bullish, top_bearish=top_bearish,
        )

    async def fetch_and_save(self, board_type: str = "industry") -> dict:
        """触发数据采集 + 持久化"""
        t0 = time.monotonic()

        sector_type = "行业资金流" if board_type == "industry" else "概念资金流"
        board_df = await asyncio.to_thread(
            self._data.get_sector_board_list, board_type
        )
        flow_df = await asyncio.to_thread(
            self._data.get_sector_fund_flow_rank, "今日", sector_type
        )

        today = datetime.now().strftime("%Y-%m-%d")
        saved_boards = 0
        saved_flows = 0

        if not board_df.empty:
            board_df["date"] = today
            board_df["board_type"] = board_type
            self._data.save_sector_board_daily(board_df)
            saved_boards = len(board_df)

        if not flow_df.empty:
            flow_df["date"] = today
            flow_df["board_type"] = board_type
            # 确保有 board_code（资金流排行可能没有 code，用 name 做 key）
            if "board_code" not in flow_df.columns:
                # 从 board_df 中匹配 code
                if not board_df.empty and "board_name" in board_df.columns:
                    name_to_code = dict(zip(board_df["board_name"], board_df["board_code"]))
                    flow_df["board_code"] = flow_df["board_name"].map(name_to_code).fillna("")
                else:
                    flow_df["board_code"] = flow_df["board_name"]
            self._data.save_sector_fund_flow(flow_df)
            saved_flows = len(flow_df)

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.fetch_and_save({board_type}) 耗时 {elapsed:.1f}s, "
            f"保存板块行情 {saved_boards} 条, 资金流向 {saved_flows} 条"
        )

        return {
            "board_type": board_type,
            "saved_boards": saved_boards,
            "saved_flows": saved_flows,
            "elapsed_s": round(elapsed, 1),
        }

    async def get_stock_sectors(
        self, stock_code: str, stock_name: str = "",
    ) -> StockSectorsResponse:
        """反查某只股票所属的所有板块（行业+概念）

        策略：遍历已缓存的行业和概念板块，检查每个板块的成分股是否包含该股票。
        """
        t0 = time.monotonic()
        sectors: list[StockSectorInfo] = []

        # 遍历 industry 和 concept 两种类型
        for board_type in ("industry", "concept"):
            try:
                boards_resp = await self.get_boards(board_type=board_type)
                for board in boards_resp.boards:
                    try:
                        cons_resp = await self.get_constituents(
                            board_name=board.board_name, board_code=board.board_code
                        )
                        for c in cons_resp.constituents:
                            if c.code == stock_code or (stock_name and c.name == stock_name):
                                sectors.append(StockSectorInfo(
                                    board_code=board.board_code,
                                    board_name=board.board_name,
                                    board_type=board_type,
                                    pct_chg=board.pct_chg,
                                ))
                                break
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"反查 {board_type} 板块失败: {e}")

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.get_stock_sectors({stock_code}) 耗时 {elapsed:.1f}s, "
            f"找到 {len(sectors)} 个板块"
        )
        return StockSectorsResponse(
            stock_code=stock_code, stock_name=stock_name, sectors=sectors,
        )

    async def get_stock_sectors_fast(
        self, stock_code: str, stock_name: str = "",
    ) -> StockSectorsResponse:
        """快速反查——利用东财个股所属板块接口（比遍历成分股快得多）

        先尝试通过数据源获取个股所属板块，如果无法获取则降级到遍历已加载的 boards 缓存。
        """
        t0 = time.monotonic()
        sectors: list[StockSectorInfo] = []

        # 方案 1：通过全局并发限流的数据源调用东财接口
        try:
            from engine.data.sources.eastmoney_direct import _EASTMONEY_SEMAPHORE
            import akshare as ak

            # 个股所属行业（受并发限流保护）
            try:
                acquired = _EASTMONEY_SEMAPHORE.acquire(timeout=15)
                if acquired:
                    try:
                        df = ak.stock_board_industry_name_em(symbol=stock_code)
                        if df is not None and not df.empty:
                            for _, row in df.iterrows():
                                sectors.append(StockSectorInfo(
                                    board_code=str(row.get("板块代码", "")),
                                    board_name=str(row.get("板块名称", "")),
                                    board_type="industry",
                                    pct_chg=self._safe_float(row.get("板块涨跌幅")),
                                ))
                    finally:
                        _EASTMONEY_SEMAPHORE.release()
            except Exception:
                pass

            # 个股所属概念（受并发限流保护）
            try:
                acquired = _EASTMONEY_SEMAPHORE.acquire(timeout=15)
                if acquired:
                    try:
                        df = ak.stock_board_concept_name_em(symbol=stock_code)
                        if df is not None and not df.empty:
                            for _, row in df.iterrows():
                                sectors.append(StockSectorInfo(
                                    board_code=str(row.get("板块代码", "")),
                                    board_name=str(row.get("板块名称", "")),
                                    board_type="concept",
                                    pct_chg=self._safe_float(row.get("板块涨跌幅")),
                                ))
                    finally:
                        _EASTMONEY_SEMAPHORE.release()
            except Exception:
                pass
        except ImportError:
            pass

        # 方案 2：降级——从缓存的 boards 中遍历（只查已加载的）
        if not sectors:
            for board_type in ("industry", "concept"):
                cache_key = f"boards:{board_type}:"
                cached = self._get_cache(cache_key)
                if cached is None:
                    continue
                for board in cached.boards:
                    if stock_name and board.leading_stock == stock_name:
                        sectors.append(StockSectorInfo(
                            board_code=board.board_code,
                            board_name=board.board_name,
                            board_type=board_type,
                            pct_chg=board.pct_chg,
                        ))

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.get_stock_sectors_fast({stock_code}) 耗时 {elapsed:.1f}s, "
            f"找到 {len(sectors)} 个板块"
        )
        return StockSectorsResponse(
            stock_code=stock_code, stock_name=stock_name, sectors=sectors,
        )

    def _auto_persist(self, board_df, fund_flow_df, board_type: str):
        """自动将板块数据持久化到 DuckDB（同步执行，不影响响应速度因在锁内）"""
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            saved_boards = 0
            saved_flows = 0

            if not board_df.empty:
                df = board_df.copy()
                df["date"] = today
                df["board_type"] = board_type
                self._data.save_sector_board_daily(df)
                saved_boards = len(df)

            if not fund_flow_df.empty:
                df = fund_flow_df.copy()
                df["date"] = today
                df["board_type"] = board_type
                if "board_code" not in df.columns:
                    if not board_df.empty and "board_name" in board_df.columns:
                        name_to_code = dict(zip(board_df["board_name"], board_df["board_code"]))
                        df["board_code"] = df["board_name"].map(name_to_code).fillna("")
                    else:
                        df["board_code"] = df["board_name"]
                self._data.save_sector_fund_flow(df)
                saved_flows = len(df)

            if saved_boards or saved_flows:
                logger.info(
                    f"📦 自动持久化({board_type}): 板块行情 {saved_boards} 条, "
                    f"资金流向 {saved_flows} 条"
                )
        except Exception as e:
            logger.warning(f"自动持久化失败（不影响数据展示）: {e}")

    @staticmethod
    def _safe_float(val, default: float = 0.0) -> float:
        if val is None or val == "" or str(val) == "nan":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _calc_trend_signal(flows: list[float]) -> str:
        """根据资金流向序列计算趋势信号"""
        if not flows:
            return "neutral"
        consecutive = 0
        for v in reversed(flows):
            if v > 0:
                if consecutive >= 0:
                    consecutive += 1
                else:
                    break
            elif v < 0:
                if consecutive <= 0:
                    consecutive -= 1
                else:
                    break
            else:
                break
        if consecutive >= 3:
            return "bullish"
        elif consecutive <= -3:
            return "bearish"
        return "neutral"
