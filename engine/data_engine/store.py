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
        
        # 尝试连接，如果文件锁冲突则使用备用路径
        try:
            self._conn = duckdb.connect(str(db_path))
        except Exception as e:
            if "lock" in str(e).lower():
                alt_path = db_path.parent / "stockterrain_v2.duckdb"
                logger.warning(f"DuckDB 文件锁冲突，使用备用路径: {alt_path}")
                self._conn = duckdb.connect(str(alt_path))
                self._db_path = alt_path
            else:
                raise
        
        self._init_tables()
        logger.info(f"DuckDB 初始化完成: {self._db_path}")

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
                wb_ratio    DOUBLE,
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

        # 每日快照历史表（用于回放）
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_snapshot_daily (
                code        VARCHAR NOT NULL,
                name        VARCHAR,
                date        DATE NOT NULL,
                price       DOUBLE,
                pct_chg     DOUBLE,
                volume      BIGINT,
                amount      DOUBLE,
                turnover_rate DOUBLE,
                pe_ttm      DOUBLE,
                pb          DOUBLE,
                total_mv    DOUBLE,
                circ_mv     DOUBLE,
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

        # ── InfoEngine schema ──
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS info")
        self._conn.execute("CREATE SEQUENCE IF NOT EXISTS info.news_articles_id_seq START 1")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS info.news_articles (
                id              INTEGER PRIMARY KEY DEFAULT nextval('info.news_articles_id_seq'),
                code            VARCHAR NOT NULL,
                title           VARCHAR NOT NULL,
                content         VARCHAR,
                source          VARCHAR,
                publish_time    VARCHAR,
                url             VARCHAR,
                sentiment       VARCHAR,
                sentiment_score DOUBLE,
                analyzed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, title)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS info.announcements (
                id              INTEGER PRIMARY KEY,
                code            VARCHAR NOT NULL,
                title           VARCHAR NOT NULL,
                type            VARCHAR,
                date            VARCHAR,
                url             VARCHAR,
                sentiment       VARCHAR,
                analyzed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS info.event_impacts (
                id              INTEGER PRIMARY KEY,
                code            VARCHAR NOT NULL,
                event_desc      VARCHAR NOT NULL,
                impact          VARCHAR,
                magnitude       VARCHAR,
                reasoning       VARCHAR,
                affected_factors VARCHAR,
                assessed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # shared schema
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS shared")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shared.llm_cache (
                cache_key    VARCHAR PRIMARY KEY,
                prompt_hash  VARCHAR NOT NULL,
                result_json  TEXT NOT NULL,
                model        VARCHAR DEFAULT '',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS shared.chat_history_id_seq
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shared.chat_history (
                id           INTEGER PRIMARY KEY DEFAULT NEXTVAL('shared.chat_history_id_seq'),
                session_id   VARCHAR NOT NULL,
                role         VARCHAR NOT NULL,
                content      TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_history_session
            ON shared.chat_history(session_id, created_at)
        """)

        # 行业认知缓存
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shared.industry_cognition (
                industry    VARCHAR NOT NULL,
                as_of_date  VARCHAR NOT NULL,
                target      VARCHAR NOT NULL,
                cognition_json TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (industry, as_of_date)
            )
        """)

        logger.info("数据表初始化完成")

        # ─── 迁移：为已有表添加新列 ────────────────────
        self._migrate_add_column("stock_snapshot", "wb_ratio", "DOUBLE DEFAULT 0")

    def _migrate_add_column(self, table: str, column: str, col_type: str):
        """安全地给已有表添加新列（如果不存在的话）"""
        try:
            cols = [
                r[0] for r in
                self._conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            ]
            if column not in cols:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                logger.info(f"迁移: {table} 新增列 {column}")
        except Exception as e:
            logger.warning(f"迁移 {table}.{column} 失败(非致命): {e}")

    def save_snapshot(self, df: pd.DataFrame):
        """保存实时行情快照（UPSERT）并同时存入每日历史"""
        if df.empty:
            return

        # 显式指定列及顺序，确保与表结构对齐
        snapshot_cols = [
            "code", "name", "price", "pct_chg", "volume", "amount",
            "turnover_rate", "pe_ttm", "pb", "total_mv", "circ_mv",
            "high", "low", "open", "pre_close", "wb_ratio",
        ]
        # 确保 df 有所有列（缺失的填 0）
        for col in snapshot_cols:
            if col not in df.columns:
                df[col] = 0
        insert_cols = ", ".join(snapshot_cols)
        select_cols = ", ".join(f'df."{c}"' for c in snapshot_cols)

        self._conn.execute(
            f"CREATE OR REPLACE TEMP TABLE tmp_snapshot AS SELECT * FROM stock_snapshot WHERE 1=0"
        )
        self._conn.execute(
            f"INSERT INTO tmp_snapshot ({insert_cols}, updated_at) "
            f"SELECT {select_cols}, CURRENT_TIMESTAMP FROM df"
        )

        self._conn.execute("""
            INSERT OR REPLACE INTO stock_snapshot
            SELECT * FROM tmp_snapshot
        """)

        # 同时存入每日历史表
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO stock_snapshot_daily
                SELECT code, name, CURRENT_DATE, price, pct_chg,
                       volume, amount, turnover_rate, pe_ttm, pb,
                       total_mv, circ_mv
                FROM df
            """)
            logger.info(f"快照保存: {len(df)} 条 (含每日历史)")
        except Exception as e:
            logger.warning(f"每日快照写入失败(非致命): {e}")
            logger.info(f"快照保存: {len(df)} 条")

    def get_snapshot_daily_dates(self) -> list[str]:
        """获取已保存的每日快照日期列表"""
        try:
            result = self._conn.execute("""
                SELECT DISTINCT date FROM stock_snapshot_daily
                ORDER BY date DESC
            """).fetchdf()
            return [str(d) for d in result["date"].tolist()]
        except Exception:
            return []

    def get_snapshot_daily(self, date: str) -> pd.DataFrame:
        """获取指定日期的快照"""
        try:
            return self._conn.execute(
                "SELECT * FROM stock_snapshot_daily WHERE date = ? ORDER BY code",
                [date],
            ).fetchdf()
        except Exception:
            return pd.DataFrame()

    def get_snapshot_daily_range(self, days: int = 7) -> dict[str, pd.DataFrame]:
        """获取最近 N 天的每日快照，按日期分组返回"""
        try:
            dates = self.get_snapshot_daily_dates()
            recent = dates[:days]
            result = {}
            for d in sorted(recent):
                result[d] = self.get_snapshot_daily(d)
            return result
        except Exception:
            return {}

    def save_history_as_snapshots(self, history_by_date: dict[str, "pd.DataFrame"]):
        """
        将远程拉取的历史日线数据写入 stock_snapshot_daily 表
        
        这样下次请求历史回放时可以直接从本地读取，无需再次远程拉取。
        
        Args:
            history_by_date: { date_str: DataFrame(code, pct_chg, volume, ...) }
        """
        total = 0
        for date_str, day_df in history_by_date.items():
            if day_df.empty:
                continue
            try:
                # 构造与 stock_snapshot_daily 表匹配的 DataFrame
                snap = pd.DataFrame()
                snap["code"] = day_df["code"].astype(str) if "code" in day_df.columns else ""
                snap["name"] = day_df["name"].astype(str) if "name" in day_df.columns else ""
                snap["date"] = date_str
                snap["price"] = pd.to_numeric(day_df.get("close", day_df.get("price", 0)), errors="coerce").fillna(0)
                snap["pct_chg"] = pd.to_numeric(day_df.get("pct_chg", 0), errors="coerce").fillna(0)
                snap["volume"] = pd.to_numeric(day_df.get("volume", 0), errors="coerce").fillna(0).astype(int)
                snap["amount"] = pd.to_numeric(day_df.get("amount", 0), errors="coerce").fillna(0)
                snap["turnover_rate"] = pd.to_numeric(day_df.get("turnover_rate", day_df.get("turn", 0)), errors="coerce").fillna(0)
                snap["pe_ttm"] = pd.to_numeric(day_df.get("pe_ttm", 0), errors="coerce").fillna(0)
                snap["pb"] = pd.to_numeric(day_df.get("pb", 0), errors="coerce").fillna(0)
                snap["total_mv"] = pd.to_numeric(day_df.get("total_mv", 0), errors="coerce").fillna(0)
                snap["circ_mv"] = pd.to_numeric(day_df.get("circ_mv", 0), errors="coerce").fillna(0)

                self._conn.execute("""
                    INSERT OR REPLACE INTO stock_snapshot_daily
                    SELECT code, name, date::DATE, price, pct_chg,
                           volume, amount, turnover_rate, pe_ttm, pb,
                           total_mv, circ_mv
                    FROM snap
                """)
                total += len(snap)
            except Exception as e:
                logger.warning(f"写入快照 {date_str} 失败: {e}")

        if total > 0:
            logger.info(f"📦 历史快照持久化完成: {len(history_by_date)} 天, {total} 条记录")

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

    def get_llm_cache(self, cache_key: str) -> str | None:
        """查询 LLM 结果缓存，返回 result_json 或 None"""
        try:
            row = self._conn.execute(
                "SELECT result_json FROM shared.llm_cache WHERE cache_key = ?",
                [cache_key],
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f"llm_cache 查询失败: {e}")
            return None

    def set_llm_cache(self, cache_key: str, prompt_hash: str, result_json: str, model: str = "") -> None:
        """写入 LLM 结果缓存（INSERT OR REPLACE）"""
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO shared.llm_cache
                    (cache_key, prompt_hash, result_json, model)
                VALUES (?, ?, ?, ?)
            """, [cache_key, prompt_hash, result_json, model])
        except Exception as e:
            logger.warning(f"llm_cache 写入失败: {e}")

    def append_chat_history(self, session_id: str, role: str, content: str) -> None:
        """追加一条对话历史"""
        try:
            self._conn.execute("""
                INSERT INTO shared.chat_history (session_id, role, content)
                VALUES (?, ?, ?)
            """, [session_id, role, content])
        except Exception as e:
            logger.warning(f"chat_history 写入失败: {e}")

    def get_chat_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """获取指定会话的历史消息，按时间正序"""
        try:
            rows = self._conn.execute("""
                SELECT role, content, created_at
                FROM shared.chat_history
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            """, [session_id, limit]).fetchall()
            return [{"role": r[0], "content": r[1], "created_at": str(r[2])} for r in rows]
        except Exception as e:
            logger.warning(f"chat_history 查询失败: {e}")
            return []

    def close(self):
        self._conn.close()
        logger.info("DuckDB 连接已关闭")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
