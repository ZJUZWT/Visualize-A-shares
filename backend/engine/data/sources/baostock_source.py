"""
BaoStock 数据源 — Level 2 备选
数据来源：证交所
特点：免费无限制、匿名可用、可多进程并行、财务数据结构化好
"""

from typing import Optional

import pandas as pd
from loguru import logger

from .base import BaseDataSource


class BaoStockSource(BaseDataSource):
    name = "baostock"
    priority = 2

    def __init__(self):
        try:
            import baostock as bs
            self._bs = bs
            self._logged_in = False
            logger.info("[BaoStock] 数据源初始化成功")
        except ImportError:
            logger.error("[BaoStock] baostock 未安装，请运行: pip install baostock")
            raise

    def _ensure_login(self):
        """确保已登录 BaoStock 服务"""
        if not self._logged_in:
            result = self._bs.login(user_id="anonymous", password="123456")
            if result.error_code == "0":
                self._logged_in = True
                logger.info("[BaoStock] 登录成功")
            else:
                logger.error(f"[BaoStock] 登录失败: {result.error_msg}")
                raise ConnectionError(f"BaoStock login failed: {result.error_msg}")

    def _logout(self):
        if self._logged_in:
            self._bs.logout()
            self._logged_in = False

    @staticmethod
    def _to_bs_code(code: str) -> str:
        """
        将纯数字代码转为 BaoStock 格式
        600000 → sh.600000
        000001 → sz.000001
        300001 → sz.300001
        """
        code = code.strip()
        if code.startswith(("sh.", "sz.")):
            return code
        if code.startswith(("6", "9")):
            return f"sh.{code}"
        return f"sz.{code}"

    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        BaoStock 不支持实时行情，抛出异常由编排器降级处理
        """
        raise NotImplementedError("[BaoStock] 不支持实时行情，请使用 AKShare")

    def get_daily_history(
        self,
        code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取个股日线历史行情
        底层接口: bs.query_history_k_data_plus()
        """
        self._ensure_login()
        bs_code = self._to_bs_code(code)
        logger.debug(f"[BaoStock] 拉取 {bs_code} 日线 {start_date} ~ {end_date}")

        fields = "date,open,high,low,close,volume,amount,pctChg,turn,isST"

        rs = self._bs.query_history_k_data_plus(
            bs_code,
            fields,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",  # 前复权
        )

        rows = []
        while (rs.error_code == "0") and rs.next():
            rows.append(rs.get_row_data())

        if not rows:
            logger.warning(f"[BaoStock] {bs_code} 无数据")
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=rs.fields)

        column_map = {
            "pctChg": "pct_chg",
            "turn": "turnover_rate",
            "isST": "is_st",
        }
        df = df.rename(columns=column_map)

        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """
        获取季频财务数据（盈利能力）
        底层接口: bs.query_profit_data() + bs.query_growth_data()
        """
        self._ensure_login()
        bs_code = self._to_bs_code(code)
        logger.debug(f"[BaoStock] 拉取 {bs_code} 财务 {year}Q{quarter}")

        result = {}

        # 1. 盈利能力
        try:
            rs = self._bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())
            if rows:
                profit_df = pd.DataFrame(rows, columns=rs.fields)
                result["roe_avg"] = profit_df.get("roeAvg", [None])[0] if len(profit_df) > 0 else None
                result["gross_margin"] = profit_df.get("gpMargin", [None])[0] if len(profit_df) > 0 else None
                result["net_margin"] = profit_df.get("npMargin", [None])[0] if len(profit_df) > 0 else None
        except Exception as e:
            logger.warning(f"[BaoStock] 盈利数据获取失败: {e}")

        # 2. 成长能力
        try:
            rs = self._bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
            rows = []
            while (rs.error_code == "0") and rs.next():
                rows.append(rs.get_row_data())
            if rows:
                growth_df = pd.DataFrame(rows, columns=rs.fields)
                result["revenue_yoy"] = growth_df.get("YOYEquity", [None])[0] if len(growth_df) > 0 else None
                result["profit_yoy"] = growth_df.get("YOYNI", [None])[0] if len(growth_df) > 0 else None
        except Exception as e:
            logger.warning(f"[BaoStock] 成长数据获取失败: {e}")

        if result:
            df = pd.DataFrame([result])
            df["code"] = code
            df["year"] = year
            df["quarter"] = quarter
            return df

        return pd.DataFrame()

    def get_intraday_history(
        self, code: str, frequency: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        获取分钟级 K 线数据
        底层接口: bs.query_history_k_data_plus(frequency="60"/"30"/"15"/"5")
        注意: BaoStock 分钟线不含 pct_chg/turnover_rate
        """
        self._ensure_login()
        bs_code = self._to_bs_code(code)
        logger.debug(f"[BaoStock] 拉取 {bs_code} {frequency}min {start_date} ~ {end_date}")

        fields = "date,time,code,open,high,low,close,volume,amount"
        rs = self._bs.query_history_k_data_plus(
            bs_code,
            fields,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            adjustflag="2",  # 前复权
        )

        rows = []
        while (rs.error_code == "0") and rs.next():
            rows.append(rs.get_row_data())

        if not rows:
            logger.warning(f"[BaoStock] {bs_code} {frequency}min 无数据")
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=rs.fields)

        # BaoStock time 格式: "20260316103000000" (YYYYMMDDHHMMSSmmm)
        # 直接从 time 字段前14位解析
        df["datetime"] = pd.to_datetime(
            df["time"].str[:14],
            format="%Y%m%d%H%M%S",
        )

        numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        logger.info(f"[BaoStock] {bs_code} {frequency}min 获取成功: {len(df)} 条")
        return df[["datetime", "open", "high", "low", "close", "volume", "amount"]].copy()

    def __del__(self):
        try:
            self._logout()
        except AttributeError:
            pass
