"""
混合数据访问层 — 自动选择 REST API 或 DuckDB read-only

策略：
1. 启动时探测后端是否在线（GET /api/v1/health）
2. 在线 → 优先通过 REST API 获取运行时数据
3. 离线 → 直接读 DuckDB 历史快照（read_only=True）
4. API 调用失败 → 立即降级为离线模式并重置缓存
"""

import time
from pathlib import Path

import duckdb
import httpx
import pandas as pd
from loguru import logger


class DataAccess:
    """混合数据访问 — 自动选择 API 或 DuckDB"""

    def __init__(self, api_base: str = "http://localhost:8000"):
        self._api_base = api_base.rstrip("/")
        self._is_online: bool | None = None
        self._online_checked_at: float = 0
        self._online_cache_ttl: float = 30.0
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_path: Path | None = None

    def _ensure_db(self) -> duckdb.DuckDBPyConnection:
        """懒初始化 DuckDB read-only 连接"""
        if self._conn is not None:
            return self._conn

        # 查找数据库文件
        from config import DB_PATH
        self._db_path = DB_PATH

        if not self._db_path.exists():
            raise FileNotFoundError(f"DuckDB 数据库不存在: {self._db_path}")

        self._conn = duckdb.connect(str(self._db_path), read_only=True)
        logger.info(f"DuckDB read-only 连接已建立: {self._db_path}")
        return self._conn

    def is_online(self) -> bool:
        """检查后端是否在线（带 30s 缓存）"""
        now = time.time()
        if self._is_online is not None and (now - self._online_checked_at) < self._online_cache_ttl:
            return self._is_online
        try:
            resp = httpx.get(f"{self._api_base}/api/v1/health", timeout=3.0)
            self._is_online = resp.status_code == 200
        except Exception:
            self._is_online = False
        self._online_checked_at = now
        return self._is_online

    def _on_api_error(self):
        """API 调用失败时重置在线状态缓存"""
        self._is_online = False
        self._online_checked_at = 0

    # ─── REST API 请求工具 ─────────────────────────────

    def api_get(self, path: str, params: dict | None = None, timeout: float = 15.0) -> dict | None:
        """GET 请求后端 API，失败返回 None 并降级"""
        try:
            resp = httpx.get(
                f"{self._api_base}{path}",
                params=params,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"API GET {path} 失败: {e}")
            self._on_api_error()
            return None

    def api_post(self, path: str, params: dict | None = None, timeout: float = 60.0) -> dict | None:
        """POST 请求后端 API，失败返回 None 并降级"""
        try:
            resp = httpx.post(
                f"{self._api_base}{path}",
                params=params,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return {"_error": "BUSY", "_message": "计算正在进行中，请稍后重试"}
            logger.warning(f"API POST {path} 失败: {e}")
            self._on_api_error()
            return None
        except Exception as e:
            logger.warning(f"API POST {path} 失败: {e}")
            self._on_api_error()
            return None

    def api_post_sse(self, path: str, params: dict | None = None, timeout: float = 120.0) -> dict | None:
        """POST 请求 SSE 端点，消费流并返回 complete 事件数据"""
        import json

        try:
            with httpx.stream(
                "POST",
                f"{self._api_base}{path}",
                params=params,
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                event_type = None
                data_buf = ""
                for line in resp.iter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        data_buf = line[6:]
                    elif line == "" and event_type and data_buf:
                        if event_type == "complete":
                            return json.loads(data_buf)
                        elif event_type == "error":
                            err = json.loads(data_buf)
                            return {"_error": "API_ERROR", "_message": err.get("message", "未知错误")}
                        event_type = None
                        data_buf = ""
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return {"_error": "BUSY", "_message": "计算正在进行中，请稍后重试"}
            logger.warning(f"API POST SSE {path} 失败: {e}")
            self._on_api_error()
        except Exception as e:
            logger.warning(f"API POST SSE {path} 失败: {e}")
            self._on_api_error()
        return None

    # ─── DuckDB 查询工具 ──────────────────────────────

    def db_query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        """执行 DuckDB 查询，返回 DataFrame"""
        conn = self._ensure_db()
        try:
            if params:
                return conn.execute(sql, params).fetchdf()
            return conn.execute(sql).fetchdf()
        except Exception as e:
            logger.warning(f"DuckDB 查询失败: {e}")
            return pd.DataFrame()

    def db_query_one(self, sql: str, params: list | None = None) -> tuple | None:
        """执行 DuckDB 查询，返回单行"""
        conn = self._ensure_db()
        try:
            if params:
                return conn.execute(sql, params).fetchone()
            return conn.execute(sql).fetchone()
        except Exception:
            return None

    def get_latest_snapshot(self) -> pd.DataFrame:
        """获取最新快照"""
        return self.db_query("SELECT * FROM stock_snapshot ORDER BY code")

    def get_latest_cluster_results(self) -> pd.DataFrame:
        """获取最近一天的聚类结果"""
        return self.db_query("""
            SELECT * FROM cluster_results
            WHERE date = (SELECT MAX(date) FROM cluster_results)
            ORDER BY code
        """)

    def get_snapshot_daily_latest(self) -> pd.DataFrame:
        """获取最近一天的每日快照"""
        return self.db_query("""
            SELECT * FROM stock_snapshot_daily
            WHERE date = (SELECT MAX(date) FROM stock_snapshot_daily)
            ORDER BY code
        """)

    def get_stock_detail(self, code: str) -> dict | None:
        """获取单只股票的快照数据（行情+因子字段）"""
        if self.is_online():
            # 优先从内存聚类结果搜索（含 cluster_id/rise_prob）
            data = self.api_get("/api/v1/stocks/search", params={"q": code})
            if data and data.get("results"):
                for s in data["results"]:
                    if s.get("code") == code:
                        return s
            # fallback: snapshot 接口
            stock = self.api_get(f"/api/v1/data/snapshot/{code}")
            if stock and "code" in stock:
                return stock
        # 离线降级：从 DuckDB snapshot 取
        df = self.db_query(
            "SELECT * FROM stock_snapshot WHERE code = ? LIMIT 1", [code]
        )
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def get_daily_history(self, code: str, days: int = 60) -> pd.DataFrame:
        """获取指定股票的日线历史"""
        return self.db_query(
            """SELECT * FROM stock_daily
               WHERE code = ?
               ORDER BY date DESC
               LIMIT ?""",
            [code, days],
        )

    def get_snapshot_daily_dates(self) -> list[str]:
        """获取所有快照日期"""
        df = self.db_query("SELECT DISTINCT date FROM stock_snapshot_daily ORDER BY date DESC")
        if df.empty:
            return []
        return [str(d) for d in df["date"].tolist()]

    def get_snapshot_daily_range(self, days: int = 7) -> dict[str, pd.DataFrame]:
        """获取最近 N 天的每日快照"""
        dates = self.get_snapshot_daily_dates()
        recent = dates[:days]
        result = {}
        for d in sorted(recent):
            df = self.db_query(
                "SELECT * FROM stock_snapshot_daily WHERE date = ? ORDER BY code",
                [d],
            )
            if not df.empty:
                result[d] = df
        return result

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
