# 板块研究仪表盘 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增 `/sector` 仪表盘页面，支持行业/概念板块涨跌排行、资金流热力图、成分股穿透、日期选择、板块级多因子预测和轮动预测。

**Architecture:** 扩展现有 DataEngine 数据管道（AKShareSource → DataCollector → DataEngine → DuckDBStore），新增 SectorEngine + SectorPredictor 引擎层，前端新建 `/sector` Next.js 页面，使用 Zustand store + lightweight-charts 图表。

**Tech Stack:** Python 3.12 / FastAPI / DuckDB / AKShare / Next.js 15 / React 19 / Zustand 5 / TailwindCSS 4 / lightweight-charts / TypeScript

---

## Chunk 1: 数据引擎扩展 — AKShare 板块 API + DuckDB 表

### Task 1: DuckDB sector schema + 板块表

**Files:**
- Modify: `backend/engine/data/store.py:42-256` (`_init_tables` 方法)

**Step 1: 在 `_init_tables()` 中新增 sector schema 和两张表**

在 `store.py` 第 213 行 `CREATE SCHEMA IF NOT EXISTS shared` 之后（约第 254 行 `_init_tables` 结尾之前），添加：

```python
        # ── sector 板块数据 ──
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS sector")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sector.board_daily (
                board_code VARCHAR,
                board_name VARCHAR,
                board_type VARCHAR,
                date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                pct_chg DOUBLE,
                volume DOUBLE,
                amount DOUBLE,
                turnover_rate DOUBLE,
                PRIMARY KEY (board_code, date)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sector.fund_flow_daily (
                board_code VARCHAR,
                board_name VARCHAR,
                board_type VARCHAR,
                date DATE,
                main_force_net_inflow DOUBLE,
                main_force_net_ratio DOUBLE,
                super_large_net_inflow DOUBLE,
                large_net_inflow DOUBLE,
                medium_net_inflow DOUBLE,
                small_net_inflow DOUBLE,
                PRIMARY KEY (board_code, date)
            )
        """)
```

**Step 2: 添加 save/get 方法**

在 `store.py` 文件末尾（最后一个方法之后），添加：

```python
    # ── Sector 板块数据方法 ──

    def save_sector_board_daily(self, df: pd.DataFrame):
        """保存板块日行情数据"""
        if df.empty:
            return
        required = ["board_code", "date"]
        if not all(c in df.columns for c in required):
            logger.warning(f"save_sector_board_daily: 缺少必要列 {required}")
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO sector.board_daily SELECT * FROM df"
        )
        logger.info(f"保存板块日行情: {len(df)} 条")

    def save_sector_fund_flow(self, df: pd.DataFrame):
        """保存板块资金流向数据"""
        if df.empty:
            return
        required = ["board_code", "date"]
        if not all(c in df.columns for c in required):
            logger.warning(f"save_sector_fund_flow: 缺少必要列 {required}")
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO sector.fund_flow_daily SELECT * FROM df"
        )
        logger.info(f"保存板块资金流向: {len(df)} 条")

    def get_sector_board_daily(
        self, board_type: str = "", start_date: str = "", end_date: str = ""
    ) -> pd.DataFrame:
        """查询板块日行情"""
        query = "SELECT * FROM sector.board_daily WHERE 1=1"
        params: list = []
        if board_type:
            query += " AND board_type = ?"
            params.append(board_type)
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date DESC, pct_chg DESC"
        return self._conn.execute(query, params).fetchdf()

    def get_sector_board_history(
        self, board_code: str, start_date: str = "", end_date: str = ""
    ) -> pd.DataFrame:
        """查询单个板块的历史行情"""
        query = "SELECT * FROM sector.board_daily WHERE board_code = ?"
        params: list = [board_code]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date"
        return self._conn.execute(query, params).fetchdf()

    def get_sector_fund_flow(
        self, board_type: str = "", start_date: str = "", end_date: str = ""
    ) -> pd.DataFrame:
        """查询板块资金流向"""
        query = "SELECT * FROM sector.fund_flow_daily WHERE 1=1"
        params: list = []
        if board_type:
            query += " AND board_type = ?"
            params.append(board_type)
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date DESC, main_force_net_inflow DESC"
        return self._conn.execute(query, params).fetchdf()

    def get_sector_fund_flow_history(
        self, board_code: str, start_date: str = "", end_date: str = ""
    ) -> pd.DataFrame:
        """查询单个板块的资金流向历史"""
        query = "SELECT * FROM sector.fund_flow_daily WHERE board_code = ?"
        params: list = [board_code]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date"
        return self._conn.execute(query, params).fetchdf()
```

**Step 3: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python -c "from engine.data.store import DuckDBStore; s = DuckDBStore(); print('sector tables OK')"`
Expected: 输出 `sector tables OK`，无报错

**Step 4: Commit**

```bash
git add backend/engine/data/store.py
git commit -m "feat(sector): add DuckDB sector schema + board_daily & fund_flow_daily tables"
```

---

### Task 2: AKShareSource 板块 API 封装

**Files:**
- Modify: `backend/engine/data/sources/akshare_source.py` (在最后一个方法后添加)

**Step 1: 添加 6 个板块数据方法**

在 `akshare_source.py` 文件末尾（最后一个方法 `get_announcements` 之后），添加：

```python
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

        kwargs = {"symbol": board_name, "adjust": ""}
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

        # 列名带有 indicator 前缀（如 "今日主力净流入-净额"），需要去除
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

        # 标注板块类型
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
```

**Step 2: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python -c "from engine.data.sources.akshare_source import AKShareSource; s = AKShareSource(); print([m for m in dir(s) if m.startswith('get_sector')])" `
Expected: 输出包含 4 个 `get_sector_*` 方法名

**Step 3: Commit**

```bash
git add backend/engine/data/sources/akshare_source.py
git commit -m "feat(sector): add 4 sector board AKShare API methods to AKShareSource"
```

---

### Task 3: DataCollector + DataEngine 板块方法扩展

**Files:**
- Modify: `backend/engine/data/collector.py` (在最后一个方法后添加)
- Modify: `backend/engine/data/engine.py` (在最后一个方法后添加)

**Step 1: DataCollector 新增板块编排方法**

在 `collector.py` 末尾添加：

```python
    # ── 板块数据方法 ──

    def get_sector_board_list(self, board_type: str = "industry") -> pd.DataFrame:
        """获取板块列表 + 实时行情（降级链）"""
        for source in self._sources:
            try:
                df = source.get_sector_board_list(board_type=board_type)
                if df is not None and len(df) > 5:
                    logger.info(f"[{source.name}] 获取{board_type}板块列表: {len(df)} 个板块")
                    return df
            except (NotImplementedError, AttributeError):
                continue
            except Exception as e:
                logger.warning(f"[{source.name}] 获取板块列表失败: {e}")
        logger.error("所有数据源获取板块列表均失败")
        return pd.DataFrame()

    def get_sector_board_history(
        self, board_name: str, board_type: str = "industry",
        start_date: str = "", end_date: str = "",
    ) -> pd.DataFrame:
        """获取单个板块历史 K 线（降级链）"""
        for source in self._sources:
            try:
                df = source.get_sector_board_history(
                    board_name=board_name, board_type=board_type,
                    start_date=start_date, end_date=end_date,
                )
                if df is not None and len(df) > 0:
                    return df
            except (NotImplementedError, AttributeError):
                continue
            except Exception as e:
                logger.warning(f"[{source.name}] 获取板块 {board_name} 历史失败: {e}")
        return pd.DataFrame()

    def get_sector_fund_flow_rank(
        self, indicator: str = "今日", sector_type: str = "行业资金流"
    ) -> pd.DataFrame:
        """获取板块资金流排行（降级链）"""
        for source in self._sources:
            try:
                df = source.get_sector_fund_flow_rank(
                    indicator=indicator, sector_type=sector_type,
                )
                if df is not None and len(df) > 5:
                    return df
            except (NotImplementedError, AttributeError):
                continue
            except Exception as e:
                logger.warning(f"[{source.name}] 获取板块资金流排行失败: {e}")
        return pd.DataFrame()

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        """获取板块成分股（降级链）"""
        for source in self._sources:
            try:
                df = source.get_sector_constituents(board_name=board_name)
                if df is not None and len(df) > 0:
                    return df
            except (NotImplementedError, AttributeError):
                continue
            except Exception as e:
                logger.warning(f"[{source.name}] 获取板块 {board_name} 成分股失败: {e}")
        return pd.DataFrame()
```

**Step 2: DataEngine 新增板块门面方法**

在 `engine.py` 末尾添加：

```python
    # ── 板块数据方法 ──

    def get_sector_board_list(self, board_type: str = "industry") -> pd.DataFrame:
        """获取板块列表 + 实时行情"""
        return self._collector.get_sector_board_list(board_type=board_type)

    def get_sector_board_history(
        self, board_name: str, board_code: str = "",
        board_type: str = "industry",
        start_date: str = "", end_date: str = "",
    ) -> pd.DataFrame:
        """获取板块历史 K 线（本地优先 + 远程回填）"""
        # 先查本地
        if board_code:
            local = self._store.get_sector_board_history(
                board_code, start_date=start_date, end_date=end_date
            )
            if not local.empty and len(local) >= 5:
                return local

        # 远程拉取
        df = self._collector.get_sector_board_history(
            board_name=board_name, board_type=board_type,
            start_date=start_date, end_date=end_date,
        )
        if not df.empty and board_code:
            df["board_code"] = board_code
            df["board_name"] = board_name
            df["board_type"] = board_type
            self._store.save_sector_board_daily(df)
        return df

    def get_sector_fund_flow_rank(
        self, indicator: str = "今日", sector_type: str = "行业资金流"
    ) -> pd.DataFrame:
        """获取板块资金流排行"""
        return self._collector.get_sector_fund_flow_rank(
            indicator=indicator, sector_type=sector_type
        )

    def get_sector_constituents(self, board_name: str) -> pd.DataFrame:
        """获取板块成分股"""
        return self._collector.get_sector_constituents(board_name=board_name)

    def save_sector_board_daily(self, df: pd.DataFrame):
        """保存板块日行情到 DuckDB"""
        self._store.save_sector_board_daily(df)

    def save_sector_fund_flow(self, df: pd.DataFrame):
        """保存板块资金流向到 DuckDB"""
        self._store.save_sector_fund_flow(df)
```

**Step 3: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python -c "from engine.data import get_data_engine; e = get_data_engine(); print([m for m in dir(e) if 'sector' in m])"`
Expected: 输出包含 6 个 `*sector*` 方法名

**Step 4: Commit**

```bash
git add backend/engine/data/collector.py backend/engine/data/engine.py
git commit -m "feat(sector): extend DataCollector + DataEngine with sector board methods"
```

---

## Chunk 2: SectorEngine 核心 + Schemas + Routes

### Task 4: Pydantic schemas

**Files:**
- Create: `backend/engine/sector/__init__.py`
- Create: `backend/engine/sector/schemas.py`

**Step 1: 创建 schemas**

`backend/engine/sector/__init__.py`:
```python
```

`backend/engine/sector/schemas.py`:
```python
"""板块研究仪表盘数据模型"""
from pydantic import BaseModel


class SectorBoardItem(BaseModel):
    """板块列表项"""
    board_code: str = ""
    board_name: str = ""
    board_type: str = ""  # 'industry' / 'concept'
    close: float = 0.0
    pct_chg: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    turnover_rate: float = 0.0
    total_mv: float = 0.0
    rise_count: int = 0
    fall_count: int = 0
    leading_stock: str = ""
    leading_pct_chg: float = 0.0
    # 资金流字段（可选，合并后填充）
    main_force_net_inflow: float | None = None
    main_force_net_ratio: float | None = None
    # 预测信号（可选）
    prediction_score: float | None = None
    prediction_signal: str | None = None  # 'bullish' / 'bearish' / 'neutral'


class SectorHistoryItem(BaseModel):
    """板块历史 K 线单条"""
    date: str
    open: float
    high: float
    low: float
    close: float
    pct_chg: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    turnover_rate: float = 0.0


class SectorFundFlowItem(BaseModel):
    """板块资金流向单条"""
    date: str = ""
    board_code: str = ""
    board_name: str = ""
    main_force_net_inflow: float = 0.0
    main_force_net_ratio: float = 0.0
    super_large_net_inflow: float = 0.0
    large_net_inflow: float = 0.0
    medium_net_inflow: float = 0.0
    small_net_inflow: float = 0.0


class ConstituentItem(BaseModel):
    """成分股"""
    code: str
    name: str = ""
    price: float = 0.0
    pct_chg: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    turnover_rate: float = 0.0
    pe_ttm: float | None = None
    pb: float | None = None


class SectorPredictionItem(BaseModel):
    """板块预测结果"""
    board_code: str = ""
    board_name: str = ""
    probability: float = 0.5
    signal: str = "neutral"  # 'bullish' / 'bearish' / 'neutral'
    factor_details: dict[str, float] = {}


class HeatmapCell(BaseModel):
    """热力图单元格"""
    board_code: str = ""
    board_name: str = ""
    pct_chg: float = 0.0
    main_force_net_inflow: float = 0.0
    main_force_net_ratio: float = 0.0


class RotationMatrixRow(BaseModel):
    """轮动矩阵一行（一个板块的多日资金流）"""
    board_code: str = ""
    board_name: str = ""
    daily_flows: list[float] = []  # 每日主力净流入值
    daily_dates: list[str] = []    # 对应日期
    trend_signal: str = "neutral"  # 连续流入/流出趋势
    prediction: SectorPredictionItem | None = None


class SectorBoardsResponse(BaseModel):
    boards: list[SectorBoardItem] = []
    date: str = ""
    board_type: str = ""
    total: int = 0


class SectorHistoryResponse(BaseModel):
    board_code: str = ""
    board_name: str = ""
    history: list[SectorHistoryItem] = []
    fund_flow_history: list[SectorFundFlowItem] = []


class SectorHeatmapResponse(BaseModel):
    cells: list[HeatmapCell] = []
    date: str = ""
    board_type: str = ""


class SectorRotationResponse(BaseModel):
    matrix: list[RotationMatrixRow] = []
    days: int = 10
    board_type: str = ""
    top_bullish: list[SectorPredictionItem] = []
    top_bearish: list[SectorPredictionItem] = []


class SectorConstituentsResponse(BaseModel):
    board_code: str = ""
    board_name: str = ""
    constituents: list[ConstituentItem] = []
    total: int = 0
```

**Step 2: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python -c "from engine.sector.schemas import SectorBoardsResponse; print('schemas OK')"`
Expected: `schemas OK`

**Step 3: Commit**

```bash
git add backend/engine/sector/
git commit -m "feat(sector): add Pydantic schemas for sector dashboard"
```

---

### Task 5: SectorEngine 核心引擎

**Files:**
- Create: `backend/engine/sector/engine.py`

**Step 1: 实现 SectorEngine**

```python
"""板块研究引擎 — 数据编排 + 信号合成"""
import time
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

from engine.data import get_data_engine
from engine.sector.schemas import (
    SectorBoardItem, SectorHistoryItem, SectorFundFlowItem,
    ConstituentItem, HeatmapCell, RotationMatrixRow,
    SectorBoardsResponse, SectorHistoryResponse,
    SectorHeatmapResponse, SectorRotationResponse,
    SectorConstituentsResponse, SectorPredictionItem,
)


class SectorEngine:
    """板块研究引擎"""

    def __init__(self):
        self._data = get_data_engine()

    async def get_boards(
        self, board_type: str = "industry", date: str = "",
    ) -> SectorBoardsResponse:
        """获取板块列表 + 实时行情 + 资金流 + 预测信号"""
        import asyncio
        t0 = time.monotonic()

        # 并行获取板块列表和资金流排行
        sector_type = "行业资金流" if board_type == "industry" else "概念资金流"
        board_list_df, fund_flow_df = await asyncio.gather(
            asyncio.to_thread(self._data.get_sector_board_list, board_type),
            asyncio.to_thread(
                self._data.get_sector_fund_flow_rank, "今日", sector_type
            ),
        )

        # 合并资金流数据
        items: list[SectorBoardItem] = []
        fund_flow_map: dict[str, dict] = {}
        if not fund_flow_df.empty and "board_name" in fund_flow_df.columns:
            for _, row in fund_flow_df.iterrows():
                name = row.get("board_name", "")
                fund_flow_map[name] = {
                    "main_force_net_inflow": self._safe_float(row.get("main_force_net_inflow")),
                    "main_force_net_ratio": self._safe_float(row.get("main_force_net_ratio")),
                }

        if not board_list_df.empty:
            for _, row in board_list_df.iterrows():
                name = row.get("board_name", "")
                flow = fund_flow_map.get(name, {})
                items.append(SectorBoardItem(
                    board_code=str(row.get("board_code", "")),
                    board_name=name,
                    board_type=board_type,
                    close=self._safe_float(row.get("close")),
                    pct_chg=self._safe_float(row.get("pct_chg")),
                    volume=self._safe_float(row.get("volume")),
                    amount=self._safe_float(row.get("amount")),
                    turnover_rate=self._safe_float(row.get("turnover_rate")),
                    total_mv=self._safe_float(row.get("total_mv")),
                    rise_count=int(row.get("rise_count", 0) or 0),
                    fall_count=int(row.get("fall_count", 0) or 0),
                    leading_stock=str(row.get("leading_stock", "")),
                    leading_pct_chg=self._safe_float(row.get("leading_pct_chg")),
                    main_force_net_inflow=flow.get("main_force_net_inflow"),
                    main_force_net_ratio=flow.get("main_force_net_ratio"),
                ))

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.get_boards({board_type}) 耗时 {elapsed:.1f}s, "
            f"{len(items)} 个板块"
        )

        return SectorBoardsResponse(
            boards=items,
            date=date or datetime.now().strftime("%Y-%m-%d"),
            board_type=board_type,
            total=len(items),
        )

    async def get_history(
        self, board_code: str, board_name: str,
        board_type: str = "industry",
        start_date: str = "", end_date: str = "",
    ) -> SectorHistoryResponse:
        """获取单个板块的历史行情 + 资金流时序"""
        import asyncio
        t0 = time.monotonic()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # 并行拉取 K 线和资金流历史
        hist_df, flow_df = await asyncio.gather(
            asyncio.to_thread(
                self._data.get_sector_board_history,
                board_name=board_name, board_code=board_code,
                board_type=board_type,
                start_date=start_date, end_date=end_date,
            ),
            asyncio.to_thread(
                self._data.store.get_sector_fund_flow_history,
                board_code=board_code,
                start_date=start_date, end_date=end_date,
            ),
        )

        history = []
        if not hist_df.empty:
            for _, row in hist_df.iterrows():
                history.append(SectorHistoryItem(
                    date=str(row.get("date", "")),
                    open=self._safe_float(row.get("open")),
                    high=self._safe_float(row.get("high")),
                    low=self._safe_float(row.get("low")),
                    close=self._safe_float(row.get("close")),
                    pct_chg=self._safe_float(row.get("pct_chg")),
                    volume=self._safe_float(row.get("volume")),
                    amount=self._safe_float(row.get("amount")),
                    turnover_rate=self._safe_float(row.get("turnover_rate")),
                ))

        fund_flow_history = []
        if not flow_df.empty:
            for _, row in flow_df.iterrows():
                fund_flow_history.append(SectorFundFlowItem(
                    date=str(row.get("date", "")),
                    board_code=board_code,
                    board_name=board_name,
                    main_force_net_inflow=self._safe_float(row.get("main_force_net_inflow")),
                    main_force_net_ratio=self._safe_float(row.get("main_force_net_ratio")),
                    super_large_net_inflow=self._safe_float(row.get("super_large_net_inflow")),
                    large_net_inflow=self._safe_float(row.get("large_net_inflow")),
                    medium_net_inflow=self._safe_float(row.get("medium_net_inflow")),
                    small_net_inflow=self._safe_float(row.get("small_net_inflow")),
                ))

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.get_history({board_name}) 耗时 {elapsed:.1f}s, "
            f"K线 {len(history)} 条, 资金流 {len(fund_flow_history)} 条"
        )

        return SectorHistoryResponse(
            board_code=board_code,
            board_name=board_name,
            history=history,
            fund_flow_history=fund_flow_history,
        )

    async def get_heatmap(
        self, board_type: str = "industry", date: str = "",
    ) -> SectorHeatmapResponse:
        """获取热力图数据"""
        t0 = time.monotonic()
        resp = await self.get_boards(board_type=board_type, date=date)
        cells = [
            HeatmapCell(
                board_code=b.board_code,
                board_name=b.board_name,
                pct_chg=b.pct_chg,
                main_force_net_inflow=b.main_force_net_inflow or 0.0,
                main_force_net_ratio=b.main_force_net_ratio or 0.0,
            )
            for b in resp.boards
        ]
        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ SectorEngine.get_heatmap({board_type}) 耗时 {elapsed:.1f}s")
        return SectorHeatmapResponse(
            cells=cells, date=resp.date, board_type=board_type,
        )

    async def get_constituents(
        self, board_name: str, board_code: str = "",
    ) -> SectorConstituentsResponse:
        """获取板块成分股"""
        import asyncio
        t0 = time.monotonic()
        df = await asyncio.to_thread(
            self._data.get_sector_constituents, board_name
        )
        items = []
        if not df.empty:
            for _, row in df.iterrows():
                items.append(ConstituentItem(
                    code=str(row.get("code", "")),
                    name=str(row.get("name", "")),
                    price=self._safe_float(row.get("price")),
                    pct_chg=self._safe_float(row.get("pct_chg")),
                    volume=self._safe_float(row.get("volume")),
                    amount=self._safe_float(row.get("amount")),
                    turnover_rate=self._safe_float(row.get("turnover_rate")),
                    pe_ttm=self._safe_float(row.get("pe_ttm")) or None,
                    pb=self._safe_float(row.get("pb")) or None,
                ))
        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.get_constituents({board_name}) 耗时 {elapsed:.1f}s, "
            f"{len(items)} 只成分股"
        )
        return SectorConstituentsResponse(
            board_code=board_code,
            board_name=board_name,
            constituents=items,
            total=len(items),
        )

    async def get_rotation(
        self, days: int = 10, board_type: str = "industry",
    ) -> SectorRotationResponse:
        """获取板块轮动预测"""
        t0 = time.monotonic()

        # 查询板块资金流历史（从 DuckDB）
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        flow_df = self._data.store.get_sector_fund_flow(
            board_type=board_type, start_date=start_date, end_date=end_date,
        )

        matrix: list[RotationMatrixRow] = []
        if not flow_df.empty and "board_code" in flow_df.columns:
            for code, group in flow_df.groupby("board_code"):
                group = group.sort_values("date").tail(days)
                flows = group["main_force_net_inflow"].tolist()
                dates = [str(d) for d in group["date"].tolist()]
                name = group["board_name"].iloc[0] if "board_name" in group.columns else ""

                # 趋势信号：连续正/负天数
                trend = self._calc_trend_signal(flows)

                matrix.append(RotationMatrixRow(
                    board_code=str(code),
                    board_name=str(name),
                    daily_flows=flows,
                    daily_dates=dates,
                    trend_signal=trend,
                ))

        # 排序：按最近日资金流入
        matrix.sort(key=lambda r: r.daily_flows[-1] if r.daily_flows else 0, reverse=True)

        # Top 5 看涨/看跌
        top_bullish = [
            SectorPredictionItem(
                board_code=r.board_code, board_name=r.board_name,
                signal="bullish",
            )
            for r in matrix[:5] if r.trend_signal == "bullish"
        ]
        top_bearish = [
            SectorPredictionItem(
                board_code=r.board_code, board_name=r.board_name,
                signal="bearish",
            )
            for r in reversed(matrix) if r.trend_signal == "bearish"
        ][:5]

        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ SectorEngine.get_rotation(days={days}) 耗时 {elapsed:.1f}s")

        return SectorRotationResponse(
            matrix=matrix, days=days, board_type=board_type,
            top_bullish=top_bullish, top_bearish=top_bearish,
        )

    async def fetch_and_save(self, board_type: str = "industry") -> dict:
        """触发数据采集 + 持久化"""
        import asyncio
        t0 = time.monotonic()

        sector_type = "行业资金流" if board_type == "industry" else "概念资金流"
        board_df, flow_df = await asyncio.gather(
            asyncio.to_thread(self._data.get_sector_board_list, board_type),
            asyncio.to_thread(
                self._data.get_sector_fund_flow_rank, "今日", sector_type
            ),
        )

        today = datetime.now().strftime("%Y-%m-%d")
        saved_boards = 0
        saved_flows = 0

        if not board_df.empty:
            board_df["date"] = today
            board_df["board_type"] = board_type
            self._data.save_sector_board_daily(board_df)
            saved_boards = len(board_df)

        if not flow_df.empty:
            flow_df["date"] = today
            flow_df["board_type"] = board_type
            self._data.save_sector_fund_flow(flow_df)
            saved_flows = len(flow_df)

        elapsed = time.monotonic() - t0
        logger.info(
            f"⏱️ SectorEngine.fetch_and_save({board_type}) 耗时 {elapsed:.1f}s, "
            f"保存板块行情 {saved_boards} 条, 资金流向 {saved_flows} 条"
        )

        return {
            "board_type": board_type,
            "saved_boards": saved_boards,
            "saved_flows": saved_flows,
            "elapsed_s": round(elapsed, 1),
        }

    @staticmethod
    def _safe_float(val, default: float = 0.0) -> float:
        if val is None or val == "" or val == "nan":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _calc_trend_signal(flows: list[float]) -> str:
        """根据资金流向序列计算趋势信号"""
        if not flows:
            return "neutral"
        consecutive = 0
        for v in reversed(flows):
            if v > 0:
                if consecutive >= 0:
                    consecutive += 1
                else:
                    break
            elif v < 0:
                if consecutive <= 0:
                    consecutive -= 1
                else:
                    break
            else:
                break
        if consecutive >= 3:
            return "bullish"
        elif consecutive <= -3:
            return "bearish"
        return "neutral"
```

**Step 2: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python -c "from engine.sector.engine import SectorEngine; e = SectorEngine(); print('SectorEngine OK')"`
Expected: `SectorEngine OK`

**Step 3: Commit**

```bash
git add backend/engine/sector/engine.py
git commit -m "feat(sector): implement SectorEngine core with data orchestration + timing stats"
```

---

### Task 6: FastAPI Routes + 注册到 main.py

**Files:**
- Create: `backend/engine/sector/routes.py`
- Modify: `backend/main.py:25-33` (导入) 和 `87-95` (注册 router)

**Step 1: 创建 routes.py**

```python
"""板块研究仪表盘 API 路由"""
from fastapi import APIRouter, Query
from engine.sector.engine import SectorEngine
from engine.sector.schemas import (
    SectorBoardsResponse, SectorHistoryResponse,
    SectorHeatmapResponse, SectorRotationResponse,
    SectorConstituentsResponse,
)

router = APIRouter(prefix="/api/v1/sector", tags=["sector"])

_engine: SectorEngine | None = None


def _get_engine() -> SectorEngine:
    global _engine
    if _engine is None:
        _engine = SectorEngine()
    return _engine


@router.get("/boards", response_model=SectorBoardsResponse)
async def get_boards(
    type: str = Query("industry", description="板块类型: industry / concept"),
    date: str = Query("", description="日期 (YYYY-MM-DD)，默认今天"),
):
    """获取板块列表 + 涨跌 + 资金流"""
    engine = _get_engine()
    return await engine.get_boards(board_type=type, date=date)


@router.get("/{board_code}/history", response_model=SectorHistoryResponse)
async def get_history(
    board_code: str,
    board_name: str = Query("", description="板块名称"),
    board_type: str = Query("industry"),
    start: str = Query("", description="开始日期"),
    end: str = Query("", description="结束日期"),
):
    """获取板块历史行情 + 资金流时序"""
    engine = _get_engine()
    return await engine.get_history(
        board_code=board_code, board_name=board_name,
        board_type=board_type,
        start_date=start, end_date=end,
    )


@router.get("/{board_code}/constituents", response_model=SectorConstituentsResponse)
async def get_constituents(
    board_code: str,
    board_name: str = Query("", description="板块名称"),
):
    """获取板块成分股"""
    engine = _get_engine()
    return await engine.get_constituents(
        board_name=board_name, board_code=board_code,
    )


@router.get("/heatmap", response_model=SectorHeatmapResponse)
async def get_heatmap(
    type: str = Query("industry"),
    date: str = Query(""),
):
    """获取热力图数据"""
    engine = _get_engine()
    return await engine.get_heatmap(board_type=type, date=date)


@router.get("/rotation", response_model=SectorRotationResponse)
async def get_rotation(
    days: int = Query(10, description="回溯天数"),
    type: str = Query("industry"),
):
    """获取轮动预测"""
    engine = _get_engine()
    return await engine.get_rotation(days=days, board_type=type)


@router.post("/fetch")
async def fetch_sector_data(
    type: str = Query("industry"),
):
    """触发板块数据采集"""
    engine = _get_engine()
    return await engine.fetch_and_save(board_type=type)
```

**Step 2: 注册到 main.py**

在 `main.py` 第 33 行 `from engine.industry.routes import router as industry_router` 之后添加：
```python
from engine.sector.routes import router as sector_router
```

在 `main.py` 第 95 行 `app.include_router(industry_router)` 之后添加：
```python
app.include_router(sector_router)
```

**Step 3: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python -c "from main import app; routes = [r.path for r in app.routes]; sector_routes = [r for r in routes if '/sector' in r]; print(f'Sector routes: {sector_routes}')"`
Expected: 输出包含 6 个 `/api/v1/sector/*` 路由

**Step 4: Commit**

```bash
git add backend/engine/sector/routes.py backend/main.py
git commit -m "feat(sector): add FastAPI sector routes + register in main.py"
```

---

## Chunk 3: SectorPredictor 因子系统 + 轮动预测

### Task 7: SectorPredictor 实现

**Files:**
- Create: `backend/engine/sector/predictor.py`
- Modify: `backend/engine/sector/engine.py` (集成预测到 get_boards 和 get_rotation)

**Step 1: 创建 predictor.py**

```python
"""板块级多因子预测 + 轮动预测模型

与 StockPredictorV2 同架构：MAD去极值 → Z-Score → 正交化 → 加权 → 正态CDF
"""
import time
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy import stats
from loguru import logger


@dataclass
class SectorFactorDef:
    name: str
    direction: int          # +1=因子越大越看涨, -1=因子越大越看跌
    group: str = ""
    default_weight: float = 0.0
    desc: str = ""


SECTOR_FACTOR_DEFS: list[SectorFactorDef] = [
    SectorFactorDef("sector_reversal_1d",       -1, group="momentum",     default_weight=-0.12, desc="昨日涨幅极端→今日反转"),
    SectorFactorDef("sector_momentum_5d",        +1, group="momentum",     default_weight=0.10,  desc="5日板块涨幅动量"),
    SectorFactorDef("sector_momentum_20d",       +1, group="momentum",     default_weight=0.08,  desc="20日板块动量"),
    SectorFactorDef("sector_volume_surge",       +1, group="liquidity",    default_weight=0.06,  desc="成交量/20日均量比值"),
    SectorFactorDef("sector_turnover_zscore",    -1, group="liquidity",    default_weight=-0.05, desc="换手率Z-Score（过高→回落）"),
    SectorFactorDef("main_force_flow_ratio",     +1, group="capital_flow", default_weight=0.15,  desc="当日主力净流入占比"),
    SectorFactorDef("main_force_flow_5d_avg",    +1, group="capital_flow", default_weight=0.15,  desc="5日主力净流入均值"),
    SectorFactorDef("main_force_flow_trend",     +1, group="capital_flow", default_weight=0.12,  desc="连续净流入天数(+N/-N)"),
    SectorFactorDef("super_large_flow_ratio",    +1, group="capital_flow", default_weight=0.10,  desc="超大单净流入占比"),
    SectorFactorDef("sector_ma_dev_10",          -1, group="technical",    default_weight=-0.07, desc="10日均线偏离度"),
]


@dataclass
class SectorPredictionResult:
    predictions: dict[str, float] = field(default_factory=dict)        # { board_code: probability }
    factor_details: dict[str, dict[str, float]] = field(default_factory=dict)
    signals: dict[str, str] = field(default_factory=dict)              # { board_code: 'bullish'/'bearish'/'neutral' }
    computation_time_ms: float = 0


class SectorPredictor:
    """板块级多因子预测器"""

    def __init__(self, factor_defs: list[SectorFactorDef] | None = None):
        self.factor_defs = factor_defs or SECTOR_FACTOR_DEFS

    def predict(
        self,
        board_daily_df: pd.DataFrame,
        fund_flow_df: pd.DataFrame,
    ) -> SectorPredictionResult:
        """
        执行板块预测

        参数:
            board_daily_df: sector.board_daily 数据，需含多日历史
            fund_flow_df: sector.fund_flow_daily 数据，需含多日历史

        返回:
            SectorPredictionResult
        """
        t0 = time.monotonic()

        if board_daily_df.empty:
            logger.warning("SectorPredictor: 无板块行情数据，跳过预测")
            return SectorPredictionResult()

        # 1. 计算因子矩阵
        factor_matrix = self._compute_factors(board_daily_df, fund_flow_df)
        if factor_matrix.empty:
            return SectorPredictionResult()

        # 2. MAD 去极值 + Z-Score 标准化
        for col in factor_matrix.columns:
            if col == "board_code":
                continue
            factor_matrix[col] = self._mad_winsorize(factor_matrix[col])
            factor_matrix[col] = self._zscore(factor_matrix[col])

        # 3. 施密特正交化（同组因子）
        factor_matrix = self._orthogonalize(factor_matrix)

        # 4. 应用因子方向
        for fdef in self.factor_defs:
            if fdef.name in factor_matrix.columns:
                factor_matrix[fdef.name] *= fdef.direction

        # 5. 加权合成
        weights = {f.name: f.default_weight for f in self.factor_defs}
        factor_cols = [f.name for f in self.factor_defs if f.name in factor_matrix.columns]
        weight_arr = np.array([weights[c] for c in factor_cols])
        vals = factor_matrix[factor_cols].values
        composite = vals @ weight_arr

        # 6. 归一化 composite → 正态 CDF → 概率
        if np.std(composite) > 0:
            composite = (composite - np.mean(composite)) / np.std(composite)
        probabilities = stats.norm.cdf(composite)
        # 收缩到 [0.12, 0.88]
        probabilities = 0.12 + probabilities * 0.76

        # 7. 组装结果
        predictions = {}
        signals = {}
        factor_details = {}
        codes = factor_matrix["board_code"].tolist()

        for i, code in enumerate(codes):
            prob = float(probabilities[i])
            predictions[code] = prob
            if prob > 0.6:
                signals[code] = "bullish"
            elif prob < 0.4:
                signals[code] = "bearish"
            else:
                signals[code] = "neutral"
            factor_details[code] = {
                col: float(factor_matrix.iloc[i][col])
                for col in factor_cols
                if col in factor_matrix.columns
            }

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            f"⏱️ SectorPredictor.predict 耗时 {elapsed:.0f}ms, "
            f"{len(predictions)} 个板块"
        )

        return SectorPredictionResult(
            predictions=predictions,
            factor_details=factor_details,
            signals=signals,
            computation_time_ms=elapsed,
        )

    def _compute_factors(
        self, board_df: pd.DataFrame, flow_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """从原始数据计算 10 个因子"""
        if "board_code" not in board_df.columns:
            return pd.DataFrame()

        results = []
        for code, group in board_df.groupby("board_code"):
            group = group.sort_values("date")
            if len(group) < 2:
                continue

            row: dict = {"board_code": code}
            latest = group.iloc[-1]

            # 1. sector_reversal_1d — 昨日涨跌幅
            row["sector_reversal_1d"] = float(latest.get("pct_chg", 0) or 0)

            # 2. sector_momentum_5d — 5日累计涨幅
            if len(group) >= 5:
                row["sector_momentum_5d"] = float(group["pct_chg"].tail(5).sum())
            else:
                row["sector_momentum_5d"] = float(group["pct_chg"].sum())

            # 3. sector_momentum_20d — 20日累计涨幅
            if len(group) >= 20:
                row["sector_momentum_20d"] = float(group["pct_chg"].tail(20).sum())
            else:
                row["sector_momentum_20d"] = float(group["pct_chg"].sum())

            # 4. sector_volume_surge — 成交量 / 20日均量
            if "volume" in group.columns and len(group) >= 20:
                avg_vol = group["volume"].tail(20).mean()
                cur_vol = float(latest.get("volume", 0) or 0)
                row["sector_volume_surge"] = cur_vol / avg_vol if avg_vol > 0 else 1.0
            else:
                row["sector_volume_surge"] = 1.0

            # 5. sector_turnover_zscore
            if "turnover_rate" in group.columns and len(group) >= 20:
                tr = group["turnover_rate"].tail(20)
                mean_tr = tr.mean()
                std_tr = tr.std()
                cur_tr = float(latest.get("turnover_rate", 0) or 0)
                row["sector_turnover_zscore"] = (cur_tr - mean_tr) / std_tr if std_tr > 0 else 0.0
            else:
                row["sector_turnover_zscore"] = 0.0

            # 10. sector_ma_dev_10 — 10日均线偏离
            if "close" in group.columns and len(group) >= 10:
                ma10 = group["close"].tail(10).mean()
                cur_close = float(latest.get("close", 0) or 0)
                row["sector_ma_dev_10"] = (cur_close - ma10) / ma10 * 100 if ma10 > 0 else 0.0
            else:
                row["sector_ma_dev_10"] = 0.0

            # 资金流因子（需从 flow_df 取）
            if not flow_df.empty and "board_code" in flow_df.columns:
                code_flow = flow_df[flow_df["board_code"] == code].sort_values("date")
                if not code_flow.empty:
                    fl = code_flow.iloc[-1]
                    # 6. main_force_flow_ratio
                    row["main_force_flow_ratio"] = float(fl.get("main_force_net_ratio", 0) or 0)
                    # 9. super_large_flow_ratio
                    ratio = fl.get("super_large_net_inflow", 0) or 0
                    total = fl.get("main_force_net_inflow", 0) or 0
                    row["super_large_flow_ratio"] = float(ratio) / abs(float(total)) if total else 0.0

                    # 7. main_force_flow_5d_avg — 5日主力净流入均值
                    if len(code_flow) >= 5:
                        row["main_force_flow_5d_avg"] = float(
                            code_flow["main_force_net_inflow"].tail(5).mean()
                        )
                    else:
                        row["main_force_flow_5d_avg"] = float(
                            code_flow["main_force_net_inflow"].mean()
                        )

                    # 8. main_force_flow_trend — 连续流入天数
                    flows = code_flow["main_force_net_inflow"].tolist()
                    trend = 0
                    for v in reversed(flows):
                        if v > 0:
                            if trend >= 0:
                                trend += 1
                            else:
                                break
                        elif v < 0:
                            if trend <= 0:
                                trend -= 1
                            else:
                                break
                        else:
                            break
                    row["main_force_flow_trend"] = float(trend)
                else:
                    for k in ["main_force_flow_ratio", "main_force_flow_5d_avg",
                              "main_force_flow_trend", "super_large_flow_ratio"]:
                        row[k] = 0.0
            else:
                for k in ["main_force_flow_ratio", "main_force_flow_5d_avg",
                          "main_force_flow_trend", "super_large_flow_ratio"]:
                    row[k] = 0.0

            results.append(row)

        return pd.DataFrame(results) if results else pd.DataFrame()

    @staticmethod
    def _mad_winsorize(series: pd.Series, n_mad: float = 5.0) -> pd.Series:
        """MAD 去极值"""
        median = series.median()
        mad = (series - median).abs().median()
        if mad == 0:
            return series
        upper = median + n_mad * mad
        lower = median - n_mad * mad
        return series.clip(lower, upper)

    @staticmethod
    def _zscore(series: pd.Series) -> pd.Series:
        """Z-Score 标准化"""
        std = series.std()
        if std == 0:
            return series * 0
        return (series - series.mean()) / std

    def _orthogonalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """施密特正交化（同组因子）"""
        groups: dict[str, list[str]] = {}
        for fdef in self.factor_defs:
            if fdef.name in df.columns:
                groups.setdefault(fdef.group, []).append(fdef.name)

        for group_name, cols in groups.items():
            if len(cols) < 2:
                continue
            for i in range(1, len(cols)):
                for j in range(i):
                    v_i = df[cols[i]].values
                    v_j = df[cols[j]].values
                    dot = np.dot(v_i, v_j)
                    norm = np.dot(v_j, v_j)
                    if norm > 0:
                        df[cols[i]] = v_i - (dot / norm) * v_j
        return df
```

**Step 2: 集成到 SectorEngine**

在 `engine.py` 的 `__init__` 中添加：
```python
from engine.sector.predictor import SectorPredictor
# 在 __init__ 中：
self._predictor = SectorPredictor()
```

在 `get_boards` 方法的末尾（return 之前），添加预测逻辑：
```python
        # 尝试加载预测信号（如果有足够历史数据）
        try:
            board_hist = self._data.store.get_sector_board_daily(board_type=board_type)
            flow_hist = self._data.store.get_sector_fund_flow(board_type=board_type)
            if not board_hist.empty and len(board_hist) > 20:
                pred = self._predictor.predict(board_hist, flow_hist)
                for item in items:
                    if item.board_code in pred.predictions:
                        item.prediction_score = pred.predictions[item.board_code]
                        item.prediction_signal = pred.signals.get(item.board_code, "neutral")
        except Exception as e:
            logger.warning(f"板块预测失败（不影响数据展示）: {e}")
```

类似地，在 `get_rotation` 中集成预测到每个 `RotationMatrixRow.prediction`。

**Step 3: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python -c "from engine.sector.predictor import SectorPredictor, SECTOR_FACTOR_DEFS; print(f'{len(SECTOR_FACTOR_DEFS)} factors'); p = SectorPredictor(); print('predictor OK')"`
Expected: `10 factors` + `predictor OK`

**Step 4: Commit**

```bash
git add backend/engine/sector/predictor.py backend/engine/sector/engine.py
git commit -m "feat(sector): implement SectorPredictor with 10 factors + MAD/ZScore/orthogonal pipeline"
```

---

## Chunk 4: 前端页面框架 + 排行列表 + 热力图

### Task 8: Zustand Store + API 类型定义

**Files:**
- Create: `frontend/stores/useSectorStore.ts`
- Create: `frontend/lib/sector-api.ts`

**Step 1: 创建 API 类型和请求函数**

`frontend/lib/sector-api.ts`:
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SectorBoardItem {
  board_code: string;
  board_name: string;
  board_type: string;
  close: number;
  pct_chg: number;
  volume: number;
  amount: number;
  turnover_rate: number;
  total_mv: number;
  rise_count: number;
  fall_count: number;
  leading_stock: string;
  leading_pct_chg: number;
  main_force_net_inflow: number | null;
  main_force_net_ratio: number | null;
  prediction_score: number | null;
  prediction_signal: string | null;
}

export interface SectorHistoryItem {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  pct_chg: number;
  volume: number;
  amount: number;
  turnover_rate: number;
}

export interface SectorFundFlowItem {
  date: string;
  board_code: string;
  board_name: string;
  main_force_net_inflow: number;
  main_force_net_ratio: number;
  super_large_net_inflow: number;
  large_net_inflow: number;
  medium_net_inflow: number;
  small_net_inflow: number;
}

export interface ConstituentItem {
  code: string;
  name: string;
  price: number;
  pct_chg: number;
  volume: number;
  amount: number;
  turnover_rate: number;
  pe_ttm: number | null;
  pb: number | null;
}

export interface HeatmapCell {
  board_code: string;
  board_name: string;
  pct_chg: number;
  main_force_net_inflow: number;
  main_force_net_ratio: number;
}

export interface RotationMatrixRow {
  board_code: string;
  board_name: string;
  daily_flows: number[];
  daily_dates: string[];
  trend_signal: string;
}

export interface SectorPredictionItem {
  board_code: string;
  board_name: string;
  probability: number;
  signal: string;
}

export async function fetchSectorBoards(type: string, date = "") {
  const params = new URLSearchParams({ type });
  if (date) params.set("date", date);
  const res = await fetch(`${API_BASE}/api/v1/sector/boards?${params}`);
  return res.json();
}

export async function fetchSectorHistory(boardCode: string, boardName: string, boardType = "industry", start = "", end = "") {
  const params = new URLSearchParams({ board_name: boardName, board_type: boardType });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const res = await fetch(`${API_BASE}/api/v1/sector/${boardCode}/history?${params}`);
  return res.json();
}

export async function fetchSectorConstituents(boardCode: string, boardName: string) {
  const params = new URLSearchParams({ board_name: boardName });
  const res = await fetch(`${API_BASE}/api/v1/sector/${boardCode}/constituents?${params}`);
  return res.json();
}

export async function fetchSectorHeatmap(type: string, date = "") {
  const params = new URLSearchParams({ type });
  if (date) params.set("date", date);
  const res = await fetch(`${API_BASE}/api/v1/sector/heatmap?${params}`);
  return res.json();
}

export async function fetchSectorRotation(days = 10, type = "industry") {
  const params = new URLSearchParams({ days: String(days), type });
  const res = await fetch(`${API_BASE}/api/v1/sector/rotation?${params}`);
  return res.json();
}

export async function triggerSectorFetch(type: string) {
  const res = await fetch(`${API_BASE}/api/v1/sector/fetch?type=${type}`, { method: "POST" });
  return res.json();
}
```

**Step 2: 创建 Zustand Store**

`frontend/stores/useSectorStore.ts`:
```typescript
import { create } from "zustand";
import {
  SectorBoardItem, HeatmapCell, RotationMatrixRow,
  SectorHistoryItem, SectorFundFlowItem, ConstituentItem,
  SectorPredictionItem,
  fetchSectorBoards, fetchSectorHeatmap, fetchSectorRotation,
  fetchSectorHistory, fetchSectorConstituents, triggerSectorFetch,
} from "@/lib/sector-api";

type SortField = "pct_chg" | "main_force_net_inflow" | "prediction_score";

interface SectorStore {
  // 状态
  boardType: "industry" | "concept";
  date: string;
  boards: SectorBoardItem[];
  heatmapCells: HeatmapCell[];
  rotationMatrix: RotationMatrixRow[];
  topBullish: SectorPredictionItem[];
  topBearish: SectorPredictionItem[];
  selectedBoard: SectorBoardItem | null;
  history: SectorHistoryItem[];
  fundFlowHistory: SectorFundFlowItem[];
  constituents: ConstituentItem[];
  sortField: SortField;
  sortDesc: boolean;
  loading: boolean;
  detailLoading: boolean;

  // 操作
  setBoardType: (type: "industry" | "concept") => void;
  setDate: (date: string) => void;
  setSortField: (field: SortField) => void;
  selectBoard: (board: SectorBoardItem | null) => void;
  loadBoards: () => Promise<void>;
  loadHeatmap: () => Promise<void>;
  loadRotation: (days?: number) => Promise<void>;
  loadDetail: (board: SectorBoardItem) => Promise<void>;
  fetchData: () => Promise<void>;
}

export const useSectorStore = create<SectorStore>((set, get) => ({
  boardType: "industry",
  date: "",
  boards: [],
  heatmapCells: [],
  rotationMatrix: [],
  topBullish: [],
  topBearish: [],
  selectedBoard: null,
  history: [],
  fundFlowHistory: [],
  constituents: [],
  sortField: "pct_chg",
  sortDesc: true,
  loading: false,
  detailLoading: false,

  setBoardType: (type) => {
    set({ boardType: type, selectedBoard: null, history: [], constituents: [] });
    get().loadBoards();
    get().loadHeatmap();
  },

  setDate: (date) => {
    set({ date });
    get().loadBoards();
  },

  setSortField: (field) => {
    const { sortField, sortDesc } = get();
    if (sortField === field) {
      set({ sortDesc: !sortDesc });
    } else {
      set({ sortField: field, sortDesc: true });
    }
  },

  selectBoard: (board) => {
    set({ selectedBoard: board });
    if (board) get().loadDetail(board);
  },

  loadBoards: async () => {
    const { boardType, date } = get();
    set({ loading: true });
    try {
      const data = await fetchSectorBoards(boardType, date);
      set({ boards: data.boards || [], loading: false });
    } catch (e) {
      console.error("加载板块列表失败", e);
      set({ loading: false });
    }
  },

  loadHeatmap: async () => {
    const { boardType, date } = get();
    try {
      const data = await fetchSectorHeatmap(boardType, date);
      set({ heatmapCells: data.cells || [] });
    } catch (e) {
      console.error("加载热力图失败", e);
    }
  },

  loadRotation: async (days = 10) => {
    const { boardType } = get();
    try {
      const data = await fetchSectorRotation(days, boardType);
      set({
        rotationMatrix: data.matrix || [],
        topBullish: data.top_bullish || [],
        topBearish: data.top_bearish || [],
      });
    } catch (e) {
      console.error("加载轮动预测失败", e);
    }
  },

  loadDetail: async (board) => {
    set({ detailLoading: true });
    try {
      const [histData, consData] = await Promise.all([
        fetchSectorHistory(board.board_code, board.board_name, board.board_type),
        fetchSectorConstituents(board.board_code, board.board_name),
      ]);
      set({
        history: histData.history || [],
        fundFlowHistory: histData.fund_flow_history || [],
        constituents: consData.constituents || [],
        detailLoading: false,
      });
    } catch (e) {
      console.error("加载板块详情失败", e);
      set({ detailLoading: false });
    }
  },

  fetchData: async () => {
    const { boardType } = get();
    set({ loading: true });
    try {
      await triggerSectorFetch(boardType);
      await get().loadBoards();
      await get().loadHeatmap();
    } catch (e) {
      console.error("数据采集失败", e);
      set({ loading: false });
    }
  },
}));
```

**Step 3: 验证**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/frontend && npx tsc --noEmit lib/sector-api.ts stores/useSectorStore.ts 2>&1 | head -20`
Expected: 无类型错误（或仅 path 相关配置 warning）

**Step 4: Commit**

```bash
git add frontend/lib/sector-api.ts frontend/stores/useSectorStore.ts
git commit -m "feat(sector): add Zustand sector store + API client"
```

---

### Task 9: 前端页面 + 排行列表 + 热力图组件

**Files:**
- Create: `frontend/app/sector/page.tsx`
- Create: `frontend/components/sector/SectorDashboard.tsx`
- Create: `frontend/components/sector/SectorRankTable.tsx`
- Create: `frontend/components/sector/SectorHeatMap.tsx`
- Create: `frontend/components/sector/BoardTypeTab.tsx`

**注意**: 这些组件代码较长，实现时参考以下要点：

- `page.tsx`: 与 `expert/page.tsx` 同结构 — `"use client"` + `<NavSidebar />` + `<SectorDashboard />` + `marginLeft: 48`
- `SectorDashboard.tsx`: 容器组件，`useEffect` 触发 `loadBoards + loadHeatmap`，布局上下分区
- `BoardTypeTab.tsx`: 两个按钮 `[行业板块] [概念板块]`，active 状态高亮
- `SectorRankTable.tsx`: 表格组件，列：排名、板块名、涨跌幅、主力净流入、预测信号。表头可点击切换排序。涨跌幅红绿色标
- `SectorHeatMap.tsx`: CSS Grid 网格，每个格子显示板块名+涨跌幅，背景色按涨跌幅映射（红涨绿跌），透明度按资金流强度调节

完整代码在实现时编写，这里给出关键骨架。

**Step 5: Commit**

```bash
git add frontend/app/sector/ frontend/components/sector/
git commit -m "feat(sector): add sector page + rank table + heatmap components"
```

---

## Chunk 5: 前端详情面板 + 成分股 + 轮动面板

### Task 10: 详情面板 + 成分股 + 趋势图

**Files:**
- Create: `frontend/components/sector/SectorDetailPanel.tsx`
- Create: `frontend/components/sector/SectorTrendChart.tsx`
- Create: `frontend/components/sector/ConstituentTable.tsx`

**要点:**
- `SectorDetailPanel.tsx`: 展开/收起动画（framer-motion），左右分栏
- `SectorTrendChart.tsx`: 使用 `lightweight-charts` 渲染 K 线图，叠加资金流柱状图
- `ConstituentTable.tsx`: 成分股列表，列：代码、名称、现价、涨跌幅、成交额、换手率、PE、PB

**Step 3: Commit**

```bash
git add frontend/components/sector/
git commit -m "feat(sector): add detail panel + trend chart + constituent table"
```

---

### Task 11: 轮动预测面板

**Files:**
- Create: `frontend/components/sector/SectorRotationPanel.tsx`

**要点:**
- 热力矩阵：行=板块名，列=日期，格子颜色=资金流入强度（正=绿/负=红）
- 下方展示 Top5 看涨 / Top5 看跌 预测排名
- `useEffect` 触发 `loadRotation(10)`

**Step 2: Commit**

```bash
git add frontend/components/sector/SectorRotationPanel.tsx
git commit -m "feat(sector): add rotation prediction panel with heatmap matrix"
```

---

## Chunk 6: 联调 + 日期选择 + NavSidebar + 打磨

### Task 12: NavSidebar 新增板块研究导航 + 日期选择器

**Files:**
- Modify: `frontend/components/ui/NavSidebar.tsx:7-11` (NAV_ITEMS 数组)
- Create: `frontend/components/sector/DatePicker.tsx`

**Step 1: NavSidebar 添加第 4 个导航项**

在 `NavSidebar.tsx` 第 11 行 `{ href: "/expert", icon: BrainCircuit, label: "投资专家" },` 之后添加：
```typescript
  { href: "/sector", icon: TrendingUp, label: "板块研究" },
```

同时在 import 行（第 3 行）添加 `TrendingUp`：
```typescript
import { Mountain, Scale, BrainCircuit, TrendingUp } from "lucide-react";
```

**Step 2: DatePicker 组件**

简洁的日期输入组件，使用原生 `<input type="date">`，配合 TailwindCSS 样式。

**Step 3: Commit**

```bash
git add frontend/components/ui/NavSidebar.tsx frontend/components/sector/DatePicker.tsx
git commit -m "feat(sector): add sector nav item + date picker component"
```

---

### Task 13: 全栈联调 + 冒烟测试

**Step 1: 启动后端**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/backend && python main.py`

**Step 2: 测试 API**

Run: `curl http://localhost:8000/api/v1/sector/boards?type=industry | python -m json.tool | head -30`
Expected: JSON 格式的板块列表数据

Run: `curl -X POST http://localhost:8000/api/v1/sector/fetch?type=industry | python -m json.tool`
Expected: `{"board_type": "industry", "saved_boards": N, "saved_flows": M, "elapsed_s": X.X}`

**Step 3: 启动前端**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares/frontend && npm run dev`

**Step 4: 验证页面**

浏览器访问 `http://localhost:3000/sector`
- [ ] NavSidebar 显示"板块研究"导航项
- [ ] 行业板块/概念板块 Tab 可切换
- [ ] 排行列表显示板块数据，可排序
- [ ] 热力图显示网格色块
- [ ] 点击板块展开详情（趋势图 + 成分股）
- [ ] 日期选择器可切换日期
- [ ] 轮动预测面板展示热力矩阵

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat(sector): complete sector dashboard - full stack integration"
```

---

## Summary

| Chunk | Tasks | 核心交付 |
|-------|-------|---------|
| 1 | Task 1-3 | 数据引擎扩展（DuckDB表 + AKShare API + DataEngine） |
| 2 | Task 4-6 | SectorEngine 核心 + Schemas + Routes |
| 3 | Task 7 | SectorPredictor 10因子 + 轮动预测 |
| 4 | Task 8-9 | 前端 Store + 页面框架 + 排行列表 + 热力图 |
| 5 | Task 10-11 | 详情面板 + 成分股 + 轮动面板 |
| 6 | Task 12-13 | NavSidebar + 日期选择 + 联调 |

预计新增/修改文件 ~20 个，新增代码 ~2500 行。
