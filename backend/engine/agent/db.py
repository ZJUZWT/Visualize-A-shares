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
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.watchlist (
                id VARCHAR PRIMARY KEY,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                reason TEXT,
                added_by VARCHAR DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.agent_state (
                portfolio_id VARCHAR PRIMARY KEY,
                market_view JSON,
                position_level VARCHAR,
                sector_preferences JSON,
                risk_alerts JSON,
                source_run_id VARCHAR,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.brain_runs (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                run_type VARCHAR DEFAULT 'scheduled',
                status VARCHAR DEFAULT 'running',
                candidates JSON,
                analysis_results JSON,
                decisions JSON,
                plan_ids JSON,
                trade_ids JSON,
                error_message TEXT,
                llm_tokens_used INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT now(),
                completed_at TIMESTAMP
            )
        """)
        self._conn.execute("""
            ALTER TABLE agent.brain_runs
            ADD COLUMN IF NOT EXISTS thinking_process JSON
        """)
        self._conn.execute("""
            ALTER TABLE agent.brain_runs
            ADD COLUMN IF NOT EXISTS state_before JSON
        """)
        self._conn.execute("""
            ALTER TABLE agent.brain_runs
            ADD COLUMN IF NOT EXISTS state_after JSON
        """)
        self._conn.execute("""
            ALTER TABLE agent.brain_runs
            ADD COLUMN IF NOT EXISTS execution_summary JSON
        """)
        self._conn.execute("""
            ALTER TABLE agent.trade_plans
            ADD COLUMN IF NOT EXISTS source_run_id VARCHAR
        """)
        self._conn.execute("""
            ALTER TABLE agent.position_strategies
            ADD COLUMN IF NOT EXISTS source_run_id VARCHAR
        """)
        self._conn.execute("""
            ALTER TABLE agent.trades
            ADD COLUMN IF NOT EXISTS source_run_id VARCHAR
        """)
        self._conn.execute("""
            ALTER TABLE agent.trades
            ADD COLUMN IF NOT EXISTS source_plan_id VARCHAR
        """)
        self._conn.execute("""
            ALTER TABLE agent.trades
            ADD COLUMN IF NOT EXISTS source_strategy_id VARCHAR
        """)
        self._conn.execute("""
            ALTER TABLE agent.trades
            ADD COLUMN IF NOT EXISTS source_strategy_version INTEGER
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.review_records (
                id VARCHAR PRIMARY KEY,
                brain_run_id VARCHAR,
                trade_id VARCHAR,
                stock_code VARCHAR,
                stock_name VARCHAR,
                action VARCHAR,
                decision_price DOUBLE,
                review_price DOUBLE,
                pnl_pct DOUBLE,
                holding_days INTEGER,
                status VARCHAR,
                review_date DATE,
                review_type VARCHAR,
                created_at TIMESTAMP DEFAULT now(),
                UNIQUE (trade_id, review_date)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.weekly_summaries (
                id VARCHAR PRIMARY KEY,
                week_start DATE,
                week_end DATE,
                total_trades INTEGER,
                win_count INTEGER,
                loss_count INTEGER,
                win_rate DOUBLE,
                total_pnl_pct DOUBLE,
                best_trade_id VARCHAR,
                worst_trade_id VARCHAR,
                insights TEXT,
                created_at TIMESTAMP DEFAULT now(),
                UNIQUE (week_start)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.agent_memories (
                id VARCHAR PRIMARY KEY,
                rule_text VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                source_run_id VARCHAR,
                status VARCHAR DEFAULT 'active',
                confidence DOUBLE DEFAULT 0.5,
                verify_count INTEGER DEFAULT 0,
                verify_win INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT now(),
                retired_at TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.brain_config (
                id VARCHAR PRIMARY KEY DEFAULT 'default',
                enable_debate BOOLEAN DEFAULT false,
                max_candidates INTEGER DEFAULT 30,
                quant_top_n INTEGER DEFAULT 20,
                max_position_count INTEGER DEFAULT 10,
                single_position_pct DOUBLE DEFAULT 0.15,
                schedule_time VARCHAR DEFAULT '15:30',
                updated_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            INSERT INTO agent.brain_config (id) VALUES ('default')
            ON CONFLICT (id) DO NOTHING
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
