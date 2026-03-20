"""
AgentDB — Main Agent 数据库单例
独立 DuckDB 文件 (data/agent.duckdb)，长连接 + asyncio.Lock 写锁
"""
from __future__ import annotations

import asyncio

import duckdb
from loguru import logger

from config import AGENT_DB_PATH


class AgentDB:
    """Main Agent 数据库 — 单例长连接 + 写锁"""

    _instance: AgentDB | None = None
    _conn: duckdb.DuckDBPyConnection
    _write_lock: asyncio.Lock

    @classmethod
    def get_instance(cls) -> AgentDB:
        if cls._instance is None:
            raise RuntimeError("AgentDB not initialized. Call init_instance() first.")
        return cls._instance

    @classmethod
    def init_instance(cls) -> AgentDB:
        if cls._instance is not None:
            return cls._instance
        inst = cls.__new__(cls)
        inst._conn = duckdb.connect(str(AGENT_DB_PATH))
        inst._write_lock = asyncio.Lock()
        inst._init_tables()
        cls._instance = inst
        logger.info(f"AgentDB 初始化完成: {AGENT_DB_PATH}")
        return inst

    def _init_tables(self):
        """建表（幂等）"""
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS agent")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.portfolio_config (
                id VARCHAR PRIMARY KEY,
                mode VARCHAR NOT NULL DEFAULT 'live',
                initial_capital DOUBLE NOT NULL,
                cash_balance DOUBLE NOT NULL,
                sim_start_date DATE,
                sim_current_date DATE,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.positions (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                direction VARCHAR DEFAULT 'long',
                holding_type VARCHAR NOT NULL,
                entry_price DOUBLE NOT NULL,
                current_qty INTEGER NOT NULL,
                cost_basis DOUBLE NOT NULL,
                entry_date DATE NOT NULL,
                entry_reason TEXT NOT NULL,
                status VARCHAR DEFAULT 'open',
                closed_at TIMESTAMP,
                closed_reason TEXT,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.position_strategies (
                id VARCHAR PRIMARY KEY,
                position_id VARCHAR NOT NULL,
                holding_type VARCHAR NOT NULL,
                take_profit DOUBLE,
                stop_loss DOUBLE,
                reasoning TEXT NOT NULL,
                details JSON,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.trades (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                position_id VARCHAR NOT NULL,
                action VARCHAR NOT NULL,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                price DOUBLE NOT NULL,
                quantity INTEGER NOT NULL,
                amount DOUBLE NOT NULL,
                reason TEXT NOT NULL,
                thesis TEXT NOT NULL,
                data_basis JSON NOT NULL,
                risk_note TEXT NOT NULL,
                invalidation TEXT NOT NULL,
                triggered_by VARCHAR DEFAULT 'agent',
                review_result VARCHAR,
                review_note TEXT,
                review_date TIMESTAMP,
                pnl_at_review DOUBLE,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.trade_groups (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                position_id VARCHAR,
                group_type VARCHAR NOT NULL,
                trade_ids JSON NOT NULL,
                position_ids JSON,
                thesis TEXT NOT NULL,
                planned_duration VARCHAR,
                status VARCHAR DEFAULT 'executing',
                started_at TIMESTAMP DEFAULT now(),
                completed_at TIMESTAMP,
                review_eligible_after DATE,
                review_result VARCHAR,
                review_note TEXT,
                actual_pnl_pct DOUBLE,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.llm_calls (
                id VARCHAR PRIMARY KEY,
                caller VARCHAR NOT NULL,
                model VARCHAR,
                input_tokens INTEGER,
                output_tokens INTEGER,
                call_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.trade_plans (
                id VARCHAR PRIMARY KEY,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                current_price DOUBLE,
                direction VARCHAR NOT NULL,
                entry_price DOUBLE,
                entry_method TEXT,
                position_pct DOUBLE,
                take_profit DOUBLE,
                take_profit_method TEXT,
                stop_loss DOUBLE,
                stop_loss_method TEXT,
                reasoning TEXT NOT NULL,
                risk_note TEXT,
                invalidation TEXT,
                valid_until DATE,
                status VARCHAR DEFAULT 'pending',
                source_type VARCHAR DEFAULT 'expert',
                source_conversation_id VARCHAR,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """)

    async def execute_read(self, sql: str, params=None) -> list[dict]:
        return await asyncio.to_thread(self._sync_read, sql, params)

    def _sync_read(self, sql: str, params=None) -> list[dict]:
        import math
        if params:
            result = self._conn.execute(sql, params).fetchdf()
        else:
            result = self._conn.execute(sql).fetchdf()
        records = result.to_dict("records")
        # DuckDB fetchdf() 把 NULL DOUBLE 转成 NaN，这里统一转回 None
        for row in records:
            for k, v in row.items():
                if isinstance(v, float) and math.isnan(v):
                    row[k] = None
        return records

    async def execute_write(self, sql: str, params=None):
        async with self._write_lock:
            await asyncio.to_thread(self._sync_write, sql, params)

    def _sync_write(self, sql: str, params=None):
        if params:
            self._conn.execute(sql, params)
        else:
            self._conn.execute(sql)

    async def execute_transaction(self, queries: list[tuple[str, list]]):
        async with self._write_lock:
            await asyncio.to_thread(self._sync_transaction, queries)

    def _sync_transaction(self, queries: list[tuple[str, list]]):
        self._conn.begin()
        try:
            for sql, params in queries:
                if params:
                    self._conn.execute(sql, params)
                else:
                    self._conn.execute(sql)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self):
        try:
            self._conn.execute("CHECKPOINT")
        except Exception:
            pass
        self._conn.close()
        AgentDB._instance = None
        logger.info("AgentDB 连接已关闭")
