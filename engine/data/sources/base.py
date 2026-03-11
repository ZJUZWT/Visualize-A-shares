"""
数据源抽象基类
所有数据源（AKShare / BaoStock / Tushare）实现此接口
"""

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd
from loguru import logger


class BaseDataSource(ABC):
    """数据源接口 — Strategy Pattern"""

    name: str = "base"
    priority: int = 0  # 优先级：数值越小越优先

    @abstractmethod
    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        获取全市场实时行情快照
        返回 DataFrame 必须包含统一字段：
            code, name, price, pct_chg, volume, amount,
            turnover_rate, pe_ttm, pb, total_mv, circ_mv,
            high, low, open, pre_close
        """
        ...

    @abstractmethod
    def get_daily_history(
        self,
        code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取个股日线历史行情
        返回: date, open, high, low, close, volume, amount, pct_chg
        """
        ...

    @abstractmethod
    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """
        获取季频财务数据
        返回: roe, roa, gross_margin, net_margin, revenue_yoy, profit_yoy, etc.
        """
        ...

    def health_check(self) -> bool:
        """检测数据源是否可用"""
        try:
            df = self.get_realtime_quotes()
            ok = df is not None and len(df) > 100
            logger.info(f"[{self.name}] health check: {'OK' if ok else 'FAIL'} ({len(df)} rows)")
            return ok
        except Exception as e:
            logger.warning(f"[{self.name}] health check failed: {e}")
            return False

    # ─── 统一字段映射 ──────────────────────────────────
    UNIFIED_QUOTE_COLUMNS = [
        "code",
        "name",
        "price",
        "pct_chg",
        "volume",
        "amount",
        "turnover_rate",
        "pe_ttm",
        "pb",
        "total_mv",
        "circ_mv",
        "high",
        "low",
        "open",
        "pre_close",
    ]

    def _standardize_quotes(self, df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
        """将数据源原始字段映射为统一字段"""
        df = df.rename(columns=column_map)

        # 只保留统一字段
        available = [c for c in self.UNIFIED_QUOTE_COLUMNS if c in df.columns]
        df = df[available].copy()

        # 类型标准化
        numeric_cols = [c for c in available if c not in ("code", "name")]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # 去除无效行
        df = df.dropna(subset=["code", "price"])
        df = df[df["price"] > 0]

        return df.reset_index(drop=True)
