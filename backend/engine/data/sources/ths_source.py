"""
同花顺数据源 — 板块数据独立备选（完全独立于东财）
数据来源：同花顺 q.10jqka.com.cn（通过 AKShare 的 _ths 系列接口封装）
特点：
    - 板块列表 7×24h 可用（东财夜间维护时同花顺仍可用）
    - 与东财完全独立的服务器，不受东财断路器影响
    - 行业板块 90 个（同花顺分类） + 概念板块 375+
    - 行业板块有净流入、涨跌家数、领涨股等完整信息
    - 板块历史 K 线可用

限制：
    - 概念板块列表请求较慢（需要分页，约 6~8s）
    - 同花顺行业分类与东财不完全一致（90 vs 496 个行业板块）
    - 资金流数据直接在 summary 中（净流入），不如东财细分（超大单/大单/中单/小单）
    - AKShare 当前版本(1.18+)无同花顺成分股接口，成分股需降级到东财
"""

import random
import time
import threading
from typing import Optional

import pandas as pd
from loguru import logger

from .base import BaseDataSource

# 同花顺自己的并发控制（独立于东财）
_THS_SEMAPHORE = threading.Semaphore(2)  # 同花顺并发稍保守
_THS_LAST_REQUEST = 0.0
_THS_REQUEST_LOCK = threading.Lock()
_THS_MIN_INTERVAL = 0.5  # 同花顺请求间隔稍长


class THSSource(BaseDataSource):
    """同花顺数据源 — 板块数据的独立备选（不依赖东财服务器）"""

    name = "ths"
    priority = 1.5  # 在 EastMoney(0.5) 和 AKShare(1) 之后，BaoStock(2) 之前

    MAX_RETRIES = 2
    RETRY_BASE_DELAY = 2

    def __init__(self):
        try:
            import akshare as ak
            self._ak = ak
            # 验证同花顺接口存在
            assert hasattr(ak, "stock_board_industry_summary_ths")
            logger.info("[THS] 同花顺数据源初始化成功")
        except (ImportError, AssertionError) as e:
            logger.error(f"[THS] 同花顺数据源初始化失败: {e}")
            raise

        # 板块名 → code 缓存（避免重复请求 name 接口）
        self._industry_name_to_code: dict[str, str] = {}
        self._concept_name_to_code: dict[str, str] = {}

    def _throttle(self):
        """同花顺独立节流"""
        global _THS_LAST_REQUEST
        with _THS_REQUEST_LOCK:
            now = time.monotonic()
            elapsed = now - _THS_LAST_REQUEST
            if elapsed < _THS_MIN_INTERVAL:
                time.sleep(_THS_MIN_INTERVAL - elapsed + random.uniform(0, 0.2))
            _THS_LAST_REQUEST = time.monotonic()

    def _fetch_with_retry(self, func, func_name: str, **kwargs):
        """带重试 + 独立并发限流的数据拉取"""
        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            acquired = _THS_SEMAPHORE.acquire(timeout=30)
            if not acquired:
                logger.warning(f"[THS] {func_name} 并发限流等待超时")
                continue
            try:
                self._throttle()
                result = func(**kwargs) if kwargs else func()
                return result
            except Exception as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_BASE_DELAY * attempt + random.uniform(0, 1)
                    logger.warning(
                        f"[THS] {func_name} 第 {attempt} 次失败: {e}，"
                        f"{wait:.1f}s 后重试..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[THS] {func_name} {self.MAX_RETRIES} 次重试全部失败: {e}"
                    )
            finally:
                _THS_SEMAPHORE.release()
        return None

    # ─── 必须实现的抽象方法（同花顺不适合作为个股数据源，返回空）──

    def get_realtime_quotes(self) -> pd.DataFrame:
        """同花顺不提供全市场实时快照"""
        raise NotImplementedError

    def get_daily_history(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """同花顺不提供个股日线"""
        raise NotImplementedError

    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """同花顺不提供财务数据"""
        raise NotImplementedError

    def health_check(self) -> bool:
        """检查同花顺接口是否可用"""
        try:
            df = self._fetch_with_retry(
                self._ak.stock_board_industry_summary_ths,
                "health_check",
            )
            ok = df is not None and len(df) > 10
            logger.info(f"[THS] health check: {'OK' if ok else 'FAIL'}")
            return ok
        except Exception as e:
            logger.warning(f"[THS] health check failed: {e}")
            return False

    # ═══════════════════════════════════════════════════
    # 内部工具：板块名 → 代码 映射缓存
    # ═══════════════════════════════════════════════════

    def _ensure_industry_name_map(self):
        """确保行业板块 name→code 映射已加载"""
        if self._industry_name_to_code:
            return
        name_df = self._fetch_with_retry(
            self._ak.stock_board_industry_name_ths,
            "stock_board_industry_name_ths",
        )
        if name_df is not None and not name_df.empty:
            self._industry_name_to_code = dict(
                zip(name_df["name"], name_df["code"])
            )
            logger.info(
                f"[THS] 加载行业板块映射: {len(self._industry_name_to_code)} 个"
            )

    def _ensure_concept_name_map(self):
        """确保概念板块 name→code 映射已加载"""
        if self._concept_name_to_code:
            return
        name_df = self._fetch_with_retry(
            self._ak.stock_board_concept_name_ths,
            "stock_board_concept_name_ths",
        )
        if name_df is not None and not name_df.empty:
            self._concept_name_to_code = dict(
                zip(name_df["name"], name_df["code"])
            )
            logger.info(
                f"[THS] 加载概念板块映射: {len(self._concept_name_to_code)} 个"
            )

    # ═══════════════════════════════════════════════════
    # 板块接口 1: 板块列表 + 实时行情
    # ═══════════════════════════════════════════════════

    def get_sector_board_list(self, board_type: str = "industry") -> pd.DataFrame:
        """获取板块列表 + 实时行情
        board_type: 'industry' (行业板块) 或 'concept' (概念板块)

        同花顺行业板块有 90 个，概念板块有 375+
        """
        if board_type == "industry":
            return self._get_industry_board_list()
        elif board_type == "concept":
            return self._get_concept_board_list()
        else:
            raise ValueError(f"不支持的板块类型: {board_type}")

    def _get_industry_board_list(self) -> pd.DataFrame:
        """同花顺行业板块列表（含涨跌幅、资金流、领涨股等）"""
        df = self._fetch_with_retry(
            self._ak.stock_board_industry_summary_ths,
            "stock_board_industry_summary_ths",
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # 加载 name→code 映射
        self._ensure_industry_name_map()

        rows = []
        for _, row in df.iterrows():
            name = str(row.get("板块", ""))
            rows.append({
                "board_code": self._industry_name_to_code.get(name, ""),
                "board_name": name,
                "board_type": "industry",
                "close": None,  # 同花顺 summary 没有最新价
                "pct_chg": self._safe_float(row.get("涨跌幅")),
                "volume": self._safe_float(row.get("总成交量")),  # 万手
                "amount": self._safe_float(row.get("总成交额")),  # 亿元
                "turnover_rate": None,
                "total_mv": None,
                "rise_count": int(self._safe_float(row.get("上涨家数")) or 0),
                "fall_count": int(self._safe_float(row.get("下跌家数")) or 0),
                "leading_stock": str(row.get("领涨股", "")),
                "leading_pct_chg": self._safe_float(row.get("领涨股-涨跌幅")),
                "main_force_net_inflow": self._safe_float(row.get("净流入")),  # 亿元
            })

        result = pd.DataFrame(rows)
        logger.info(f"[THS] 行业板块列表: {len(result)} 个板块")
        return result

    def _get_concept_board_list(self) -> pd.DataFrame:
        """同花顺概念板块列表

        优先使用 concept_name_ths（code+name，快），
        同时尝试用 concept_summary_ths 补充额外信息（驱动事件、龙头股等）。
        """
        # 先拉 name 列表（code + name，快速）
        name_df = self._fetch_with_retry(
            self._ak.stock_board_concept_name_ths,
            "stock_board_concept_name_ths",
        )
        if name_df is None or name_df.empty:
            return pd.DataFrame()

        # 缓存 name→code 映射
        if not self._concept_name_to_code:
            self._concept_name_to_code = dict(
                zip(name_df["name"], name_df["code"])
            )

        # 尝试拉 summary（有驱动事件、龙头股、成分股数量，但不一定覆盖全量）
        summary_map: dict[str, dict] = {}
        try:
            summary_df = self._fetch_with_retry(
                self._ak.stock_board_concept_summary_ths,
                "stock_board_concept_summary_ths",
            )
            if summary_df is not None and not summary_df.empty:
                for _, srow in summary_df.iterrows():
                    cname = str(srow.get("概念名称", ""))
                    summary_map[cname] = {
                        "leading_stock": str(srow.get("龙头股", "")),
                        "driver_event": str(srow.get("驱动事件", "")),
                        "constituent_count": int(srow.get("成分股数量", 0) or 0),
                    }
        except Exception as e:
            logger.debug(f"[THS] 概念板块 summary 获取失败（不影响列表）: {e}")

        rows = []
        for _, row in name_df.iterrows():
            name = str(row.get("name", ""))
            code = str(row.get("code", ""))
            extra = summary_map.get(name, {})
            rows.append({
                "board_code": code,
                "board_name": name,
                "board_type": "concept",
                "pct_chg": None,  # 概念板块 name 接口没有涨跌幅
                "leading_stock": extra.get("leading_stock", ""),
            })

        result = pd.DataFrame(rows)
        logger.info(f"[THS] 概念板块列表: {len(result)} 个板块")
        return result

    # ═══════════════════════════════════════════════════
    # 板块接口 2: 板块历史 K 线
    # ═══════════════════════════════════════════════════

    def get_sector_board_history(
        self, board_name: str, board_type: str = "industry",
        start_date: str = "", end_date: str = "",
        **kwargs,
    ) -> pd.DataFrame:
        """获取板块历史 K 线

        注意：概念板块 K 线接口 (stock_board_concept_index_ths) 内部会先
        拉取全量概念名→code 映射（分页请求，约 6~8s），然后查 K 线。
        如果 board_name 在映射中找不到（名称不精确匹配），会抛 KeyError。
        """
        func_map = {
            "industry": self._ak.stock_board_industry_index_ths,
            "concept": self._ak.stock_board_concept_index_ths,
        }
        func = func_map.get(board_type)
        if not func:
            raise ValueError(f"不支持的板块类型: {board_type}")

        # 对概念板块，先检查名称是否在缓存映射中（快速失败，避免白白等 6s 分页）
        if board_type == "concept" and self._concept_name_to_code:
            if board_name not in self._concept_name_to_code:
                logger.debug(
                    f"[THS] 概念板块 '{board_name}' 不在同花顺映射中，跳过"
                )
                return pd.DataFrame()

        call_kwargs = {"symbol": board_name}
        if start_date:
            call_kwargs["start_date"] = start_date.replace("-", "")
        if end_date:
            call_kwargs["end_date"] = end_date.replace("-", "")

        df = self._fetch_with_retry(
            func,
            f"stock_board_{board_type}_index_ths({board_name})",
            **call_kwargs,
        )
        if df is None or df.empty:
            return pd.DataFrame()

        column_map = {
            "日期": "date",
            "开盘价": "open",
            "收盘价": "close",
            "最高价": "high",
            "最低价": "low",
            "成交量": "volume",
            "成交额": "amount",
        }
        available = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=available)

        # 计算涨跌幅（如果不存在）
        if "pct_chg" not in df.columns and "close" in df.columns:
            df["pct_chg"] = df["close"].pct_change() * 100

        return df

    # ═══════════════════════════════════════════════════
    # 板块接口 3: 板块资金流排行
    # ═══════════════════════════════════════════════════

    def get_sector_fund_flow_rank(
        self, indicator: str = "今日", sector_type: str = "行业资金流",
    ) -> pd.DataFrame:
        """获取板块资金流排行

        同花顺的资金流数据包含在 industry_summary 接口中（净流入字段），
        但不如东财细分（没有超大单/大单/中单/小单细分）。
        概念板块没有资金流数据。
        """
        if "行业" not in sector_type:
            # 同花顺概念板块没有资金流数据
            return pd.DataFrame()

        # 行业板块的 summary 接口已经包含了净流入数据
        df = self._fetch_with_retry(
            self._ak.stock_board_industry_summary_ths,
            "stock_board_industry_summary_ths(资金流)",
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # 加载 name→code 映射（用于补充 board_code）
        self._ensure_industry_name_map()

        rows = []
        for _, row in df.iterrows():
            net_inflow = self._safe_float(row.get("净流入"))
            name = str(row.get("板块", ""))
            rows.append({
                "board_name": name,
                "board_code": self._industry_name_to_code.get(name, ""),
                "pct_chg": self._safe_float(row.get("涨跌幅")),
                "main_force_net_inflow": net_inflow * 1e8 if net_inflow else None,  # 亿→元
                "main_force_net_ratio": None,  # 同花顺没有净占比
                "board_type": "industry",
            })

        result = pd.DataFrame(rows)
        return result

    # ═══════════════════════════════════════════════════
    # 板块接口 4: 板块成分股
    # ═══════════════════════════════════════════════════

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        """获取板块成分股

        AKShare 当前版本(1.18+)没有同花顺成分股接口
        (stock_board_industry_cons_ths / stock_board_concept_cons_ths 均不存在)。
        此方法 raise NotImplementedError 以让 collector 降级到其他数据源（东财）。
        """
        raise NotImplementedError(
            "[THS] AKShare 当前版本无同花顺板块成分股接口"
        )

    # ─── 工具方法 ──────────────────────────────────────

    @staticmethod
    def _safe_float(val, default=None):
        """安全转浮点数"""
        if val is None or val == "" or val == "-":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
