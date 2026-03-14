"""
AKShare 数据源 — Level 1 主力
数据来源：东方财富
特点：零门槛、全市场实时快照、免费无限制
"""

import time
from typing import Optional

import pandas as pd
from loguru import logger

from .base import BaseDataSource


class AKShareSource(BaseDataSource):
    name = "akshare"
    priority = 1  # 最高优先级

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # 秒

    def __init__(self):
        try:
            import akshare as ak
            self._ak = ak
            logger.info("[AKShare] 数据源初始化成功")
        except ImportError:
            logger.error("[AKShare] akshare 未安装，请运行: pip install akshare")
            raise

    def _fetch_with_retry(self, func, func_name: str, **kwargs):
        """带重试的数据拉取"""
        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = func(**kwargs) if kwargs else func()
                return result
            except Exception as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_DELAY * attempt
                    logger.warning(
                        f"[AKShare] {func_name} 第 {attempt} 次失败: {e}，"
                        f"{wait}s 后重试..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[AKShare] {func_name} {self.MAX_RETRIES} 次重试全部失败: {e}"
                    )
        raise last_err

    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        获取沪深京 A 股全市场实时行情
        底层接口: ak.stock_zh_a_spot_em()
        数据量: 约 5000+ 条
        """
        logger.info("[AKShare] 拉取全市场实时行情...")

        df = self._fetch_with_retry(
            self._ak.stock_zh_a_spot_em,
            "stock_zh_a_spot_em"
        )

        # 东方财富原始字段 → 统一字段映射
        column_map = {
            "代码": "code",
            "名称": "name",
            "最新价": "price",
            "涨跌幅": "pct_chg",
            "成交量": "volume",
            "成交额": "amount",
            "换手率": "turnover_rate",
            "市盈率-动态": "pe_ttm",
            "市净率": "pb",
            "总市值": "total_mv",
            "流通市值": "circ_mv",
            "最高": "high",
            "最低": "low",
            "今开": "open",
            "昨收": "pre_close",
        }

        df = self._standardize_quotes(df, column_map)

        # 市值从"元"转为"亿元"
        if "total_mv" in df.columns:
            df["total_mv"] = df["total_mv"] / 1e8
        if "circ_mv" in df.columns:
            df["circ_mv"] = df["circ_mv"] / 1e8

        logger.info(f"[AKShare] 实时行情获取成功: {len(df)} 只股票")
        return df

    def get_daily_history(
        self,
        code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取个股日线历史数据
        底层接口: ak.stock_zh_a_hist()
        """
        logger.debug(f"[AKShare] 拉取 {code} 日线 {start_date} ~ {end_date}")

        try:
            df = self._ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",  # 前复权
            )
        except Exception as e:
            logger.error(f"[AKShare] 日线获取失败 {code}: {e}")
            raise

        column_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "pct_chg",
        }

        df = df.rename(columns=column_map)
        available = [c for c in column_map.values() if c in df.columns]
        return df[available].copy()

    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """
        获取个股财务指标
        AKShare 财务数据通过多个接口聚合
        """
        logger.debug(f"[AKShare] 拉取 {code} 财务 {year}Q{quarter}")

        try:
            # 获取个股财务指标
            df = self._ak.stock_financial_analysis_indicator(symbol=code)

            if df is not None and len(df) > 0:
                # 筛选对应年份季度
                df["日期"] = pd.to_datetime(df["日期"])
                # 简化处理：返回最近的数据
                return df.head(4)
        except Exception as e:
            logger.warning(f"[AKShare] 财务数据获取失败 {code}: {e}")

        return pd.DataFrame()

    def get_stock_list(self) -> pd.DataFrame:
        """获取 A 股股票列表"""
        try:
            df = self._ak.stock_info_a_code_name()
            df.columns = ["code", "name"]
            return df
        except Exception as e:
            logger.error(f"[AKShare] 股票列表获取失败: {e}")
            return pd.DataFrame(columns=["code", "name"])
