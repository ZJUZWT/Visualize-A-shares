"""
腾讯行情数据源 — Level 0 紧急备用
数据来源：腾讯财经 qt.gtimg.cn
特点：无任何限制、毫秒级响应、可批量查询、极其稳定
"""

import time
import math
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from loguru import logger

from .base import BaseDataSource


class TencentSource(BaseDataSource):
    name = "tencent"
    priority = 0  # 最高优先级（比 AKShare 还高）

    BASE_URL = "https://qt.gtimg.cn/q="
    BATCH_SIZE = 50  # 每次请求最多 50 只股票
    MAX_WORKERS = 10  # 并行线程数
    TIMEOUT = 8  # 超时秒数

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://finance.qq.com/",
        })
        logger.info("[Tencent] 数据源初始化成功")

    def _get_all_stock_codes(self) -> list[str]:
        """
        获取全市场 A 股代码列表
        使用 BaoStock 或硬编码范围生成
        """
        codes = []
        # 沪市主板: 600000-605999
        for i in range(600000, 606000):
            codes.append(f"sh{i}")
        # 沪市科创板: 688000-689999
        for i in range(688000, 690000):
            codes.append(f"sh{i}")
        # 深市主板: 000001-003999
        for i in range(1, 4000):
            codes.append(f"sz{i:06d}")
        # 创业板: 300000-301999
        for i in range(300000, 302000):
            codes.append(f"sz{i}")

        return codes

    def _parse_tencent_line(self, line: str) -> Optional[dict]:
        """
        解析腾讯行情单行数据
        格式: v_sh600000="1~浦发银行~600000~10.07~9.96~...";
        """
        if '="' not in line:
            return None

        try:
            # 提取 key 和 value
            key_part, val_part = line.split('="', 1)
            val_part = val_part.rstrip('";')

            if not val_part or val_part == '':
                return None

            fields = val_part.split('~')
            if len(fields) < 45:
                return None

            # 提取 code
            code_key = key_part.split('_')[-1]  # e.g. "sh600000"
            raw_code = fields[2]  # 纯数字代码

            price = self._safe_float(fields[3])
            pre_close = self._safe_float(fields[4])

            if price is None or price <= 0:
                return None

            pct_chg = self._safe_float(fields[32])
            if pct_chg is None and pre_close and pre_close > 0:
                pct_chg = (price - pre_close) / pre_close * 100

            # 委比 = (委买总量 - 委卖总量) / (委买总量 + 委卖总量) × 100
            # 买一~买五手数: fields[10,12,14,16,18]
            # 卖一~卖五手数: fields[20,22,24,26,28]
            bid_vol = sum(
                self._safe_float(fields[i]) or 0
                for i in (10, 12, 14, 16, 18)
            )
            ask_vol = sum(
                self._safe_float(fields[i]) or 0
                for i in (20, 22, 24, 26, 28)
            )
            total_委 = bid_vol + ask_vol
            wb_ratio = (
                round((bid_vol - ask_vol) / total_委 * 100, 2)
                if total_委 > 0 else 0.0
            )

            return {
                "code": raw_code,
                "name": fields[1],
                "price": price,
                "pre_close": pre_close,
                "open": self._safe_float(fields[5]),
                "high": self._safe_float(fields[33]) or self._safe_float(fields[3]),
                "low": self._safe_float(fields[34]) or self._safe_float(fields[3]),
                "pct_chg": round(pct_chg, 4) if pct_chg is not None else 0.0,
                "volume": self._safe_float(fields[6]) or 0,
                "amount": self._safe_float(fields[37]) or 0,
                "turnover_rate": self._safe_float(fields[38]) or 0,
                "pe_ttm": self._safe_float(fields[39]) or 0,
                "pb": self._safe_float(fields[46]) if len(fields) > 46 else 0,
                "total_mv": (self._safe_float(fields[45]) or 0) / 1e4 if len(fields) > 45 else 0,
                "circ_mv": (self._safe_float(fields[44]) or 0) / 1e4 if len(fields) > 44 else 0,
                "wb_ratio": wb_ratio,
            }
        except Exception:
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """安全浮点转换"""
        try:
            v = float(val)
            return v if not math.isnan(v) and not math.isinf(v) else None
        except (ValueError, TypeError):
            return None

    def _fetch_batch(self, codes: list[str]) -> list[dict]:
        """拉取一批股票数据"""
        url = self.BASE_URL + ",".join(codes)
        try:
            resp = self._session.get(url, timeout=self.TIMEOUT)
            resp.encoding = "gbk"
            text = resp.text.strip()

            results = []
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    parsed = self._parse_tencent_line(line)
                    if parsed:
                        results.append(parsed)
            return results
        except Exception as e:
            logger.warning(f"[Tencent] 批量请求失败: {e}")
            return []

    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        获取全市场 A 股实时行情
        通过并行批量请求腾讯行情 API
        """
        logger.info("[Tencent] 拉取全市场实时行情...")
        start = time.time()

        all_codes = self._get_all_stock_codes()
        logger.info(f"[Tencent] 候选代码数: {len(all_codes)}")

        # 分批
        batches = []
        for i in range(0, len(all_codes), self.BATCH_SIZE):
            batches.append(all_codes[i:i + self.BATCH_SIZE])

        # 并行请求
        all_results = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._fetch_batch, batch): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"[Tencent] 批次失败: {e}")

        if not all_results:
            raise RuntimeError("[Tencent] 未获取到任何有效数据")

        df = pd.DataFrame(all_results)

        # 过滤无效数据
        df = df[df["price"] > 0].copy()
        df = df.drop_duplicates(subset=["code"], keep="first")

        # 过滤退市股票（名称中包含"退市"）
        if "name" in df.columns:
            delist_mask = df["name"].str.contains("退市", na=False)
            n_delist = delist_mask.sum()
            if n_delist > 0:
                logger.info(f"[Tencent] 过滤退市股票: {n_delist} 只")
                df = df[~delist_mask]

        elapsed = time.time() - start
        logger.info(
            f"[Tencent] 实时行情获取成功: {len(df)} 只股票 "
            f"({elapsed:.1f}s)"
        )

        return df

    def get_daily_history(
        self,
        code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """腾讯不提供历史数据接口，交给 BaoStock"""
        raise NotImplementedError("[Tencent] 不支持历史数据")

    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """腾讯不提供财务数据"""
        raise NotImplementedError("[Tencent] 不支持财务数据")

    def health_check(self) -> bool:
        """检查腾讯接口是否可用"""
        try:
            resp = self._session.get(
                f"{self.BASE_URL}sh600000", timeout=5
            )
            return resp.status_code == 200 and 'v_sh600000=' in resp.text
        except Exception:
            return False
