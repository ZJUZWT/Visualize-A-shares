# 数据源升级设计规格

## 目标

在不改变 DataEngine 对外接口的前提下，引入 DataProvider 统一抽象层，修复已知数据质量问题，增加盘中定时快照刷新和分钟K线全频率支持，加固降级链可靠性。

## 需求清单

1. `DataProvider` 统一接口抽象，现有 5 个数据源逐步适配
2. 统一缓存策略、重试策略、健康检查
3. 修复节假日判断（引入交易日历）
4. 财务数据 DuckDB 持久化
5. 快照 `updated_at` 新鲜度兜底
6. 盘中定时快照刷新（1 分钟间隔，可配置）
7. 分钟K线全频率（5m/15m/30m/60m）
8. 降级链加固（熔断、重试、健康追踪）

## 架构

```
DataEngine (对外接口不变，全部同步方法)
    └── ProviderManager (同步接口，内部用 asyncio.to_thread 包装 IO)
            ├── TencentProvider (implements DataProvider)
            ├── AKShareProvider (implements DataProvider)
            ├── EastMoneyProvider (implements DataProvider)
            ├── THSProvider (implements DataProvider)
            └── BaoStockProvider (implements DataProvider)
```

### DataProvider 抽象基类

所有方法为同步方法。现有数据源（AKShare、BaoStock 等）本身就是同步库，无需 async。ProviderManager 在需要时通过 `asyncio.to_thread` 将同步调用放入线程池，避免阻塞事件循环。

```python
class DataProvider(ABC):
    name: str
    priority: int  # 数字越小优先级越高
    capabilities: set[str]

    @abstractmethod
    def get_snapshot(self) -> pd.DataFrame: ...

    @abstractmethod
    def get_daily(self, code: str, start: str, end: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_kline(self, code: str, freq: str, days: int) -> pd.DataFrame: ...

    @abstractmethod
    def get_financial(self, code: str, year: int, quarter: int) -> pd.DataFrame: ...

    @abstractmethod
    def get_news(self, code: str, limit: int) -> pd.DataFrame: ...

    @abstractmethod
    def get_announcements(self, code: str, limit: int) -> pd.DataFrame: ...

    @abstractmethod
    def get_sector_board_list(self, board_type: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_sector_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_sector_fund_flow_rank(self, indicator: str, sector_type: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_sector_constituents(self, board_name: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_intraday_history(self, code: str, freq: str, start: str, end: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_market_history_batch(self, codes: list[str], days: int, on_progress=None, on_batch_done=None) -> dict[str, pd.DataFrame]: ...

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities
```

不支持的方法返回空 `pd.DataFrame()`，不抛异常。

### Capability 完整列表

| Capability | 说明 | Tencent | AKShare | EastMoney | THS | BaoStock |
|-----------|------|---------|---------|-----------|-----|----------|
| `snapshot` | 全市场实时快照 | ✅ | ✅ | ✅ | ❌ | ❌ |
| `daily` | 个股日线历史 | ✅ | ✅ | ✅ | ❌ | ✅ |
| `kline_5m` | 5分钟K线 | ✅ | ✅ | ✅ | ❌ | ❌ |
| `kline_15m` | 15分钟K线 | ✅ | ✅ | ✅ | ❌ | ❌ |
| `kline_30m` | 30分钟K线 | ✅ | ✅ | ✅ | ❌ | ❌ |
| `kline_60m` | 60分钟K线 | ✅ | ✅ | ✅ | ❌ | ❌ |
| `financial` | 季频财务数据 | ❌ | ✅ | ❌ | ❌ | ✅ |
| `news` | 个股新闻 | ❌ | ✅ | ✅ | ❌ | ❌ |
| `announcements` | 公司公告 | ❌ | ✅ | ✅ | ❌ | ❌ |
| `sector_board` | 板块列表+行情 | ❌ | ✅ | ✅ | ✅ | ❌ |
| `sector_history` | 板块历史K线 | ❌ | ✅ | ✅ | ✅ | ❌ |
| `sector_fund_flow` | 板块资金流 | ❌ | ✅ | ✅ | ❌ | ❌ |
| `sector_constituents` | 板块成分股 | ❌ | ✅ | ✅ | ❌ | ❌ |
| `market_history_batch` | 全市场历史批量 | ❌ | ✅ | ❌ | ❌ | ✅ |

### ProviderManager 接口

```python
class ProviderManager:
    def __init__(self, providers: list[DataProvider]): ...

    # —— 数据获取（同步，与 DataProvider 方法一一对应）——
    def get_snapshot(self) -> pd.DataFrame: ...
    def get_daily(self, code: str, start: str, end: str) -> pd.DataFrame: ...
    def get_kline(self, code: str, freq: str, days: int) -> pd.DataFrame: ...
    def get_financial(self, code: str, year: int, quarter: int) -> pd.DataFrame: ...
    def get_news(self, code: str, limit: int) -> pd.DataFrame: ...
    def get_announcements(self, code: str, limit: int) -> pd.DataFrame: ...
    def get_sector_board_list(self, board_type: str) -> pd.DataFrame: ...
    def get_sector_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame: ...
    def get_sector_fund_flow_rank(self, indicator: str, sector_type: str) -> pd.DataFrame: ...
    def get_sector_constituents(self, board_name: str) -> pd.DataFrame: ...
    def get_intraday_history(self, code: str, freq: str, start: str, end: str) -> pd.DataFrame: ...
    def get_market_history_batch(self, codes: list[str], days: int, on_progress=None, on_batch_done=None) -> dict[str, pd.DataFrame]: ...

    # —— 健康状态 ——
    def get_health(self) -> dict: ...
    # 返回格式：
    # {
    #   "providers": {
    #     "tencent": {
    #       "status": "healthy" | "degraded" | "circuit_broken",
    #       "success_rate": 0.95,
    #       "avg_latency_ms": 120,
    #       "last_failure": "2026-03-21T14:30:00" | null,
    #       "circuit_broken_until": "2026-03-21T14:31:00" | null
    #     },
    #     ...
    #   }
    # }
```

每个 `get_*` 方法内部逻辑：
1. 筛选支持对应 capability 的 providers，按 priority 排序
2. 跳过已熔断的 provider
3. 调用第一个可用 provider，失败则指数退避重试（最多 2 次）
4. 重试仍失败 → 记录失败计数 → 降级到下一个 provider
5. 所有 provider 都失败 → 返回空 DataFrame（不抛异常）

### 重试与熔断规则

- **重试范围**：单个 provider 的单次 `get_*` 调用。重试 2 次（间隔 0.5s, 1s）。
- **熔断触发**：同一 provider 连续 3 次最终失败（重试耗尽后仍失败才计 1 次）。
- **熔断时长**：60 秒。期间该 provider 被跳过，请求直接路由到下一级。
- **探活**：熔断期满后，下一次请求会尝试该 provider。成功 → 重置失败计数，恢复正常；失败 → 重新熔断 60 秒。

### DataEngine 切换

DataEngine 对外接口完全不变。`__init__` 中：

```python
class DataEngine:
    def __init__(self):
        self._provider_mgr = ProviderManager([
            TencentProvider(),
            AKShareProvider(),
            EastMoneyProvider(),
            THSProvider(),
            BaoStockProvider(),
        ])
        self._store = DuckDBStore()
        self._profiles = load_profiles()

    # 保留 collector 属性做兼容，指向 provider_mgr
    @property
    def collector(self) -> ProviderManager:
        return self._provider_mgr
```

现有消费者（Agent Brain、Expert、路由层）零改动。`get_market_history_streaming` 改为调用 `self._provider_mgr.get_market_history_batch()`。

## 缓存与持久化策略

| 数据类型 | 缓存位置 | TTL / 刷新策略 |
|---------|---------|---------------|
| 实时快照 | DuckDB + 内存 | 盘中：定时刷新（可配置，默认 1 分钟）；盘后：当日收盘价不过期 |
| 日线历史 | DuckDB | 按交易日历判断是否需要回填，非交易日不触发网络 |
| 分钟K线 | DuckDB | 按频率+交易日历，盘中可增量追加 |
| 财务数据 | DuckDB（新增） | 季度粒度，`(code, year, quarter)` 唯一键，命中直接返回 |
| 公司概况 | JSON 文件 | 保持现状 |

### TradingCalendar

```python
class TradingCalendar:
    def __init__(self, store: DuckDBStore): ...

    def is_trading_day(self, d: date) -> bool: ...
    def last_trading_day(self) -> date: ...
    def trading_days_between(self, start: date, end: date) -> int: ...
    def is_trading_hours(self) -> bool: ...  # 9:30-11:30 或 13:00-15:00
    def refresh(self): ...  # 从 AKShare 拉取并持久化
```

- 启动时从 DuckDB 加载缓存的交易日历。如果缓存为空或不包含当年数据，从 AKShare 拉取当年交易日历并持久化。
- **AKShare 不可用时的 fallback**：使用现有的周末排除逻辑（`weekday() < 5`）作为降级方案，记录 warning 日志。不会 fail hard。
- DuckDB 表：`trading_calendar`，字段 `(date DATE PRIMARY KEY)`，存储所有交易日。
- 替换 DataEngine 中现有的 `_count_trading_days_between()` 方法。

### 快照新鲜度

- ProviderManager 写入快照时强制带 `updated_at` 时间戳（`datetime.now()`）
- 现有 `snapshot` 表已有 `updated_at` 列（DuckDBStore.save_snapshot 写入时带），无需 schema 迁移
- 读取时校验 `updated_at`，不再依赖数据源是否返回该字段

### 财务数据持久化

- 新增 DuckDB 表 `financial_data`：

```sql
CREATE TABLE IF NOT EXISTS financial_data (
    code VARCHAR,
    year INTEGER,
    quarter INTEGER,
    data_json TEXT,  -- JSON 序列化的 DataFrame records
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, year, quarter)
)
```

- 读取时：命中缓存 → `pd.DataFrame(json.loads(data_json))` 返回 DataFrame
- 未命中 → 走 ProviderManager 降级链拉取 → 拿到 DataFrame → `df.to_json(orient='records')` 持久化 → 返回 DataFrame
- 消费者拿到的始终是 `pd.DataFrame`，与现有 `DataEngine.get_financial_data` 返回类型一致

## 盘中定时快照刷新

### SnapshotScheduler

- 在 `backend/main.py` 的 `startup` 事件中初始化，与 AgentScheduler 同级
- 使用 APScheduler 的 `IntervalTrigger`（interval=60s）
- 生命周期：`main.py startup` 创建并启动，`shutdown` 关闭

```python
class SnapshotScheduler:
    _instance: SnapshotScheduler | None = None

    @classmethod
    def get_instance(cls) -> SnapshotScheduler: ...

    def start(self):
        # APScheduler IntervalTrigger, 每 60 秒
        # job 内部检查：TradingCalendar.is_trading_hours() → 否则跳过
        ...

    async def _refresh_job(self):
        if not self._calendar.is_trading_day(date.today()):
            return
        if not self._calendar.is_trading_hours():
            return
        df = self._provider_mgr.get_snapshot()
        if not df.empty:
            self._store.save_snapshot(df)

    def shutdown(self): ...
```

- 拉取失败记录日志 + 健康状态标记，不影响下一轮
- 刷新间隔可通过 `config.yaml` 配置（`data.snapshot_refresh_seconds: 60`）
- 消费者读本地 DuckDB 即可，`DataEngine.get_snapshot()` 逻辑不变

## 分钟K线全频率

- 支持频率：5m / 15m / 30m / 60m
- 数据源优先级：Tencent → AKShare → EastMoney（BaoStock 不支持分钟K线，跳过）
- DuckDB 持久化：复用现有 `kline_minutes` 表，`(code, freq, timestamp)` 唯一键
- 增量更新逻辑：
  1. 查本地 `max(timestamp)` for `(code, freq)`
  2. 如果 `max(timestamp)` 存在且在最近 N 个交易日内 → 只拉 `max(timestamp)` 之后的数据追加
  3. 如果本地无数据或太旧 → 全量拉取 `days` 天
  4. 不处理中间空洞（罕见场景，全量重拉即可覆盖）
- `DataEngine.get_kline(code, frequency, days)` 接口不变，去掉内部的 60m 硬编码限制
- 各 Provider 按 capabilities 声明支持哪些频率（`kline_5m`, `kline_15m`, `kline_30m`, `kline_60m`）

## 降级链加固

见上方「重试与熔断规则」章节。

健康端点扩展（`/api/v1/data/health`）返回格式：

```json
{
  "status": "ok",
  "stock_count": 5200,
  "profiles_count": 5200,
  "providers": {
    "tencent": {
      "status": "healthy",
      "success_rate": 0.98,
      "avg_latency_ms": 85,
      "last_failure": null,
      "circuit_broken_until": null
    },
    "akshare": {
      "status": "circuit_broken",
      "success_rate": 0.45,
      "avg_latency_ms": 2300,
      "last_failure": "2026-03-21T14:28:00",
      "circuit_broken_until": "2026-03-21T14:29:00"
    }
  },
  "snapshot_scheduler": {
    "running": true,
    "last_refresh": "2026-03-21T14:27:00",
    "refresh_interval_seconds": 60
  },
  "trading_calendar": {
    "loaded": true,
    "trading_days_count": 242,
    "is_trading_day_today": true,
    "is_trading_hours_now": true
  }
}
```

## 文件结构

```
backend/engine/data/
├── provider/
│   ├── __init__.py          # 导出所有 Provider
│   ├── base.py              # DataProvider ABC
│   ├── manager.py           # ProviderManager (路由+重试+熔断+健康)
│   ├── tencent.py           # TencentProvider
│   ├── akshare.py           # AKShareProvider
│   ├── eastmoney.py         # EastMoneyProvider
│   ├── ths.py               # THSProvider
│   └── baostock.py          # BaoStockProvider
├── calendar.py              # TradingCalendar
├── snapshot_scheduler.py    # SnapshotScheduler
├── collector.py             # 保留，逐步废弃
├── engine.py                # DataEngine (接口不变，内部切换到 ProviderManager)
├── store.py                 # DuckDBStore (新增 financial_data 表)
└── ...
```

每个 Provider 文件从现有 `collector.py` 中对应的 Source 类提取逻辑。`collector.py` 保留但标记 deprecated，过渡期后删除。

## 不做的事情

- 不引入付费数据源
- 不做 WebSocket 实时推送
- 不做前端监控面板（后续迭代）
- 不改变 DataEngine 对外接口签名
