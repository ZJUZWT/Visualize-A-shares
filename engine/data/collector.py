"""
数据采集编排器 — 多源聚合 + 智能降级

职责：
1. 按优先级尝试各数据源
2. 单源失败自动降级到下一级
3. 统一输出标准化 DataFrame
"""

import time
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

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

    def get_market_history(
        self,
        stock_codes: list[str],
        days: int = 7,
        z_metric: str = "pct_chg",
    ) -> dict[str, pd.DataFrame]:
        """
        批量获取全市场历史日线 — 用于历史回放

        v2.0 改进:
        - 降低并发到 3 线程，防止 API 限流
        - 分批处理，每批之间加延迟
        - 增加单只超时和容错
        - 最多拉取 2000 只最活跃的股票（按代码排序取前2000）

        Args:
            stock_codes: 需要查询的股票代码列表
            days: 回溯天数
            z_metric: 关注的指标

        Returns:
            { date_str: DataFrame(code, pct_chg, ...) }  按日期分组
        """
        import datetime

        t0 = time.time()
        # 多拉 5 天余量（考虑节假日、周末）
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days + 10)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # 限制最多 2000 只，减少请求量
        target_codes = stock_codes[:2000]

        logger.info(
            f"📅 批量拉取 {len(target_codes)} 只股票历史日线 "
            f"({start_str} ~ {end_str})..."
        )

        # 找一个支持历史数据的源
        hist_source = None
        for source in self._sources:
            if source.name in ("akshare", "baostock"):
                hist_source = source
                break
        if hist_source is None:
            raise RuntimeError("没有可用的历史数据源")

        all_records: list[dict] = []
        failed = 0
        success = 0

        def fetch_one(code: str):
            try:
                df = hist_source.get_daily_history(code, start_str, end_str)
                if df is not None and len(df) > 0:
                    df["code"] = code
                    return df
            except Exception:
                pass
            return None

        # 降低并发到 3 线程，分批处理防限流
        BATCH_SIZE = 100
        MAX_WORKERS = 3

        for batch_start in range(0, len(target_codes), BATCH_SIZE):
            batch_codes = target_codes[batch_start:batch_start + BATCH_SIZE]
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(fetch_one, code): code
                    for code in batch_codes
                }
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result is not None:
                            for _, row in result.iterrows():
                                record = row.to_dict()
                                all_records.append(record)
                            success += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1

            # 进度日志
            done = batch_start + len(batch_codes)
            logger.info(f"  历史数据进度: {done}/{len(target_codes)} (成功{success}/失败{failed})")

            # 批次间短暂延迟，防限流
            if done < len(target_codes):
                time.sleep(0.5)

            # 如果已经拉到足够数据（>500只成功），可以提前停止
            if success >= 500 and failed > success * 2:
                logger.warning("失败率过高，提前停止拉取")
                break

        if not all_records:
            raise RuntimeError("批量历史数据拉取失败：无有效数据")

        big_df = pd.DataFrame(all_records)
        
        # 确保 date 列是字符串
        if "date" in big_df.columns:
            big_df["date"] = big_df["date"].astype(str)

        # 按日期分组，取最近 days 个交易日
        dates = sorted(big_df["date"].unique())
        recent_dates = dates[-days:] if len(dates) > days else dates

        result = {}
        for d in recent_dates:
            result[d] = big_df[big_df["date"] == d].copy()

        elapsed = time.time() - t0
        logger.info(
            f"📅 批量历史完成: {len(recent_dates)} 个交易日, "
            f"成功 {success} 只, 失败 {failed} 只, 耗时 {elapsed:.1f}s"
        )
        return result
