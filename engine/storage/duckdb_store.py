"""
DuckDB 持久化存储层

特点：
- 嵌入式，零依赖，单文件数据库
- OLAP 列式存储，金融时序查询极快
- 原生 Pandas 集成
"""

from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
from loguru import logger

from config import DB_PATH


class DuckDBStore:
    """DuckDB 嵌入式分析数据库"""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path))
        self._init_tables()
        logger.info(f"DuckDB 初始化完成: {db_path}")

    def _init_tables(self):
        """创建核心数据表"""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_daily (
                code        VARCHAR NOT NULL,
                date        DATE NOT NULL,
                open        DOUBLE,
                high        DOUBLE,
                low         DOUBLE,
                close       DOUBLE,
                volume      BIGINT,
                amount      DOUBLE,
                pct_chg     DOUBLE,
                turnover_rate DOUBLE,
                PRIMARY KEY (code, date)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_snapshot (
                code        VARCHAR NOT NULL,
                name        VARCHAR,
                price       DOUBLE,
                pct_chg     DOUBLE,
                volume      BIGINT,
                amount      DOUBLE,
                turnover_rate DOUBLE,
                pe_ttm      DOUBLE,
                pb          DOUBLE,
                total_mv    DOUBLE,
                circ_mv     DOUBLE,
                high        DOUBLE,
                low         DOUBLE,
                open        DOUBLE,
                pre_close   DOUBLE,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (code)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_features (
                code        VARCHAR NOT NULL,
                date        DATE NOT NULL,
                -- 基本面
                pe_ttm      DOUBLE,
                pb          DOUBLE,
                roe         DOUBLE,
                roa         DOUBLE,
                gross_margin DOUBLE,
                net_margin  DOUBLE,
                revenue_yoy DOUBLE,
                profit_yoy  DOUBLE,
                total_mv    DOUBLE,
                circ_mv     DOUBLE,
                -- 技术面
                volatility_20d  DOUBLE,
                volatility_60d  DOUBLE,
                beta            DOUBLE,
                rsi_14          DOUBLE,
                ma_deviation_20 DOUBLE,
                ma_deviation_60 DOUBLE,
                momentum_20d    DOUBLE,
                -- 资金面
                turnover_rate   DOUBLE,
                volume_ratio    DOUBLE,
                PRIMARY KEY (code, date)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cluster_results (
                date            DATE NOT NULL,
                code            VARCHAR NOT NULL,
                name            VARCHAR,
                cluster_id      INTEGER,
                x               DOUBLE,
                y               DOUBLE,
                z               DOUBLE,
                PRIMARY KEY (date, code)
            )
        """)

        logger.info("数据表初始化完成")

    def save_snapshot(self, df: pd.DataFrame):
        """保存实时行情快照（UPSERT）"""
        if df.empty:
            return

        # 使用临时表实现 UPSERT
        self._conn.execute("CREATE OR REPLACE TEMP TABLE tmp_snapshot AS SELECT * FROM stock_snapshot WHERE 1=0")
        self._conn.execute("INSERT INTO tmp_snapshot SELECT *, CURRENT_TIMESTAMP FROM df")

        self._conn.execute("""
            INSERT OR REPLACE INTO stock_snapshot
            SELECT * FROM tmp_snapshot
        """)

        logger.info(f"快照保存: {len(df)} 条")

    def save_daily(self, df: pd.DataFrame):
        """保存日线数据（追加去重）"""
        if df.empty:
            return
        self._conn.execute("""
            INSERT OR REPLACE INTO stock_daily
            SELECT code, date, open, high, low, close, 
                   volume, amount, pct_chg, turnover_rate
            FROM df
        """)

    def save_features(self, df: pd.DataFrame):
        """保存特征数据"""
        if df.empty:
            return
        self._conn.execute("INSERT OR REPLACE INTO stock_features SELECT * FROM df")

    def save_cluster_results(self, df: pd.DataFrame):
        """保存聚类+降维结果"""
        if df.empty:
            return
        self._conn.execute("INSERT OR REPLACE INTO cluster_results SELECT * FROM df")

    def get_snapshot(self) -> pd.DataFrame:
        """获取最新快照"""
        return self._conn.execute("SELECT * FROM stock_snapshot ORDER BY code").fetchdf()

    def get_daily(
        self, code: str, start_date: str = "", end_date: str = ""
    ) -> pd.DataFrame:
        """获取日线数据"""
        query = "SELECT * FROM stock_daily WHERE code = ?"
        params = [code]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date"
        return self._conn.execute(query, params).fetchdf()

    def get_latest_features(self) -> pd.DataFrame:
        """获取最新的特征数据"""
        return self._conn.execute("""
            SELECT * FROM stock_features
            WHERE date = (SELECT MAX(date) FROM stock_features)
            ORDER BY code
        """).fetchdf()

    def get_cluster_results(self, date: str = "") -> pd.DataFrame:
        """获取聚类结果"""
        if date:
            return self._conn.execute(
                "SELECT * FROM cluster_results WHERE date = ? ORDER BY code",
                [date],
            ).fetchdf()
        return self._conn.execute("""
            SELECT * FROM cluster_results
            WHERE date = (SELECT MAX(date) FROM cluster_results)
            ORDER BY code
        """).fetchdf()

    def get_stock_count(self) -> int:
        """获取股票数量"""
        result = self._conn.execute("SELECT COUNT(DISTINCT code) FROM stock_snapshot").fetchone()
        return result[0] if result else 0

    def close(self):
        self._conn.close()
        logger.info("DuckDB 连接已关闭")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
