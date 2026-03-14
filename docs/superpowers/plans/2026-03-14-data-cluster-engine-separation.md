# 数据引擎/聚类引擎分离 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic `engine/` into two independent modules — `data_engine/` (data fetching, storage, profiles) and `cluster_engine/` (algorithm pipeline, clustering, prediction) — with clean interfaces and backward-compatible APIs.

**Architecture:** Same-process module separation with dependency injection. DataEngine is a facade over collector + store + profiles. ClusterEngine receives DataEngine via constructor, delegates data access through it. Both register their own FastAPI routers. Existing API paths unchanged.

**Tech Stack:** Python 3.11, FastAPI, DuckDB, Pydantic v2, HDBSCAN, UMAP

**Spec:** `docs/superpowers/specs/2026-03-14-data-cluster-engine-separation-design.md`

---

## File Structure

### New files to create

| File | Responsibility |
|------|---------------|
| `engine/data_engine/__init__.py` | Export `DataEngine`, `get_data_engine()` singleton |
| `engine/data_engine/engine.py` | DataEngine facade class |
| `engine/data_engine/precomputed.py` | Company profiles JSON loader |
| `engine/data_engine/routes.py` | `/api/v1/data/*` REST routes |
| `engine/data_engine/schemas.py` | Data engine Pydantic models |
| `engine/cluster_engine/__init__.py` | Export `ClusterEngine`, `get_cluster_engine()` singleton |
| `engine/cluster_engine/engine.py` | ClusterEngine facade class |
| `engine/cluster_engine/routes.py` | `/api/v1/terrain/*` and related routes (from terrain.py) |
| `engine/cluster_engine/schemas.py` | Cluster engine Pydantic models (from api/schemas.py) |

### Files to move (git mv)

| From | To |
|------|----|
| `engine/data/collector.py` | `engine/data_engine/collector.py` |
| `engine/data/sources/` | `engine/data_engine/sources/` |
| `engine/storage/duckdb_store.py` | `engine/data_engine/store.py` |
| `engine/algorithm/` | `engine/cluster_engine/algorithm/` |
| `engine/preprocess/` | `engine/cluster_engine/preprocess/` |

### Files to modify in place

| File | Change |
|------|--------|
| `engine/main.py` | New router imports, startup hook rewiring |
| `engine/mcpserver/tools.py` | Import paths for predictor_v2, factor_backtest, profiles |
| `engine/api/routes/chat.py` | Import path for schemas |
| `engine/api/schemas.py` | Reduce to LLM-only schemas |
| `engine/config.py` | No change needed (already standalone) |

### Files to delete after migration

| File | Reason |
|------|--------|
| `engine/data/__init__.py` | Replaced by data_engine |
| `engine/data/collector.py` | Moved |
| `engine/data/sources/*` | Moved |
| `engine/storage/__init__.py` | Replaced by data_engine |
| `engine/storage/duckdb_store.py` | Moved |
| `engine/algorithm/*` | Moved to cluster_engine/algorithm |
| `engine/preprocess/*` | Moved to cluster_engine/preprocess |
| `engine/api/routes/__init__.py` | No longer needed |
| `engine/api/routes/terrain.py` | Split into two routes.py files |

---

## Chunk 1: Data Engine Module

### Task 1: Create data_engine directory and move source files

**Files:**
- Create: `engine/data_engine/__init__.py`
- Create: `engine/data_engine/sources/__init__.py`
- Move: `engine/data/sources/base.py` → `engine/data_engine/sources/base.py`
- Move: `engine/data/sources/tencent_source.py` → `engine/data_engine/sources/tencent_source.py`
- Move: `engine/data/sources/akshare_source.py` → `engine/data_engine/sources/akshare_source.py`
- Move: `engine/data/sources/baostock_source.py` → `engine/data_engine/sources/baostock_source.py`
- Move: `engine/data/collector.py` → `engine/data_engine/collector.py`
- Move: `engine/storage/duckdb_store.py` → `engine/data_engine/store.py`

- [ ] **Step 1: Create data_engine directories**

```bash
mkdir -p engine/data_engine/sources
```

- [ ] **Step 2: Move source files with git mv**

```bash
git mv engine/data/sources/base.py engine/data_engine/sources/base.py
git mv engine/data/sources/tencent_source.py engine/data_engine/sources/tencent_source.py
git mv engine/data/sources/akshare_source.py engine/data_engine/sources/akshare_source.py
git mv engine/data/sources/baostock_source.py engine/data_engine/sources/baostock_source.py
git mv engine/data/sources/__init__.py engine/data_engine/sources/__init__.py
git mv engine/data/collector.py engine/data_engine/collector.py
git mv engine/storage/duckdb_store.py engine/data_engine/store.py
```

- [ ] **Step 3: Fix internal imports in collector.py**

`engine/data_engine/collector.py` — change relative imports to new paths:

```python
# Before:
from .sources.base import BaseDataSource
from .sources.tencent_source import TencentSource
from .sources.akshare_source import AKShareSource
from .sources.baostock_source import BaoStockSource
```

These relative imports still work because `sources/` moved alongside `collector.py`. No change needed here.

- [ ] **Step 4: Create empty `__init__.py` files**

`engine/data_engine/__init__.py`:
```python
"""数据引擎模块 — 行情拉取、持久化、公司概况"""
```

- [ ] **Step 5: Verify Python imports work**

```bash
cd engine && python3 -c "from data_engine.collector import DataCollector; print('collector OK')"
cd engine && python3 -c "from data_engine.store import DuckDBStore; print('store OK')"
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor: 移动数据层文件到 data_engine/"
```

### Task 2: Create precomputed.py — 公司概况加载器

**Files:**
- Create: `engine/data_engine/precomputed.py`

This extracts the profiles-loading logic from `engine/algorithm/features.py:PrecomputedData._load()` (lines 74-107, profiles portion only).

- [ ] **Step 1: Write precomputed.py**

```python
"""
公司概况加载器

从 data/precomputed/company_profiles.json 加载公司基础信息。
兼容 v2.0 的 industry_mapping.json 格式。
"""

import json
from pathlib import Path
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "data" / "precomputed"


def load_profiles() -> dict[str, dict]:
    """
    加载公司概况 {code: {name, industry, scope, ...}}

    优先加载 company_profiles.json，兼容 v2.0 的 industry_mapping.json。
    """
    profiles: dict[str, dict] = {}
    profiles_path = PRECOMPUTED_DIR / "company_profiles.json"

    if profiles_path.exists():
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                profiles = json.load(f)
            logger.info(f"📋 公司概况加载: {len(profiles)} 只股票")
            return profiles
        except Exception as e:
            logger.warning(f"公司概况加载失败: {e}")

    # 兼容 v2.0 的 industry_mapping.json
    industry_path = PRECOMPUTED_DIR / "industry_mapping.json"
    if industry_path.exists():
        try:
            with open(industry_path, "r", encoding="utf-8") as f:
                industry_mapping = json.load(f)
            for code, info in industry_mapping.items():
                profiles[code] = {
                    "code": code,
                    "industry": info.get("industry_name", ""),
                }
            logger.info(f"📋 兼容 v2.0 行业映射: {len(profiles)} 只")
        except Exception:
            pass

    return profiles
```

- [ ] **Step 2: Verify it loads**

```bash
cd engine && python3 -c "from data_engine.precomputed import load_profiles; p = load_profiles(); print(f'{len(p)} profiles loaded')"
```

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/precomputed.py && git commit -m "feat: data_engine/precomputed.py 公司概况加载器"
```

### Task 3: Create DataEngine facade

**Files:**
- Create: `engine/data_engine/engine.py`
- Modify: `engine/data_engine/__init__.py`

- [ ] **Step 1: Write engine.py**

```python
"""
DataEngine — 数据引擎门面类

统一管理行情拉取、DuckDB 持久化、公司概况查询。
对外提供单一接口，内部编排 collector + store + precomputed。
"""

import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from .collector import DataCollector
from .store import DuckDBStore
from .precomputed import load_profiles


class DataEngine:
    """数据引擎 — 原始数据的获取、持久化、查询门面"""

    def __init__(self):
        self._collector = DataCollector()
        self._store = DuckDBStore()
        self._profiles = load_profiles()

    @property
    def store(self) -> DuckDBStore:
        """暴露 store 给需要直接访问的模块（如聚类引擎存储聚类结果）"""
        return self._store

    @property
    def collector(self) -> DataCollector:
        """暴露 collector 给需要直接访问的模块"""
        return self._collector

    @property
    def available_sources(self) -> list[str]:
        return self._collector.available_sources

    # ── 行情数据 ──

    def get_realtime_quotes(self) -> pd.DataFrame:
        """拉取全市场实时行情（网络请求）"""
        return self._collector.get_realtime_quotes()

    def get_snapshot(self) -> pd.DataFrame:
        """获取 DuckDB 中最新快照（本地查询）"""
        return self._store.get_snapshot()

    def save_snapshot(self, df: pd.DataFrame):
        """保存行情快照到 DuckDB"""
        self._store.save_snapshot(df)

    # ── 日线历史 ──

    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        """获取个股日线，优先本地 DuckDB，缺失则通过 collector 拉取"""
        df = self._store.get_daily(code, start, end)
        if df is not None and len(df) > 0:
            return df
        # 本地无数据，尝试网络拉取
        df = self._collector.get_daily_history(code, start, end)
        if df is not None and len(df) > 0:
            self._store.save_daily(df)
        return df if df is not None else pd.DataFrame()

    def get_daily_history_batch(
        self, snapshot: pd.DataFrame, min_days: int = 20
    ) -> dict[str, pd.DataFrame]:
        """
        批量获取日线历史（从本地 DuckDB 缓存）
        纯本地查询，不触发网络请求。
        """
        if snapshot.empty or "code" not in snapshot.columns:
            return {}

        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")

        codes = snapshot["code"].astype(str).tolist()
        daily_map: dict[str, pd.DataFrame] = {}
        matched = 0

        for code in codes:
            try:
                df = self._store.get_daily(code, start_date, end_date)
                if df is not None and len(df) >= min_days:
                    daily_map[code] = df
                    matched += 1
            except Exception:
                continue

        logger.info(f"📈 日线历史读取: {matched}/{len(codes)} 只股票有 ≥{min_days} 日数据")
        return daily_map

    def get_market_history_streaming(
        self,
        codes: list[str],
        days: int = 7,
        on_progress: Optional["callable"] = None,
        on_batch_done: Optional["callable"] = None,
    ) -> dict[str, pd.DataFrame]:
        """流式批量拉取全市场历史日线（网络请求，带进度回调）"""
        return self._collector.get_market_history_streaming(
            codes, days, on_progress, on_batch_done
        )

    # ── 财务数据 ──

    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """获取季频财务数据（逐级降级）"""
        return self._collector.get_financial_data(code, year, quarter)

    # ── 快照历史（回放用）──

    def get_snapshot_daily_dates(self) -> list[str]:
        return self._store.get_snapshot_daily_dates()

    def get_snapshot_daily_range(self, days: int = 7) -> dict[str, pd.DataFrame]:
        return self._store.get_snapshot_daily_range(days)

    def save_history_as_snapshots(self, history_by_date: dict):
        self._store.save_history_as_snapshots(history_by_date)

    # ── 公司基础信息 ──

    def get_profiles(self) -> dict[str, dict]:
        """获取全量公司概况"""
        return self._profiles

    def get_profile(self, code: str) -> dict | None:
        """获取单只股票概况"""
        return self._profiles.get(code)

    # ── 元信息 ──

    def get_stock_count(self) -> int:
        return self._store.get_stock_count()

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "data_sources": {s: True for s in self.available_sources},
            "stock_count": self.get_stock_count(),
            "profiles_count": len(self._profiles),
        }
```

- [ ] **Step 2: Update `__init__.py` with singleton**

```python
"""数据引擎模块 — 行情拉取、持久化、公司概况"""

from .engine import DataEngine

_data_engine: DataEngine | None = None


def get_data_engine() -> DataEngine:
    """获取数据引擎全局单例"""
    global _data_engine
    if _data_engine is None:
        _data_engine = DataEngine()
    return _data_engine


__all__ = ["DataEngine", "get_data_engine"]
```

- [ ] **Step 3: Verify DataEngine initializes**

```bash
cd engine && python3 -c "from data_engine import get_data_engine; de = get_data_engine(); print(de.health_check())"
```

- [ ] **Step 4: Commit**

```bash
git add engine/data_engine/ && git commit -m "feat: DataEngine 门面类 + 单例管理"
```

### Task 4: Create data_engine schemas and routes

**Files:**
- Create: `engine/data_engine/schemas.py`
- Create: `engine/data_engine/routes.py`

- [ ] **Step 1: Write schemas.py**

```python
"""数据引擎 Pydantic 响应模型"""

from pydantic import BaseModel, Field


class DataHealthResponse(BaseModel):
    status: str = "ok"
    data_sources: dict[str, bool] = Field(default_factory=dict)
    stock_count: int = 0
    profiles_count: int = 0


class ProfileResponse(BaseModel):
    code: str
    name: str = ""
    industry: str = ""
    scope: str = ""


class SnapshotStockResponse(BaseModel):
    code: str
    name: str = ""
    price: float = 0.0
    pct_chg: float = 0.0
    volume: int = 0
    amount: float = 0.0
    turnover_rate: float = 0.0
    pe_ttm: float = 0.0
    pb: float = 0.0
```

- [ ] **Step 2: Write routes.py**

```python
"""
数据引擎 REST API — /api/v1/data/*

提供行情快照、公司概况、日线历史等数据查询接口。
"""

import asyncio

from fastapi import APIRouter, Query, HTTPException
from loguru import logger

from . import get_data_engine

router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.get("/health")
async def data_health():
    """数据引擎健康检查"""
    de = get_data_engine()
    return de.health_check()


@router.get("/snapshot")
async def get_snapshot(
    limit: int = Query(50, description="返回条数限制"),
    offset: int = Query(0, description="偏移量"),
):
    """获取最新行情快照"""
    de = get_data_engine()
    df = await asyncio.to_thread(de.get_snapshot)
    if df.empty:
        return {"stocks": [], "total": 0}

    total = len(df)
    df = df.iloc[offset:offset + limit]
    stocks = df.to_dict(orient="records")
    return {"stocks": stocks, "total": total}


@router.get("/snapshot/dates")
async def get_snapshot_dates():
    """获取历史快照日期列表"""
    de = get_data_engine()
    dates = de.get_snapshot_daily_dates()
    return {"dates": dates, "count": len(dates)}


@router.get("/snapshot/history")
async def get_snapshot_history(
    days: int = Query(7, description="回溯天数"),
):
    """获取指定日期范围的历史快照"""
    de = get_data_engine()
    snapshots = await asyncio.to_thread(de.get_snapshot_daily_range, days)
    result = {}
    for date_str, df in snapshots.items():
        result[date_str] = {
            "count": len(df),
            "stocks": df.to_dict(orient="records"),
        }
    return {"days": len(result), "snapshots": result}


@router.get("/daily/{code}")
async def get_daily(
    code: str,
    days: int = Query(60, description="回溯天数"),
):
    """获取个股日线历史"""
    import datetime
    de = get_data_engine()
    end = datetime.date.today().strftime("%Y-%m-%d")
    start = (datetime.date.today() - datetime.timedelta(days=days + 10)).strftime("%Y-%m-%d")
    df = await asyncio.to_thread(de.get_daily_history, code, start, end)
    if df.empty:
        return {"code": code, "records": [], "count": 0}
    return {
        "code": code,
        "records": df.to_dict(orient="records"),
        "count": len(df),
    }


@router.get("/profiles")
async def get_profiles(
    q: str = Query("", description="搜索关键词（代码/名称/行业）"),
    limit: int = Query(50, description="返回条数限制"),
):
    """获取公司概况列表"""
    de = get_data_engine()
    profiles = de.get_profiles()

    if q:
        q_lower = q.lower()
        filtered = {
            code: p for code, p in profiles.items()
            if q_lower in code.lower()
            or q_lower in p.get("name", "").lower()
            or q_lower in p.get("industry", "").lower()
        }
    else:
        filtered = profiles

    items = list(filtered.values())[:limit]
    return {"profiles": items, "total": len(filtered)}


@router.get("/profiles/{code}")
async def get_profile(code: str):
    """获取单只公司概况"""
    de = get_data_engine()
    profile = de.get_profile(code)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"未找到股票: {code}")
    return profile


@router.post("/fetch/realtime")
async def fetch_realtime():
    """触发实时行情拉取并保存"""
    de = get_data_engine()
    try:
        snapshot = await asyncio.to_thread(de.get_realtime_quotes)
        await asyncio.to_thread(de.save_snapshot, snapshot)
        return {"status": "ok", "stock_count": len(snapshot)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"行情拉取失败: {str(e)}")
```

- [ ] **Step 3: Verify route module loads**

```bash
cd engine && python3 -c "from data_engine.routes import router; print(f'data routes: {len(router.routes)} endpoints')"
```

- [ ] **Step 4: Commit**

```bash
git add engine/data_engine/schemas.py engine/data_engine/routes.py && git commit -m "feat: data_engine REST API 路由和 schemas"
```

---

## Chunk 2: Cluster Engine Module

### Task 5: Move algorithm and preprocess into cluster_engine

**Files:**
- Create: `engine/cluster_engine/__init__.py`
- Create: `engine/cluster_engine/algorithm/__init__.py`
- Create: `engine/cluster_engine/preprocess/__init__.py`
- Move: all `engine/algorithm/*.py` → `engine/cluster_engine/algorithm/`
- Move: all `engine/preprocess/*.py` → `engine/cluster_engine/preprocess/`

- [ ] **Step 1: Create cluster_engine directories**

```bash
mkdir -p engine/cluster_engine/algorithm
mkdir -p engine/cluster_engine/preprocess
```

- [ ] **Step 2: Move algorithm files with git mv**

```bash
git mv engine/algorithm/__init__.py engine/cluster_engine/algorithm/__init__.py
git mv engine/algorithm/clustering.py engine/cluster_engine/algorithm/clustering.py
git mv engine/algorithm/features.py engine/cluster_engine/algorithm/features.py
git mv engine/algorithm/interpolation.py engine/cluster_engine/algorithm/interpolation.py
git mv engine/algorithm/pipeline.py engine/cluster_engine/algorithm/pipeline.py
git mv engine/algorithm/projection.py engine/cluster_engine/algorithm/projection.py
git mv engine/algorithm/predictor.py engine/cluster_engine/algorithm/predictor.py
git mv engine/algorithm/predictor_v2.py engine/cluster_engine/algorithm/predictor_v2.py
git mv engine/algorithm/factor_backtest.py engine/cluster_engine/algorithm/factor_backtest.py
```

- [ ] **Step 3: Move preprocess files with git mv**

```bash
git mv engine/preprocess/__init__.py engine/cluster_engine/preprocess/__init__.py
git mv engine/preprocess/rebuild_bge.py engine/cluster_engine/preprocess/rebuild_bge.py
git mv engine/preprocess/build_embeddings.py engine/cluster_engine/preprocess/build_embeddings.py
git mv engine/preprocess/export_snapshot.py engine/cluster_engine/preprocess/export_snapshot.py
```

- [ ] **Step 4: Create cluster_engine/__init__.py**

```python
"""聚类引擎模块 — 特征提取、聚类、降维、插值、预测"""
```

- [ ] **Step 5: Verify algorithm module can be found**

`pipeline.py` uses relative imports (`from .features import ...`) which still work inside `cluster_engine/algorithm/`. Verify the module is importable:

```bash
cd engine && python3 -c "from cluster_engine.algorithm.clustering import ClusterEngine; print('clustering OK')"
cd engine && python3 -c "from cluster_engine.algorithm.features import FeatureEngineer; print('features OK')"
```

Note: `AlgorithmPipeline` import may fail at this point because `features.py:PrecomputedData` still loads profiles internally — that's fixed in Task 6. Only verify the individual sub-modules here.

- [ ] **Step 6: Commit the moves**

```bash
git add -A && git commit -m "refactor: 移动算法和预处理文件到 cluster_engine/"
```

### Task 6: Modify FeatureEngineer to accept injected profiles

**Files:**
- Modify: `engine/cluster_engine/algorithm/features.py`

The key change: `PrecomputedData` no longer loads profiles from JSON. Instead, `FeatureEngineer` accepts a `profiles` parameter. `PrecomputedData` only loads embeddings.

- [ ] **Step 1: Fix PRECOMPUTED_DIR path depth and modify PrecomputedData**

**Critical:** After moving from `engine/algorithm/features.py` to `engine/cluster_engine/algorithm/features.py`, the `PROJECT_ROOT` path is one level deeper. Fix:

```python
# Before (at engine/algorithm/features.py):
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# After (at engine/cluster_engine/algorithm/features.py):
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```

Then in `engine/cluster_engine/algorithm/features.py`, change `PrecomputedData.__init__` and `_load`:

```python
class PrecomputedData:
    """预计算数据加载器 v4.0 — 仅加载嵌入向量"""

    def __init__(self):
        self.available = False
        self.profiles: dict = {}        # 由外部注入，不再自行加载
        self.embedding_codes: np.ndarray | None = None
        self.embeddings: np.ndarray | None = None
        self.embedding_dim: int = 0
        self._load_embeddings()

    def _load_embeddings(self):
        """加载 BGE 嵌入向量（不加载公司概况）"""
        embedding_path = PRECOMPUTED_DIR / "stock_embeddings.npz"

        if embedding_path.exists():
            try:
                data = np.load(embedding_path, allow_pickle=True)
                self.embedding_codes = data["codes"]
                self.embeddings = data["embeddings"]
                self.embedding_dim = self.embeddings.shape[1]
                model_name = (
                    str(data["model_name"])
                    if "model_name" in data
                    else "unknown"
                )
                logger.info(
                    f"🧠 嵌入加载: {self.embeddings.shape} "
                    f"(模型: {model_name})"
                )
            except Exception as e:
                logger.warning(f"嵌入加载失败: {e}")

        if self.embeddings is not None and len(self.embeddings) > 0:
            self.available = True
            logger.info("✅ 嵌入向量加载完成 — 语义嵌入融合模式")
        else:
            logger.warning(
                "⚠️ 嵌入文件不存在，使用纯数值特征模式。"
                "运行 python -m cluster_engine.preprocess.rebuild_bge 生成数据。"
            )

    def set_profiles(self, profiles: dict):
        """注入公司概况（由 DataEngine 提供）"""
        self.profiles = profiles
        logger.info(f"📋 公司概况已注入: {len(profiles)} 只股票")
```

- [ ] **Step 2: Modify FeatureEngineer constructor**

```python
class FeatureEngineer:
    """特征工程引擎 v4.0 — 语义嵌入 + 数值特征融合"""

    def __init__(self, profiles: dict | None = None):
        self._scaler = StandardScaler()
        self._pca = None
        self._fitted = False
        self._precomputed = PrecomputedData()
        self._cluster_centers_embedding: dict[int, np.ndarray] | None = None

        # 注入公司概况
        if profiles is not None:
            self._precomputed.set_profiles(profiles)
```

- [ ] **Step 3: Verify modified FeatureEngineer loads**

```bash
cd engine && python3 -c "
from cluster_engine.algorithm.features import FeatureEngineer
fe = FeatureEngineer(profiles={'600519': {'name': '贵州茅台', 'industry': '白酒'}})
print(f'profiles: {len(fe.precomputed.profiles)}')
print(f'embeddings available: {fe.precomputed.available}')
"
```

- [ ] **Step 4: Commit**

```bash
git add engine/cluster_engine/algorithm/features.py && git commit -m "refactor: FeatureEngineer 接受外部注入的公司概况"
```

### Task 7: Modify AlgorithmPipeline to accept DataEngine

**Files:**
- Modify: `engine/cluster_engine/algorithm/pipeline.py`

- [ ] **Step 1: Change AlgorithmPipeline constructor**

Replace the `__init__` method (lines 74-90):

```python
class AlgorithmPipeline:
    """
    算法总编排器 v3.0

    流水线：
    snapshot → 特征提取 → HDBSCAN聚类 → UMAP降维 → 高斯核密度插值(多指标) → TerrainResult
    """

    def __init__(self, profiles: dict | None = None):
        self.feature_eng = FeatureEngineer(profiles=profiles)
        self.cluster_eng = ClusterEngine()
        self.projection_eng = ProjectionEngine()
        self.interpolation_eng = InterpolationEngine()
        self.predictor = StockPredictor()         # v1 fallback
        self.predictor_v2 = StockPredictorV2()    # v2 量化增强

        # 缓存
        self._last_result: TerrainResult | None = None
        self._last_meta_df: pd.DataFrame | None = None
        self._last_embedding: np.ndarray | None = None
        self._last_snapshot: pd.DataFrame | None = None
        self._last_X_features: np.ndarray | None = None
        self._last_params: dict | None = None
        self._last_codes_set: set[str] | None = None
```

Note: Pipeline takes `profiles` directly (not `DataEngine`) to avoid importing data_engine from within cluster_engine.algorithm. This keeps the algorithm layer decoupled — the algorithm module has no dependency on data_engine. This is a deliberate deviation from the spec which shows `AlgorithmPipeline(data_engine)`. Trade-off: if profiles change at runtime, the pipeline holds stale data. Acceptable because profiles are static precomputed data that don't change during a session.

- [ ] **Step 2: Verify pipeline still loads**

```bash
cd engine && python3 -c "from cluster_engine.algorithm.pipeline import AlgorithmPipeline; p = AlgorithmPipeline(); print('pipeline OK')"
```

- [ ] **Step 3: Commit**

```bash
git add engine/cluster_engine/algorithm/pipeline.py && git commit -m "refactor: AlgorithmPipeline 接受 profiles 参数注入"
```

### Task 8: Create ClusterEngine facade

**Files:**
- Create: `engine/cluster_engine/engine.py`
- Modify: `engine/cluster_engine/__init__.py`

- [ ] **Step 1: Write engine.py**

```python
"""
ClusterEngine — 聚类引擎门面类

依赖 DataEngine 获取原始数据，编排算法流水线。
"""

import numpy as np
import pandas as pd
from loguru import logger

from .algorithm.pipeline import AlgorithmPipeline, TerrainResult
from .algorithm.factor_backtest import run_ic_backtest_from_store


class ClusterEngine:
    """聚类引擎 — 算法消费者，从 DataEngine 获取数据"""

    def __init__(self, data_engine):
        """
        Args:
            data_engine: DataEngine 实例（通过依赖注入）
        """
        self._data = data_engine
        self._pipeline = AlgorithmPipeline(profiles=data_engine.get_profiles())

    @property
    def pipeline(self) -> AlgorithmPipeline:
        """暴露 pipeline 给路由层"""
        return self._pipeline

    @property
    def last_result(self) -> TerrainResult | None:
        return self._pipeline.last_result

    def search_stocks(self, query: str, limit: int = 20) -> list[dict]:
        """搜索股票（代码/名称模糊匹配）"""
        if not self._pipeline.last_result or not self._pipeline.last_result.stocks:
            return []

        q_lower = query.lower()
        results = []
        for s in self._pipeline.last_result.stocks:
            if q_lower in s["code"].lower() or q_lower in s["name"].lower():
                results.append(s)
            if len(results) >= limit:
                break
        return results

    def try_auto_inject_icir_weights(self):
        """启动时自动从历史数据计算 ICIR 权重并注入预测器"""
        try:
            dates = self._data.get_snapshot_daily_dates()
            if len(dates) >= 5:
                logger.info(f"🔄 检测到 {len(dates)} 天历史快照，自动运行 IC 回测...")
                result = run_ic_backtest_from_store(self._data.store, rolling_window=20)
                if result.icir_weights:
                    self._pipeline.predictor_v2.set_icir_weights(result.icir_weights)
                    logger.info("✅ 启动时 ICIR 权重自动注入成功")
                else:
                    logger.info("ℹ️ IC 回测无显著权重，使用默认权重")
            else:
                logger.info(
                    f"ℹ️ 历史快照仅 {len(dates)} 天（<5天），跳过 ICIR 自动校准。"
                    f"多次「生成3D地形」积累数据后将自动启用。"
                )
        except Exception as e:
            logger.warning(f"⚠️ 启动时 ICIR 自动校准跳过: {e}")
```

- [ ] **Step 2: Update `__init__.py` with singleton**

```python
"""聚类引擎模块 — 特征提取、聚类、降维、插值、预测"""

from .engine import ClusterEngine as ClusterEngineFacade

# 同时导出 ClusterEngine 名称，方便外部使用
ClusterEngine = ClusterEngineFacade

_cluster_engine: ClusterEngineFacade | None = None


def get_cluster_engine() -> ClusterEngineFacade:
    """获取聚类引擎全局单例（依赖数据引擎）"""
    global _cluster_engine
    if _cluster_engine is None:
        from data_engine import get_data_engine
        _cluster_engine = ClusterEngineFacade(get_data_engine())
    return _cluster_engine


__all__ = ["ClusterEngine", "ClusterEngineFacade", "get_cluster_engine"]
```

Note: Import as `ClusterEngineFacade` to avoid name collision with `cluster_engine.algorithm.clustering.ClusterEngine` (the HDBSCAN wrapper). Also re-export as `ClusterEngine` for external consumers who don't need to worry about the internal naming.

- [ ] **Step 3: Verify ClusterEngine initializes**

```bash
cd engine && python3 -c "from cluster_engine import get_cluster_engine; ce = get_cluster_engine(); print('cluster engine OK')"
```

- [ ] **Step 4: Commit**

```bash
git add engine/cluster_engine/ && git commit -m "feat: ClusterEngine 门面类 + 单例管理"
```

---

## Chunk 3: Routes Migration and Wiring

### Task 9: Create cluster_engine schemas (from api/schemas.py)

**Files:**
- Create: `engine/cluster_engine/schemas.py`
- Modify: `engine/api/schemas.py` (reduce to LLM-only)

- [ ] **Step 1: Copy relevant schemas to cluster_engine/schemas.py**

Copy all terrain/cluster related models from `engine/api/schemas.py` to `engine/cluster_engine/schemas.py`. This includes: `HealthResponse`, `ComputeRequest`, `TerrainResponse`, `ClusterInfo`, `StockPoint`, `ClusterAffinity`, `RelatedStock`, `SimilarStock`, `HistoryRequest`, `HistoryResponse`, `HistoryFrame`, `StockSearchResult`, and anything else terrain-related.

The file header:

```python
"""
聚类引擎 Pydantic 模型

从 api/schemas.py 迁移的地形/聚类相关模型。
"""
```

Copy the entire content of `api/schemas.py` excluding the Chat/LLM classes.

- [ ] **Step 2: Reduce api/schemas.py to LLM-only**

Keep only: `ChatRequest`, `ChatResponse`, `LLMConfigRequest`, `LLMConfigResponse` and their imports.

- [ ] **Step 3: Update chat.py imports**

`engine/api/routes/chat.py` imports from `api.schemas` — verify these are LLM schemas that stay in `api/schemas.py`. No change needed if chat only uses Chat/LLM models.

- [ ] **Step 4: Verify both schema modules import**

```bash
cd engine && python3 -c "from cluster_engine.schemas import TerrainResponse, ComputeRequest; print('cluster schemas OK')"
cd engine && python3 -c "from api.schemas import ChatRequest; print('api schemas OK')"
```

- [ ] **Step 5: Commit**

```bash
git add engine/cluster_engine/schemas.py engine/api/schemas.py && git commit -m "refactor: schemas.py 拆分为 cluster_engine 和 LLM 两部分"
```

### Task 10: Create cluster_engine/routes.py (from terrain.py)

**Files:**
- Create: `engine/cluster_engine/routes.py`

This is the largest task. Migrate all route handlers from `engine/api/routes/terrain.py` into `engine/cluster_engine/routes.py`, replacing direct `DataCollector`/`DuckDBStore` usage with `DataEngine` access via `get_data_engine()` and `get_cluster_engine()`.

- [ ] **Step 1: Write cluster_engine/routes.py**

Key changes from the original `terrain.py`:
- Replace `get_collector()` → `get_data_engine()`
- Replace `get_pipeline()` → `get_cluster_engine().pipeline`
- Replace `get_store()` → `get_data_engine().store`
- Replace `_get_daily_history_batch(store, snapshot)` → `get_data_engine().get_daily_history_batch(snapshot)`
- Replace `_try_auto_inject_icir_weights()` → `get_cluster_engine().try_auto_inject_icir_weights()`
- Import schemas from `cluster_engine.schemas` instead of `api.schemas`
- Keep the same route prefix `/api/v1`
- **Important:** `get_factor_weights()` 内有 `from algorithm.predictor_v2 import FACTOR_DEFS` 延迟导入，必须改为 `from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS`

The full file migrates: `health_check`, `compute_terrain`, `refresh_terrain`, `get_terrain_history`, `search_stocks`, `run_factor_backtest`, `get_factor_weights`, `websocket_terrain`, `broadcast_terrain_update`.

- [ ] **Step 2: Verify route module loads**

```bash
cd engine && python3 -c "from cluster_engine.routes import router; print(f'cluster routes: {len(router.routes)} endpoints')"
```

- [ ] **Step 3: Commit**

```bash
git add engine/cluster_engine/routes.py && git commit -m "feat: cluster_engine/routes.py 从 terrain.py 迁移"
```

### Task 11: Rewire main.py

**Files:**
- Modify: `engine/main.py`

- [ ] **Step 1: Update router imports and startup hook**

Replace:
```python
from api.routes.terrain import router as terrain_router
```

With:
```python
from data_engine.routes import router as data_router
from cluster_engine.routes import router as cluster_router
```

Replace:
```python
app.include_router(terrain_router)
```

With:
```python
app.include_router(data_router)
app.include_router(cluster_router)
```

Update startup hook:
```python
@app.on_event("startup")
async def startup():
    from llm.config import llm_settings
    logger.info("=" * 60)
    logger.info("🏔️  StockTerrain Engine 启动")
    logger.info(f"   数据源: AKShare(主力) + BaoStock(备选)")
    logger.info(f"   算法: HDBSCAN + UMAP + RBF")
    logger.info(f"   预测: v2.0 (MAD去极值 + 正交化 + ICIR自适应权重)")
    logger.info(f"   LLM: {'已配置 (' + llm_settings.provider + '/' + llm_settings.model + ')' if llm_settings.api_key else '未配置 (可在设置中启用)'}")
    logger.info(f"   端口: {settings.server.port}")
    logger.info(f"   API 文档: http://localhost:{settings.server.port}/docs")
    logger.info("=" * 60)

    try:
        from cluster_engine import get_cluster_engine
        get_cluster_engine().try_auto_inject_icir_weights()
    except Exception as e:
        logger.warning(f"⚠️ ICIR 自动校准跳过: {e}")
```

- [ ] **Step 2: Verify main.py loads**

```bash
cd engine && python3 -c "from main import app; print(f'routes registered: {len(app.routes)}')"
```

- [ ] **Step 3: Commit**

```bash
git add engine/main.py && git commit -m "refactor: main.py 切换到双引擎路由"
```

### Task 12: Fix MCP Server imports

**Files:**
- Modify: `engine/mcpserver/tools.py`

- [ ] **Step 1: Update import paths**

Three changes in `engine/mcpserver/tools.py`:

1. Line 542: `from algorithm.predictor_v2 import FACTOR_DEFS` → `from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS`

2. Line 858: `from algorithm.factor_backtest import FactorBacktester` → `from cluster_engine.algorithm.factor_backtest import FactorBacktester`

3. Lines 23-38: `PROFILES_PATH` and `_load_profiles()` — keep as-is for now (reads from filesystem which still works), or update to import from `data_engine.precomputed`:

```python
from data_engine.precomputed import load_profiles as _load_profiles_from_engine

_profiles: dict[str, dict] | None = None

def _load_profiles() -> dict[str, dict]:
    global _profiles
    if _profiles is not None:
        return _profiles
    _profiles = _load_profiles_from_engine()
    return _profiles
```

- [ ] **Step 2: Verify MCP tools module loads**

```bash
cd engine && python3 -c "from mcpserver.tools import query_market_overview; print('mcp tools OK')"
```

- [ ] **Step 3: Commit**

```bash
git add engine/mcpserver/tools.py && git commit -m "fix: MCP tools.py 导入路径迁移到新引擎模块"
```

### Task 13: Fix preprocess/export_snapshot.py and build_embeddings.py imports

**Files:**
- Modify: `engine/cluster_engine/preprocess/export_snapshot.py`
- Modify: `engine/cluster_engine/preprocess/build_embeddings.py`

- [ ] **Step 1: Update export_snapshot.py imports and path depth**

**Critical path depth fix:** `ENGINE_DIR = Path(__file__).resolve().parent.parent` currently resolves to `engine/`. After moving to `engine/cluster_engine/preprocess/`, it needs `.parent.parent.parent`:

```python
# Before (at engine/preprocess/export_snapshot.py):
ENGINE_DIR = Path(__file__).resolve().parent.parent

# After (at engine/cluster_engine/preprocess/export_snapshot.py):
ENGINE_DIR = Path(__file__).resolve().parent.parent.parent
```

Then fix imports:
```python
# Before:
from data.collector import DataCollector
from algorithm.pipeline import AlgorithmPipeline

# After:
from data_engine import get_data_engine
from cluster_engine.algorithm.pipeline import AlgorithmPipeline
```

Also update any direct `DataCollector()` instantiation to use `get_data_engine()`.

- [ ] **Step 2: Update build_embeddings.py imports and path depth**

**Critical path depth fix:**

```python
# Before (at engine/preprocess/build_embeddings.py):
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# After (at engine/cluster_engine/preprocess/build_embeddings.py):
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```

`engine/cluster_engine/preprocess/build_embeddings.py` line 433:

```python
# Before:
from preprocess.rebuild_bge import _build_weighted_text

# After:
from cluster_engine.preprocess.rebuild_bge import _build_weighted_text
```

Also update the usage docstring to reflect the new module path:
```
使用方式: cd engine && python -m cluster_engine.preprocess.build_embeddings
```

- [ ] **Step 3: Update rebuild_bge.py path depth and usage docstring**

**Critical path depth fix:**

```python
# Before (at engine/preprocess/rebuild_bge.py):
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# After (at engine/cluster_engine/preprocess/rebuild_bge.py):
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```

Change the usage comment to:
```
用法：cd engine && python -m cluster_engine.preprocess.rebuild_bge
```

- [ ] **Step 4: Commit**

```bash
git add engine/cluster_engine/preprocess/ && git commit -m "fix: preprocess 模块导入路径迁移"
```

---

## Chunk 4: Cleanup and Verification

### Task 14: Delete old directories and files

**Files:**
- Delete: `engine/data/` (now empty after moves)
- Delete: `engine/storage/` (now empty after moves)
- Delete: `engine/algorithm/` (now empty after moves)
- Delete: `engine/preprocess/` (now empty after moves)
- Delete: `engine/api/routes/terrain.py` (replaced by cluster_engine/routes.py)
- Delete: `engine/api/routes/__init__.py` (if now empty)

- [ ] **Step 1: Remove old directories**

```bash
rm -rf engine/data/sources engine/data/__init__.py engine/data/
rm -rf engine/storage/__init__.py engine/storage/
rm -rf engine/algorithm/
rm -rf engine/preprocess/
rm -f engine/api/routes/terrain.py engine/api/routes/__init__.py
```

Note: `data/precomputed/` stays (it's at project root level `data/`, not `engine/data/`).

- [ ] **Step 2: Verify no broken imports**

```bash
cd engine && python3 -c "
from data_engine import get_data_engine
from cluster_engine import get_cluster_engine
from main import app
print('All imports OK')
print(f'App routes: {len(app.routes)}')
"
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: 删除旧的 data/storage/algorithm/preprocess 目录"
```

### Task 15: Start backend and verify all APIs

- [ ] **Step 1: Start the backend**

```bash
cd engine && python3 main.py &
sleep 5
```

- [ ] **Step 2: Verify health endpoint**

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

Expected: status "ok", non-zero stock_count

- [ ] **Step 3: Verify data engine routes**

```bash
curl -s http://localhost:8000/api/v1/data/health | python3 -m json.tool
curl -s "http://localhost:8000/api/v1/data/profiles?q=茅台&limit=3" | python3 -m json.tool
curl -s http://localhost:8000/api/v1/data/snapshot/dates | python3 -m json.tool
```

- [ ] **Step 4: Verify terrain compute**

```bash
curl -s -X POST http://localhost:8000/api/v1/terrain/compute \
  -H "Content-Type: application/json" \
  -d '{"z_metric":"pct_chg","resolution":64}' 2>&1 | head -20
```

Expected: SSE events with progress then complete

- [ ] **Step 5: Verify stock search**

```bash
curl -s "http://localhost:8000/api/v1/stocks/search?q=贵州茅台" | python3 -m json.tool | head -20
```

- [ ] **Step 6: Kill backend and commit final**

```bash
kill %1
git add -A && git commit -m "verified: 双引擎分离完成，所有 API 正常"
```

### Task 16: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update project structure section**

Reflect the new `data_engine/` and `cluster_engine/` structure and module descriptions.

- [ ] **Step 2: Update run commands**

```markdown
## 运行
- 后端: `cd engine && python main.py` (端口 8000)
- 前端: `cd web && npm run dev` (端口 3000)
- MCP: `cd engine && python -m mcpserver` (stdio, 配置见 `.mcp.json`)
- 重建嵌入: `cd engine && python -m cluster_engine.preprocess.rebuild_bge`
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md && git commit -m "docs: CLAUDE.md 更新双引擎模块结构"
```
