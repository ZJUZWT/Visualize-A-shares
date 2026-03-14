# 数据引擎 / 聚类引擎分离设计

## 背景

当前 `engine/` 中数据采集、持久化、算法计算耦合在一起。`terrain.py` 路由文件同时编排行情拉取、DuckDB 存储、算法流水线。`FeatureEngineer` 直接从文件系统加载公司概况。目标是将数据层和算法层解耦为两个独立模块，使数据引擎可独立使用，也可被第三方替换。

## 设计原则

- **数据引擎 = 可替换的数据供应商**：管理原始数据的获取、持久化、查询
- **聚类引擎 = 算法消费者**：从数据引擎获取数据，执行特征提取/聚类/降维/插值
- **同进程模块分离**：共享 FastAPI 实例，各自注册路由，通过 Python 接口通信
- **接口契约驱动**：聚类引擎依赖 DataEngine 的抽象接口，不依赖具体实现

## 数据归属划分

| 数据 | 归属 | 理由 |
|------|------|------|
| 行情快照 (snapshot) | 数据引擎 | 网络拉取的原始数据 |
| 日线K线 (daily) | 数据引擎 | 网络拉取的原始数据 |
| 每日快照历史 (snapshot_daily) | 数据引擎 | 网络拉取的原始数据 |
| 公司概况 JSON | 数据引擎 | 爬取的公司基础信息 |
| DuckDB 存储 | 数据引擎 | 持久化层 |
| BGE 嵌入向量 (.npz) | 聚类引擎 | 模型计算的算法产物 |
| 聚类结果 (cluster_results) | 聚类引擎 | 算法运行时产物 |
| 特征矩阵 | 聚类引擎 | 算法运行时产物 |
| 预测结果 | 聚类引擎 | 运行时计算，不落库 |

## 目录结构

```
engine/
  data_engine/                  # 数据引擎模块
    __init__.py                 # 导出 DataEngine 类
    engine.py                   # DataEngine 主类（门面）
    collector.py                # ← data/collector.py
    store.py                    # ← storage/duckdb_store.py
    precomputed.py              # 公司概况 JSON 加载
    sources/                    # ← data/sources/
      __init__.py
      base.py
      tencent_source.py
      akshare_source.py
      baostock_source.py
    routes.py                   # /api/v1/data/* 路由
    schemas.py                  # 数据引擎 Pydantic models

  cluster_engine/               # 聚类引擎模块
    __init__.py                 # 导出 ClusterEngine 主类
    engine.py                   # ClusterEngine 主类（门面）
    algorithm/                  # ← algorithm/
      __init__.py
      clustering.py
      features.py
      interpolation.py
      pipeline.py
      projection.py
      predictor.py
      predictor_v2.py
      factor_backtest.py
    preprocess/                 # ← preprocess/
      __init__.py
      rebuild_bge.py
      build_embeddings.py
      export_snapshot.py
    routes.py                   # /api/v1/terrain/* 路由
    schemas.py                  # 聚类引擎 Pydantic models

  # 保留在根级
  config.py                     # 全局配置
  main.py                       # FastAPI 入口，注册两个引擎路由
  llm/                          # LLM 模块（独立，不变）
  mcpserver/                    # MCP Server（调用方式改为通过引擎接口）
```

## DataEngine 接口设计

```python
class DataEngine:
    """数据引擎 — 原始数据的获取、持久化、查询门面"""

    def __init__(self):
        self._collector = DataCollector()
        self._store = DuckDBStore()
        self._profiles = self._load_profiles()

    # ── 行情数据 ──
    def get_realtime_quotes(self) -> pd.DataFrame:
        """拉取全市场实时行情（网络请求）"""

    def get_snapshot(self) -> pd.DataFrame:
        """获取 DuckDB 中最新快照（本地查询）"""

    def save_snapshot(self, df: pd.DataFrame):
        """保存行情快照到 DuckDB"""

    # ── 日线历史 ──
    def get_daily_history(self, code: str, start: str, end: str) -> pd.DataFrame:
        """获取个股日线，优先本地 DuckDB，缺失则通过 collector 拉取"""

    def get_daily_history_batch(
        self, snapshot: pd.DataFrame, min_days: int = 20
    ) -> dict[str, pd.DataFrame]:
        """
        批量获取日线历史（从本地 DuckDB 缓存）
        从 snapshot 中提取 code 列表，逐只查询 store.get_daily()，
        仅返回有 ≥min_days 天数据的股票。
        注意：这是纯本地查询，不触发网络请求。
        """

    def get_market_history_streaming(self, codes, days, on_progress, on_batch_done) -> dict:
        """流式批量拉取全市场历史日线（网络请求，带进度回调）"""

    # ── 财务数据 ──
    def get_financial_data(self, code: str, year: int, quarter: int) -> pd.DataFrame:
        """获取季频财务数据（逐级降级）"""

    # ── 快照历史（回放用）──
    def get_snapshot_daily_dates(self) -> list[str]:
    def get_snapshot_daily_range(self, days: int) -> dict[str, pd.DataFrame]:
    def save_history_as_snapshots(self, history_by_date: dict):

    # ── 公司基础信息 ──
    def get_profiles(self) -> dict[str, dict]:
        """获取全量公司概况 {code: {name, industry, scope, ...}}"""

    def get_profile(self, code: str) -> dict | None:
        """获取单只股票概况"""

    # ── 元信息 ──
    def get_stock_count(self) -> int:
    def health_check(self) -> dict:

    @property
    def available_sources(self) -> list[str]:
```

## DataEngine REST API 路由

```
GET  /api/v1/data/health           # 数据引擎健康检查
GET  /api/v1/data/snapshot          # 获取最新行情快照
GET  /api/v1/data/snapshot/dates    # 获取历史快照日期列表
GET  /api/v1/data/snapshot/history  # 获取指定日期范围的快照
GET  /api/v1/data/daily/{code}      # 获取个股日线
GET  /api/v1/data/profiles          # 获取公司概况列表
GET  /api/v1/data/profiles/{code}   # 获取单只公司概况
POST /api/v1/data/fetch/realtime    # 触发实时行情拉取
POST /api/v1/data/fetch/history     # 触发历史数据拉取（SSE 流式）
```

## ClusterEngine 接口设计

```python
class ClusterEngine:
    """聚类引擎 — 依赖 DataEngine 获取数据，执行算法流水线"""

    def __init__(self, data_engine: DataEngine):
        self._data = data_engine          # 通过依赖注入获取数据引擎
        self._pipeline = AlgorithmPipeline(data_engine)  # 流水线也注入数据引擎

    def compute_terrain(self, z_metric, resolution, ...) -> TerrainResult:
        """全量计算3D地形（内部从 data_engine 获取行情+概况）"""

    def update_z_axis(self, snapshot: pd.DataFrame, z_column: str) -> TerrainResult | None:
        """快速刷新 Z 轴（保持 XY 布局不变），代理到 pipeline.update_z_axis"""

    def compute_history_frames(self, days, z_metric) -> dict:
        """历史回放帧计算（封装对 pipeline 内部缓存 _last_embedding/_last_meta_df 的访问）"""

    def search_stocks(self, query: str) -> list[dict]:
        """搜索股票"""

    def try_auto_inject_icir_weights(self):
        """启动时自动从历史数据计算 ICIR 权重并注入预测器"""

    @property
    def last_result(self) -> TerrainResult | None:

    @property
    def pipeline(self) -> AlgorithmPipeline:
        """暴露 pipeline 给需要直接访问 predictor_v2 等内部组件的路由"""
```

## 聚类引擎路由（基本不变）

```
GET  /api/v1/health                 # 整体健康检查（调用两个引擎）
POST /api/v1/terrain/compute        # 全量计算（SSE）
GET  /api/v1/terrain/refresh        # 快速刷新 Z 轴
POST /api/v1/terrain/history        # 历史回放（SSE）
GET  /api/v1/stocks/search          # 搜索股票
POST /api/v1/factor/backtest        # 因子回测
GET  /api/v1/factor/weights         # 因子权重
WS   /api/v1/ws/terrain             # WebSocket 实时推送
```

## 关键改动

### 1. AlgorithmPipeline 不再直接依赖文件系统加载行情

当前 `compute_full()` 接收 `snapshot: pd.DataFrame` 参数（由路由层传入），这一点已经是好的。改动是让路由层从 `DataEngine` 获取 snapshot，而不是直接调用 `DataCollector`。

### 2. FeatureEngineer.PrecomputedData 拆分

- `profiles`（公司概况）→ 从 `DataEngine.get_profiles()` 获取
- `embeddings`（BGE 嵌入）→ 留在聚类引擎的 `PrecomputedData` 中直接加载

`FeatureEngineer` 的构造函数改为接收 `profiles: dict` 参数，不再自己加载 JSON。

相应地，`AlgorithmPipeline.__init__` 的签名也需要变化：接收 `data_engine: DataEngine` 参数，在构造 `FeatureEngineer` 时传入 `data_engine.get_profiles()`。

### 3. terrain.py 拆分

当前 `terrain.py` 包含：
- 全局单例管理 (`get_collector`, `get_pipeline`, `get_store`)
- 地形计算编排 (`compute_terrain`)
- 历史回放编排 (`get_terrain_history`)
- 因子回测 (`run_factor_backtest`)
- WebSocket (`websocket_terrain`)

拆分后：
- `data_engine/routes.py`：数据查询/拉取相关路由
- `cluster_engine/routes.py`：地形计算/搜索/因子/WebSocket 路由
- 单例管理移入各自的 `__init__.py`

### 4. MCP Server 适配

`mcpserver/data_access.py` 当前已经是通过 REST API 访问后端。分离后 MCP 的 API 路径不变（聚类路由保持原路径）。需要更新的导入路径：

- `tools.py` 中 `_load_profiles()` → 改为走数据引擎 API 或直接导入 `DataEngine`
- `tools.py` 中 `from algorithm.predictor_v2 import FACTOR_DEFS` → `from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS`
- `tools.py` 中 `from algorithm.factor_backtest import FactorBacktester` → `from cluster_engine.algorithm.factor_backtest import FactorBacktester`

### 5. main.py 入口与启动钩子

```python
from data_engine.routes import router as data_router
from cluster_engine.routes import router as cluster_router

app.include_router(data_router)     # 路由内部定义 prefix="/api/v1/data"
app.include_router(cluster_router)  # 路由内部定义 prefix="/api/v1"

@app.on_event("startup")
async def startup():
    # ... 日志 ...
    # ICIR 自动校准：ClusterEngine 内部访问 DataEngine 的 store 获取历史数据
    try:
        from cluster_engine import get_cluster_engine
        get_cluster_engine().try_auto_inject_icir_weights()
    except Exception as e:
        logger.warning(f"⚠️ ICIR 自动校准跳过: {e}")
```

`_try_auto_inject_icir_weights` 从 `terrain.py` 的模块级函数迁移为 `ClusterEngine.try_auto_inject_icir_weights()` 实例方法，内部通过 `self._data`（DataEngine）获取快照日期列表和历史数据，通过 `self._pipeline.predictor_v2` 注入权重。

### 6. preprocess/export_snapshot.py 导入迁移

`export_snapshot.py` 当前导入：
```python
from data.collector import DataCollector
from algorithm.pipeline import AlgorithmPipeline
```

迁移后更新为：
```python
from data_engine.collector import DataCollector
from cluster_engine.algorithm.pipeline import AlgorithmPipeline
```

并将 `DataCollector()` 直接实例化改为通过 `DataEngine` 获取，保持与新架构一致。

### 7. schemas.py 拆分策略

当前 `api/schemas.py` 包含三类 schema：

| Schema | 归属 | 理由 |
|--------|------|------|
| `HealthResponse` | `cluster_engine/schemas.py` | 整体健康检查由聚类路由提供 |
| `ComputeRequest`, `TerrainResponse` | `cluster_engine/schemas.py` | 地形计算专属 |
| `ClusterInfo`, `StockPoint`, `ClusterAffinity`, `RelatedStock` | `cluster_engine/schemas.py` | 算法产物 |
| `HistoryRequest`, `HistoryResponse`, `HistoryFrame` | `cluster_engine/schemas.py` | 历史回放是聚类层编排 |
| `ChatRequest`, `ChatResponse`, `LLMConfigRequest`, `LLMConfigResponse` | 保留在 `api/schemas.py`（LLM 路由共享） | LLM 模块独立，不属于任一引擎 |
| `StockSearchResult` | `cluster_engine/schemas.py` | 搜索是聚类层功能 |

`data_engine/schemas.py` 新建，定义数据引擎独有的响应模型（快照查询、概况查询等）。

### 8. cluster_results 表的归属

`cluster_results` 表虽然存储在 DuckDB 中，但其数据由聚类引擎产出。处理方式：
- `DuckDBStore`（数据引擎）保留 `save_cluster_results()` 和 `get_cluster_results()` 方法作为通用存储服务
- `ClusterEngine` 通过 `data_engine.store` 的这些方法读写聚类结果
- 数据引擎不解释这些数据的语义，只提供存储能力

## 旧路径兼容

分离后删除旧目录：
- `data/` → `data_engine/`（`data/precomputed/` 保持在项目根级不动，只是代码模块迁移）
- `storage/` → 合并入 `data_engine/store.py`
- `algorithm/` → `cluster_engine/algorithm/`
- `preprocess/` → `cluster_engine/preprocess/`
- `api/routes/terrain.py` → 拆分为两个 `routes.py`
- `api/schemas.py` → 拆分为两个 `schemas.py`

注意：`data/precomputed/` 目录（存放 JSON、NPZ 文件）保持在项目根级 `data/precomputed/`，不移动。迁移的只是 Python 代码模块。

## 向后兼容

- 所有现有 API 路径保持不变（聚类引擎路由前缀不变）
- 新增 `/api/v1/data/*` 路由
- 前端无需修改
- MCP Server 无需修改（API 路径不变）

## 验证标准

1. `python main.py` 正常启动，两个引擎路由都注册
2. 现有所有 API 功能正常（地形计算、搜索、因子回测）
3. 新增 `/api/v1/data/*` 路由可独立查询数据
4. MCP 工具正常工作
5. 前端无感知变化
