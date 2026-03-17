"""
东方财富直连数据源 — Level 0.5 板块首选
数据来源：东方财富 push2 / push2his / datacenter-web HTTP API
特点：纯 httpx 持久连接池、板块完整支持、全局并发限流防封

v2: 从 requests.Session → httpx.Client 持久连接池
    + 全局并发信号量（同一时刻最多 N 个请求），彻底解决 RemoteDisconnected
"""

import json
import math
import random
import re
import threading
import time
from typing import Optional

import pandas as pd
import httpx
from loguru import logger

from .base import BaseDataSource

# ─── 随机 User-Agent 池 ──────────────────────────────
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ─── 全局并发信号量：限制对东财服务器的同时请求数 ────────
_EASTMONEY_SEMAPHORE = threading.Semaphore(3)  # 最多 3 个并发请求
_LAST_REQUEST_TIME = 0.0
_REQUEST_LOCK = threading.Lock()
_MIN_INTERVAL = 0.3  # 两次请求间最小间隔（秒）

# ─── 断路器：连续失败后快速跳过，避免反复打不可用的东财 ──
_CIRCUIT_BREAKER_LOCK = threading.Lock()
_CONSECUTIVE_FAILURES = 0
_CIRCUIT_OPEN_UNTIL = 0.0  # monotonic 时间戳
_CIRCUIT_FAILURE_THRESHOLD = 3  # 连续失败 N 次后触发断路
_CIRCUIT_COOLDOWN = 120  # 断路冷却时间（秒），冷却后自动恢复半开状态


def _circuit_is_open() -> bool:
    """检查断路器是否打开（东财不可用）"""
    with _CIRCUIT_BREAKER_LOCK:
        if _CONSECUTIVE_FAILURES >= _CIRCUIT_FAILURE_THRESHOLD:
            if time.monotonic() < _CIRCUIT_OPEN_UNTIL:
                return True
            # 冷却期过了 → 进入半开状态，允许一次试探
    return False


def _circuit_record_success():
    """记录成功 → 关闭断路器"""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_OPEN_UNTIL
    with _CIRCUIT_BREAKER_LOCK:
        _CONSECUTIVE_FAILURES = 0
        _CIRCUIT_OPEN_UNTIL = 0.0


def _circuit_record_failure():
    """记录失败 → 累计达到阈值时打开断路器"""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_OPEN_UNTIL
    with _CIRCUIT_BREAKER_LOCK:
        _CONSECUTIVE_FAILURES += 1
        if _CONSECUTIVE_FAILURES >= _CIRCUIT_FAILURE_THRESHOLD:
            _CIRCUIT_OPEN_UNTIL = time.monotonic() + _CIRCUIT_COOLDOWN
            logger.warning(
                f"🔌 东财断路器打开: 连续 {_CONSECUTIVE_FAILURES} 次失败，"
                f"冷却 {_CIRCUIT_COOLDOWN}s 后重试"
            )


class EastMoneyDirectSource(BaseDataSource):
    """东方财富直连数据源 — 完全不依赖 akshare"""

    name = "eastmoney_direct"
    priority = 0.5  # 板块数据首选（比 AKShare 优先）

    # API 端点
    _REALTIME_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    _KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    _FINANCE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

    # 请求配置
    TIMEOUT = 20
    MAX_RETRIES = 4
    RETRY_BASE_DELAY = 1.5

    def __init__(self):
        # httpx.Client 内建连接池 + HTTP/2 + keep-alive
        self._client = httpx.Client(
            headers={
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            timeout=httpx.Timeout(self.TIMEOUT, connect=10),
            limits=httpx.Limits(
                max_connections=10,       # 连接池最大连接数
                max_keepalive_connections=5,  # keep-alive 连接数
                keepalive_expiry=30,      # keep-alive 过期时间（秒）
            ),
            follow_redirects=True,
            http2=False,  # 东财不支持 HTTP/2
        )
        logger.info("[EastMoneyDirect] 数据源初始化成功 (httpx 持久连接池)")

    # ─── 通用工具 ──────────────────────────────────────

    def _rand_ua(self) -> str:
        return random.choice(_USER_AGENTS)

    def _throttle(self):
        """全局节流：确保请求间有最小间隔"""
        global _LAST_REQUEST_TIME
        with _REQUEST_LOCK:
            now = time.monotonic()
            elapsed = now - _LAST_REQUEST_TIME
            if elapsed < _MIN_INTERVAL:
                time.sleep(_MIN_INTERVAL - elapsed + random.uniform(0, 0.1))
            _LAST_REQUEST_TIME = time.monotonic()

    def _get_json(self, url: str, params: dict, desc: str = "") -> Optional[dict]:
        """带重试 + 全局并发限流 + 断路器的 JSON 请求"""
        # 断路器：东财不可用时快速返回 None
        if _circuit_is_open():
            logger.debug(f"[EastMoneyDirect] {desc} 断路器打开，跳过请求")
            return None

        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            # 全局并发限流
            acquired = _EASTMONEY_SEMAPHORE.acquire(timeout=30)
            if not acquired:
                logger.warning(f"[EastMoneyDirect] {desc} 并发限流等待超时")
                continue
            try:
                self._throttle()
                headers = {"User-Agent": self._rand_ua()}
                resp = self._client.get(url, params=params, headers=headers)
                resp.raise_for_status()

                text = resp.text.strip()
                # 处理 JSONP 响应（有些接口会返回 jQuery...({...})）
                if text.startswith("jQuery") or text.startswith("callback"):
                    match = re.search(r"\((.+)\)$", text, re.DOTALL)
                    if match:
                        text = match.group(1)

                data = json.loads(text)
                _circuit_record_success()
                return data
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
                # 连接级错误 → 记录断路器失败 + 重建连接池
                last_err = e
                _circuit_record_failure()
                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0.5, 1.5)
                    logger.warning(
                        f"[EastMoneyDirect] {desc} 第 {attempt} 次连接断开: "
                        f"{type(e).__name__}，{wait:.1f}s 后重试..."
                    )
                    time.sleep(wait)
                    # 重建连接池（清理断开的连接）
                    try:
                        self._client.close()
                        self._client = httpx.Client(
                            headers={
                                "Referer": "https://quote.eastmoney.com/",
                                "Accept": "application/json, text/plain, */*",
                                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                            },
                            timeout=httpx.Timeout(self.TIMEOUT, connect=10),
                            limits=httpx.Limits(
                                max_connections=10,
                                max_keepalive_connections=5,
                                keepalive_expiry=30,
                            ),
                            follow_redirects=True,
                        )
                    except Exception:
                        pass
                    # 如果断路器已打开，直接退出重试循环
                    if _circuit_is_open():
                        logger.info(
                            f"[EastMoneyDirect] {desc} 断路器已打开，停止重试"
                        )
                        break
                else:
                    logger.error(
                        f"[EastMoneyDirect] {desc} {self.MAX_RETRIES} 次重试全部失败: {e}"
                    )
            except Exception as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(
                        f"[EastMoneyDirect] {desc} 第 {attempt} 次失败: {e}，"
                        f"{wait:.1f}s 后重试..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[EastMoneyDirect] {desc} {self.MAX_RETRIES} 次重试全部失败: {e}"
                    )
            finally:
                _EASTMONEY_SEMAPHORE.release()
        return None

    @staticmethod
    def _safe_float(val, default: float = 0.0) -> float:
        if val is None or val == "-":
            return default
        try:
            v = float(val)
            return default if (math.isnan(v) or math.isinf(v)) else v
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _gen_secid(code: str) -> str:
        """6位股票代码 → 东财 secid（1.=沪市, 0.=深市）"""
        code = code.strip()
        if code.startswith(("6", "9")):
            return f"1.{code}"
        elif code.startswith(("0", "3", "2")):
            return f"0.{code}"
        # 指数
        elif code.startswith("00"):
            return f"1.{code}"
        return f"0.{code}"

    # ═══════════════════════════════════════════════════
    # 基类必选接口 1: 全市场实时行情
    # ═══════════════════════════════════════════════════

    def get_realtime_quotes(self) -> pd.DataFrame:
        """获取全市场 A 股实时行情"""
        t0 = time.monotonic()
        logger.info("[EastMoneyDirect] 拉取全市场实时行情...")

        # 沪深 A 股: m:0+t:6 (深主板), m:0+t:80 (创业板), m:1+t:2 (沪主板), m:1+t:23 (科创板)
        all_items = []
        page = 1
        while True:
            params = {
                "pn": page,
                "pz": 5000,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23",
                "ut": "b2884a393a59ad64002292a3e90d46a5",
            }
            data = self._get_json(self._REALTIME_URL, params, "全市场行情")
            if not data or not data.get("data") or not data["data"].get("diff"):
                break
            items = data["data"]["diff"]
            all_items.extend(items)
            total = data["data"].get("total", 0)
            if len(all_items) >= total:
                break
            page += 1

        if not all_items:
            raise RuntimeError("[EastMoneyDirect] 未获取到任何行情数据")

        rows = []
        for item in all_items:
            price = self._safe_float(item.get("f2"))
            if price <= 0:
                continue
            name = item.get("f14", "")
            if "退市" in str(name):
                continue
            rows.append({
                "code": str(item.get("f12", "")),
                "name": name,
                "price": price,
                "pct_chg": self._safe_float(item.get("f3")),
                "volume": self._safe_float(item.get("f5")),
                "amount": self._safe_float(item.get("f6")),
                "turnover_rate": self._safe_float(item.get("f8")),
                "pe_ttm": self._safe_float(item.get("f9")),
                "pb": self._safe_float(item.get("f23")),
                "total_mv": self._safe_float(item.get("f20")),
                "circ_mv": self._safe_float(item.get("f21")),
                "high": self._safe_float(item.get("f15")),
                "low": self._safe_float(item.get("f16")),
                "open": self._safe_float(item.get("f17")),
                "pre_close": self._safe_float(item.get("f18")),
            })

        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset=["code"], keep="first")
        elapsed = time.monotonic() - t0
        logger.info(
            f"[EastMoneyDirect] 实时行情: {len(df)} 只股票 ({elapsed:.1f}s)"
        )
        return df

    # ═══════════════════════════════════════════════════
    # 基类必选接口 2: 个股日线历史
    # ═══════════════════════════════════════════════════

    def get_daily_history(
        self, code: str, start_date: str, end_date: str,
    ) -> pd.DataFrame:
        """获取个股日 K 线历史"""
        secid = self._gen_secid(code)
        beg = start_date.replace("-", "")
        end = end_date.replace("-", "")

        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,  # 日K
            "fqt": 1,    # 前复权
            "beg": beg,
            "end": end,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        }
        data = self._get_json(self._KLINE_URL, params, f"{code} 日K")
        if not data or not data.get("data") or not data["data"].get("klines"):
            return pd.DataFrame()

        rows = []
        for line in data["data"]["klines"]:
            # f51:日期 f52:开盘 f53:收盘 f54:最高 f55:最低 f56:成交量 f57:成交额 f58:振幅 f59:涨跌幅 f60:涨跌额 f61:换手率
            parts = line.split(",")
            if len(parts) < 11:
                continue
            rows.append({
                "date": parts[0],
                "open": self._safe_float(parts[1]),
                "close": self._safe_float(parts[2]),
                "high": self._safe_float(parts[3]),
                "low": self._safe_float(parts[4]),
                "volume": self._safe_float(parts[5]),
                "amount": self._safe_float(parts[6]),
                "amplitude": self._safe_float(parts[7]),
                "pct_chg": self._safe_float(parts[8]),
                "pct_chg_amount": self._safe_float(parts[9]),
                "turnover_rate": self._safe_float(parts[10]),
            })

        return pd.DataFrame(rows)

    # ═══════════════════════════════════════════════════
    # 基类必选接口 3: 财务数据
    # ═══════════════════════════════════════════════════

    def get_financial_data(
        self, code: str, year: int, quarter: int,
    ) -> pd.DataFrame:
        """获取季频财务数据（东财数据中心利润表）"""
        # 季度 → 报告期
        quarter_map = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
        report_date = f"{year}-{quarter_map.get(quarter, '12-31')}"

        # 确定市场后缀
        suffix = "SH" if code.startswith(("6", "9")) else "SZ"
        ts_code = f"{code}.{suffix}"

        params = {
            "sortColumns": "REPORT_DATE",
            "sortTypes": -1,
            "pageSize": 1,
            "pageNumber": 1,
            "reportName": "RPT_DMSK_FN_INCOME",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")(REPORT_DATE=\'{report_date}\')',
        }
        data = self._get_json(self._FINANCE_URL, params, f"{code} 财务")
        if not data or not data.get("result") or not data["result"].get("data"):
            return pd.DataFrame()

        raw = data["result"]["data"][0]
        # 映射为统一字段
        row = {
            "code": code,
            "report_date": report_date,
            "revenue": self._safe_float(raw.get("TOTAL_OPERATE_INCOME")),
            "net_profit": self._safe_float(raw.get("PARENT_NETPROFIT")),
            "gross_profit": self._safe_float(raw.get("OPERATE_PROFIT")),
            "total_cost": self._safe_float(raw.get("TOTAL_OPERATE_COST")),
            "revenue_yoy": self._safe_float(raw.get("TOTAL_OPERATE_INCOME_YOY")),
            "profit_yoy": self._safe_float(raw.get("PARENT_NETPROFIT_YOY")),
        }
        return pd.DataFrame([row])

    # ═══════════════════════════════════════════════════
    # 板块接口 1: 板块列表 + 实时行情
    # ═══════════════════════════════════════════════════

    def get_sector_board_list(self, board_type: str = "industry") -> pd.DataFrame:
        """获取行业/概念板块列表"""
        # m:90+t:2 = 行业板块, m:90+t:3 = 概念板块
        fs = "m:90+t:2+f:!50" if board_type == "industry" else "m:90+t:3+f:!50"

        params = {
            "pn": 1,
            "pz": 500,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": (
                "f2,f3,f4,f5,f6,f7,f8,f12,f14,f15,f16,f17,f18,"
                "f20,f104,f105,f128,f140,f141"
            ),
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }
        data = self._get_json(self._REALTIME_URL, params, f"{board_type}板块列表")
        if not data or not data.get("data") or not data["data"].get("diff"):
            return pd.DataFrame()

        rows = []
        for item in data["data"]["diff"]:
            rows.append({
                "board_code": str(item.get("f12", "")),
                "board_name": str(item.get("f14", "")),
                "board_type": board_type,
                "close": self._safe_float(item.get("f2")),
                "pct_chg": self._safe_float(item.get("f3")),
                "volume": self._safe_float(item.get("f5")),
                "amount": self._safe_float(item.get("f6")),
                "turnover_rate": self._safe_float(item.get("f8")),
                "total_mv": self._safe_float(item.get("f20")),
                "rise_count": int(self._safe_float(item.get("f104"))),
                "fall_count": int(self._safe_float(item.get("f105"))),
                "leading_stock": str(item.get("f140", "") or ""),
                "leading_pct_chg": self._safe_float(item.get("f141")),
            })

        df = pd.DataFrame(rows)
        logger.info(
            f"[EastMoneyDirect] {board_type}板块列表: {len(df)} 个板块"
        )
        return df

    # ═══════════════════════════════════════════════════
    # 板块接口 2: 板块历史 K 线
    # ═══════════════════════════════════════════════════

    def get_sector_board_history(
        self, board_name: str, board_type: str = "industry",
        start_date: str = "", end_date: str = "",
    ) -> pd.DataFrame:
        """获取板块历史 K 线（需要 board_code，通过 board_name 查找）"""
        # 先查 board_code
        board_code = self._resolve_board_code(board_name, board_type)
        if not board_code:
            logger.warning(f"[EastMoneyDirect] 未找到板块 '{board_name}' 的代码")
            return pd.DataFrame()

        secid = f"90.{board_code}"
        beg = start_date.replace("-", "") if start_date else "0"
        end = end_date.replace("-", "") if end_date else "20500101"

        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,
            "fqt": 1,
            "beg": beg,
            "end": end,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        }
        data = self._get_json(self._KLINE_URL, params, f"{board_name} 板块K线")
        if not data or not data.get("data") or not data["data"].get("klines"):
            return pd.DataFrame()

        rows = []
        for line in data["data"]["klines"]:
            parts = line.split(",")
            if len(parts) < 11:
                continue
            rows.append({
                "date": parts[0],
                "open": self._safe_float(parts[1]),
                "close": self._safe_float(parts[2]),
                "high": self._safe_float(parts[3]),
                "low": self._safe_float(parts[4]),
                "volume": self._safe_float(parts[5]),
                "amount": self._safe_float(parts[6]),
                "pct_chg": self._safe_float(parts[8]),
                "turnover_rate": self._safe_float(parts[10]),
            })

        return pd.DataFrame(rows)

    def _resolve_board_code(self, board_name: str, board_type: str) -> str:
        """通过板块名称查找板块代码（从列表接口获取）"""
        # 使用缓存避免重复请求
        cache_key = f"_board_map_{board_type}"
        if not hasattr(self, cache_key):
            df = self.get_sector_board_list(board_type)
            if not df.empty:
                name_to_code = dict(zip(df["board_name"], df["board_code"]))
                setattr(self, cache_key, name_to_code)
            else:
                setattr(self, cache_key, {})
        board_map = getattr(self, cache_key, {})
        return board_map.get(board_name, "")

    # ═══════════════════════════════════════════════════
    # 板块接口 3: 板块资金流排行
    # ═══════════════════════════════════════════════════

    def get_sector_fund_flow_rank(
        self, indicator: str = "今日", sector_type: str = "行业资金流",
    ) -> pd.DataFrame:
        """获取板块资金流排行"""
        # 板块类型
        fs = "m:90+t:2+f:!50" if "行业" in sector_type else "m:90+t:3+f:!50"

        # indicator → 字段组
        # 今日: f62(主力净流入), f184(主力净比), f66(超大单净流入), f69(超大单净比),
        #       f72(大单净流入), f75(大单净比), f78(中单净流入), f81(中单净比),
        #       f84(小单净流入), f87(小单净比)
        fields = "f3,f12,f14,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87"

        params = {
            "pn": 1,
            "pz": 500,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f62",
            "fs": fs,
            "fields": fields,
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }
        data = self._get_json(self._REALTIME_URL, params, f"{sector_type}资金流")
        if not data or not data.get("data") or not data["data"].get("diff"):
            return pd.DataFrame()

        rows = []
        for item in data["data"]["diff"]:
            rows.append({
                "board_name": str(item.get("f14", "")),
                "pct_chg": self._safe_float(item.get("f3")),
                "main_force_net_inflow": self._safe_float(item.get("f62")),
                "main_force_net_ratio": self._safe_float(item.get("f184")),
                "super_large_net_inflow": self._safe_float(item.get("f66")),
                "super_large_net_ratio": self._safe_float(item.get("f69")),
                "large_net_inflow": self._safe_float(item.get("f72")),
                "large_net_ratio": self._safe_float(item.get("f75")),
                "medium_net_inflow": self._safe_float(item.get("f78")),
                "medium_net_ratio": self._safe_float(item.get("f81")),
                "small_net_inflow": self._safe_float(item.get("f84")),
                "small_net_ratio": self._safe_float(item.get("f87")),
                "board_type": "industry" if "行业" in sector_type else "concept",
            })

        df = pd.DataFrame(rows)
        logger.info(
            f"[EastMoneyDirect] {sector_type}资金流: {len(df)} 个板块"
        )
        return df

    # ═══════════════════════════════════════════════════
    # 板块接口 4: 板块成分股
    # ═══════════════════════════════════════════════════

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        """获取板块成分股"""
        # 先找 board_code
        board_code = self._resolve_board_code(board_name, "industry")
        if not board_code:
            # 尝试概念板块
            board_code = self._resolve_board_code(board_name, "concept")
        if not board_code:
            logger.warning(f"[EastMoneyDirect] 未找到板块 '{board_name}' 的代码")
            return pd.DataFrame()

        params = {
            "pn": 1,
            "pz": 1000,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": f"b:{board_code}+f:!50",
            "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f12,f14,f15,f16,f17,f18,f23",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }
        data = self._get_json(self._REALTIME_URL, params, f"{board_name}成分股")
        if not data or not data.get("data") or not data["data"].get("diff"):
            return pd.DataFrame()

        rows = []
        for item in data["data"]["diff"]:
            rows.append({
                "code": str(item.get("f12", "")),
                "name": str(item.get("f14", "")),
                "price": self._safe_float(item.get("f2")),
                "pct_chg": self._safe_float(item.get("f3")),
                "volume": self._safe_float(item.get("f5")),
                "amount": self._safe_float(item.get("f6")),
                "turnover_rate": self._safe_float(item.get("f8")),
                "pe_ttm": self._safe_float(item.get("f9")),
                "pb": self._safe_float(item.get("f23")),
                "high": self._safe_float(item.get("f15")),
                "low": self._safe_float(item.get("f16")),
                "open": self._safe_float(item.get("f17")),
                "pre_close": self._safe_float(item.get("f18")),
            })

        df = pd.DataFrame(rows)
        logger.info(
            f"[EastMoneyDirect] {board_name}成分股: {len(df)} 只"
        )
        return df

    # ═══════════════════════════════════════════════════
    # 健康检查
    # ═══════════════════════════════════════════════════

    def health_check(self) -> bool:
        """检查东财直连接口是否可用"""
        try:
            params = {
                "pn": 1, "pz": 5, "po": 1, "np": 1,
                "fltt": 2, "invt": 2, "fid": "f3",
                "fs": "m:1+t:2",
                "fields": "f2,f12,f14",
                "ut": "b2884a393a59ad64002292a3e90d46a5",
            }
            data = self._get_json(self._REALTIME_URL, params, "健康检查")
            ok = (
                data is not None
                and data.get("data") is not None
                and len(data["data"].get("diff", [])) > 0
            )
            logger.info(f"[EastMoneyDirect] health check: {'OK' if ok else 'FAIL'}")
            return ok
        except Exception as e:
            logger.warning(f"[EastMoneyDirect] health check failed: {e}")
            return False

    def __del__(self):
        """清理连接池"""
        try:
            self._client.close()
        except Exception:
            pass
