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

    def get_stock_news(self, code: str, limit: int = 50) -> pd.DataFrame:
        """获取个股新闻（东方财富）
        底层接口: ak.stock_news_em(symbol=code)
        注意: AKShare API 名称可能随版本变动
        """
        try:
            df = self._ak.stock_news_em(symbol=code)
            if df is None or df.empty:
                return pd.DataFrame()

            column_map = {
                "新闻标题": "title",
                "新闻内容": "content",
                "发布时间": "publish_time",
                "文章来源": "source",
                "新闻链接": "url",
            }
            df = df.rename(columns=column_map)
            available = [c for c in ["title", "content", "publish_time", "source", "url"] if c in df.columns]
            df = df[available].head(limit)
            return df
        except Exception as e:
            logger.warning(f"[AKShare] 个股新闻获取失败 {code}: {e}")
            return pd.DataFrame()

    def get_intraday_history(
        self, code: str, frequency: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        获取分钟级 K 线数据
        底层接口: ak.stock_zh_a_hist_min_em()
        """
        logger.debug(f"[AKShare] 拉取 {code} {frequency}min {start_date} ~ {end_date}")

        df = self._fetch_with_retry(
            self._ak.stock_zh_a_hist_min_em,
            "stock_zh_a_hist_min_em",
            symbol=code,
            period=frequency,
            start_date=f"{start_date} 09:30:00",
            end_date=f"{end_date} 15:00:00",
            adjust="qfq",
        )

        if df is None or df.empty:
            return pd.DataFrame()

        column_map = {
            "时间": "datetime",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "pct_chg",
            "换手率": "turnover_rate",
        }
        df = df.rename(columns=column_map)
        df["datetime"] = pd.to_datetime(df["datetime"])

        available = [c for c in ["datetime", "open", "high", "low", "close",
                                 "volume", "amount", "pct_chg", "turnover_rate"]
                     if c in df.columns]
        df = df[available].copy()

        numeric_cols = [c for c in available if c != "datetime"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        logger.info(f"[AKShare] {code} {frequency}min 获取成功: {len(df)} 条")
        return df

    def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
        """获取公司公告（东方财富）
        底层接口: ak.stock_notice_report(symbol="全部", date=today) + 按代码过滤
        注意: AKShare >= 1.18 已将 stock_notice_report_em 重命名为 stock_notice_report，
              且不再支持按个股查询，改为按日期查全市场公告后过滤。
        """
        try:
            from datetime import datetime, timedelta

            # 逐天查最近 7 天的公告，收集够 limit 条即停
            all_dfs = []
            matched_count = 0
            today = datetime.now()
            for days_ago in range(7):
                dt = today - timedelta(days=days_ago)
                date_str = dt.strftime("%Y%m%d")
                try:
                    df = self._ak.stock_notice_report(symbol="全部", date=date_str)
                    if df is not None and not df.empty:
                        # 先过滤再收集，避免存大量无关数据
                        if "代码" in df.columns:
                            filtered = df[df["代码"] == code]
                            if not filtered.empty:
                                all_dfs.append(filtered)
                                matched_count += len(filtered)
                                if matched_count >= limit:
                                    break
                        else:
                            all_dfs.append(df)
                except Exception:
                    continue

            if not all_dfs:
                return pd.DataFrame()

            df = pd.concat(all_dfs, ignore_index=True)

            column_map = {
                "公告标题": "title",
                "公告类型": "type",
                "公告日期": "date",
                "网址": "url",
                "代码": "code",
                "名称": "name",
            }
            df = df.rename(columns=column_map)
            available = [c for c in ["title", "type", "date", "url"] if c in df.columns]
            df = df[available].head(limit)
            return df
        except Exception as e:
            logger.warning(f"[AKShare] 公司公告获取失败 {code}: {e}")
            return pd.DataFrame()

    # ── 板块数据 API ──

    def get_sector_board_list(self, board_type: str = "industry") -> pd.DataFrame:
        """获取板块列表 + 实时行情
        board_type: 'industry' (行业板块) 或 'concept' (概念板块)
        """
        import akshare as ak
        func_map = {
            "industry": ak.stock_board_industry_name_em,
            "concept": ak.stock_board_concept_name_em,
        }
        func = func_map.get(board_type)
        if not func:
            raise ValueError(f"不支持的板块类型: {board_type}")
        df = self._fetch_with_retry(func, f"stock_board_{board_type}_name_em")
        if df is None or df.empty:
            return pd.DataFrame()

        column_map = {
            "板块名称": "board_name",
            "板块代码": "board_code",
            "最新价": "close",
            "涨跌幅": "pct_chg",
            "涨跌额": "pct_chg_amount",
            "总市值": "total_mv",
            "换手率": "turnover_rate",
            "上涨家数": "rise_count",
            "下跌家数": "fall_count",
            "领涨股票": "leading_stock",
            "领涨涨跌幅": "leading_pct_chg",
        }
        available = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=available)
        df["board_type"] = board_type
        return df

    def get_sector_board_history(
        self, board_name: str, board_type: str = "industry",
        start_date: str = "", end_date: str = "",
    ) -> pd.DataFrame:
        """获取单个板块的历史 K 线
        board_name: 板块名称（如 '半导体'），可通过 get_sector_board_list 获取
        """
        import akshare as ak
        func_map = {
            "industry": ak.stock_board_industry_hist_em,
            "concept": ak.stock_board_concept_hist_em,
        }
        func = func_map.get(board_type)
        if not func:
            raise ValueError(f"不支持的板块类型: {board_type}")

        kwargs: dict = {"symbol": board_name, "adjust": ""}
        if start_date:
            kwargs["start_date"] = start_date.replace("-", "")
        if end_date:
            kwargs["end_date"] = end_date.replace("-", "")

        df = self._fetch_with_retry(func, f"stock_board_{board_type}_hist_em", **kwargs)
        if df is None or df.empty:
            return pd.DataFrame()

        column_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "涨跌幅": "pct_chg",
            "涨跌额": "pct_chg_amount",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "换手率": "turnover_rate",
        }
        available = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=available)
        return df

    def get_sector_fund_flow_rank(
        self, indicator: str = "今日", sector_type: str = "行业资金流"
    ) -> pd.DataFrame:
        """获取板块资金流排行
        indicator: '今日', '3日', '5日', '10日'
        sector_type: '行业资金流', '概念资金流'
        """
        import akshare as ak
        df = self._fetch_with_retry(
            ak.stock_sector_fund_flow_rank,
            "stock_sector_fund_flow_rank",
            indicator=indicator,
            sector_type=sector_type,
        )
        if df is None or df.empty:
            return pd.DataFrame()

        # 列名可能带有 indicator 前缀（如 "今日主力净流入-净额"），需要去除
        df.columns = df.columns.str.replace(f"{indicator}", "", regex=False)
        column_map = {
            "名称": "board_name",
            "主力净流入-净额": "main_force_net_inflow",
            "主力净流入-净占比": "main_force_net_ratio",
            "超大单净流入-净额": "super_large_net_inflow",
            "超大单净流入-净占比": "super_large_net_ratio",
            "大单净流入-净额": "large_net_inflow",
            "大单净流入-净占比": "large_net_ratio",
            "中单净流入-净额": "medium_net_inflow",
            "中单净流入-净占比": "medium_net_ratio",
            "小单净流入-净额": "small_net_inflow",
            "小单净流入-净占比": "small_net_ratio",
            "涨跌幅": "pct_chg",
        }
        available = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=available)
        df["board_type"] = "industry" if "行业" in sector_type else "concept"
        return df

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        """获取行业板块成分股"""
        import akshare as ak
        df = self._fetch_with_retry(
            ak.stock_board_industry_cons_em,
            "stock_board_industry_cons_em",
            symbol=board_name,
        )
        if df is None or df.empty:
            return pd.DataFrame()

        column_map = {
            "代码": "code",
            "名称": "name",
            "最新价": "price",
            "涨跌幅": "pct_chg",
            "涨跌额": "pct_chg_amount",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "最高": "high",
            "最低": "low",
            "今开": "open",
            "昨收": "pre_close",
            "换手率": "turnover_rate",
            "市盈率-动态": "pe_ttm",
            "市净率": "pb",
        }
        available = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=available)
        return df
