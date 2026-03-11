"""
数据采集编排器 — 多源聚合 + 智能降级

职责：
1. 按优先级尝试各数据源
2. 单源失败自动降级到下一级
3. 统一输出标准化 DataFrame
"""

from typing import Optional

import pandas as pd
from loguru import logger

from .sources.base import BaseDataSource
from .sources.tencent_source import TencentSource
from .sources.akshare_source import AKShareSource
from .sources.baostock_source import BaoStockSource


class DataCollector:
    """
    三级数据源编排器
    
    Level 0: Tencent  (腾讯行情，最稳定，实时快照)
    Level 1: AKShare  (实时行情 + 日线 + 基本面)
    Level 2: BaoStock (历史K线 + 财务数据)
    Fallback: 逐级降级
    """

    def __init__(self):
        self._sources: list[BaseDataSource] = []
        self._init_sources()

    def _init_sources(self):
        """初始化可用数据源"""
        # Level 0: Tencent（最稳定）
        try:
            self._sources.append(TencentSource())
        except Exception as e:
            logger.warning(f"Tencent 初始化失败: {e}")

        # Level 1: AKShare
        try:
            self._sources.append(AKShareSource())
        except Exception as e:
            logger.warning(f"AKShare 初始化失败: {e}")

        # Level 2: BaoStock
        try:
            self._sources.append(BaoStockSource())
        except Exception as e:
            logger.warning(f"BaoStock 初始化失败: {e}")

        # 按优先级排序
        self._sources.sort(key=lambda s: s.priority)

        if not self._sources:
            raise RuntimeError("没有可用的数据源！请安装 akshare 或 baostock")

        logger.info(
            f"数据采集器初始化完成，可用数据源: "
            f"{[s.name for s in self._sources]}"
        )

    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        获取全市场实时行情 — 逐级降级
        
        Returns:
            DataFrame with unified columns:
            code, name, price, pct_chg, volume, amount,
            turnover_rate, pe_ttm, pb, total_mv, circ_mv, ...
        """
        for source in self._sources:
            try:
                df = source.get_realtime_quotes()
                if df is not None and len(df) > 100:
                    logger.info(
                        f"✅ 实时行情: {source.name} 成功 "
                        f"({len(df)} 只股票)"
                    )
                    return df
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"⚠️ {source.name} 实时行情失败: {e}，尝试下一源")

        raise RuntimeError("所有数据源获取实时行情均失败")

    def get_daily_history(
        self,
        code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """获取个股日线历史 — 逐级降级"""
        for source in self._sources:
            try:
                df = source.get_daily_history(code, start_date, end_date)
                if df is not None and len(df) > 0:
                    logger.debug(f"✅ {code} 日线: {source.name} ({len(df)} 条)")
                    return df
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"⚠️ {source.name} {code} 日线失败: {e}")

        logger.error(f"❌ {code} 日线所有数据源均失败")
        return pd.DataFrame()

    def get_financial_data(
        self, code: str, year: int, quarter: int
    ) -> pd.DataFrame:
        """获取财务数据 — 逐级降级"""
        for source in self._sources:
            try:
                df = source.get_financial_data(code, year, quarter)
                if df is not None and len(df) > 0:
                    return df
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"⚠️ {source.name} {code} 财务数据失败: {e}")

        return pd.DataFrame()

    def health_check(self) -> dict:
        """检查所有数据源健康状态"""
        status = {}
        for source in self._sources:
            try:
                status[source.name] = source.health_check()
            except Exception:
                status[source.name] = False
        return status

    @property
    def available_sources(self) -> list[str]:
        return [s.name for s in self._sources]
