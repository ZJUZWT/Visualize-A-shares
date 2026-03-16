# 分钟级 K 线数据引擎扩展 — 设计文档

## 目标

扩展数据引擎，支持通用的多频率 K 线查询接口。当前只实现 60min（小时线），但接口层预留扩展能力，后续添加 15min/5min 只需新增 collector 方法 + 建表，上层 API 不变。

## 动机

- 量化专家需要小时级技术指标（RSI/MACD/布林带）做日内趋势判断
- 数据专家需要日内量价分布分析（哪个时段放量、价格波动规律）
- 当前所有专家只能拿到日线数据，无法做短周期分析

## 架构决策

### 通用接口 + 按需实现

```
接口层:  get_kline(code, frequency, days)    ← 通用，frequency 枚举
存储层:  stock_kline_60m 表                   ← 按频率分表，命名规范 stock_kline_{freq}
采集层:  collector.get_intraday(code, freq, start, end)  ← 通用签名
数据源:  AKShare primary → BaoStock fallback  ← 复用现有降级模式
```

### 为什么按频率分表而非单表 + frequency 列

- DuckDB 是列式存储，分表后每张表的 datetime 索引更紧凑
- 不同频率的数据量差异巨大（60min ~4条/天 vs 5min ~48条/天）
- 查询时不需要 WHERE frequency = ? 过滤，直接扫目标表
- 后续加新频率只需 CREATE TABLE，不影响已有表性能

## 数据源分析

### AKShare `stock_zh_a_hist_min_em` (Primary)

```python
ak.stock_zh_a_hist_min_em(
    symbol="600519",
    period="60",           # "1"/"5"/"15"/"30"/"60"
    start_date="2026-03-10 09:30:00",
    end_date="2026-03-16 15:00:00",
    adjust="qfq"           # 前复权
)
```

返回字段（60min）：时间, 开盘, 收盘, 最高, 最低, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅, 换手率

### BaoStock `query_history_k_data_plus` (Fallback)

```python
bs.query_history_k_data_plus(
    "sh.600519",
    "date,time,code,open,high,low,close,volume,amount",
    start_date="2026-03-10",
    end_date="2026-03-16",
    frequency="60",        # "5"/"15"/"30"/"60"
    adjustflag="2"         # 前复权
)
```

返回字段：date, time, code, open, high, low, close, volume, amount（无 pct_chg/turnover_rate）

## 详细设计

### 1. 频率枚举

```python
# data_engine/schemas.py 新增
from enum import Enum

class KlineFrequency(str, Enum):
    DAILY = "daily"      # 已有，映射到 stock_daily
    MIN_60 = "60m"       # 本次实现
    # 未来扩展:
    # MIN_15 = "15m"
    # MIN_5 = "5m"
```

此枚举用于 REST API 参数校验（FastAPI 自动生成 422 错误）和 store 白名单。

### 2. DuckDB 新表 `stock_kline_60m`

```sql
CREATE TABLE IF NOT EXISTS stock_kline_60m (
    code        VARCHAR NOT NULL,
    datetime    TIMESTAMP NOT NULL,   -- 如 2026-03-16 10:30:00
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      BIGINT,
    amount      DOUBLE,
    pct_chg     DOUBLE,              -- AKShare 有，BaoStock 无（NULL）
    turnover_rate DOUBLE,            -- AKShare 有，BaoStock 无（NULL）
    PRIMARY KEY (code, datetime)
)
```

命名规范：`stock_kline_{freq}`，后续 15m → `stock_kline_15m`。

### 3. BaseDataSource 新增可选方法

```python
# sources/base.py 新增
def get_intraday_history(
    self,
    code: str,
    frequency: str,       # "60", "30", "15", "5"
    start_date: str,      # "2026-03-10"
    end_date: str,        # "2026-03-16"
) -> pd.DataFrame:
    """获取分钟级 K 线 — 子类可选实现"""
    raise NotImplementedError
```

### 4. AKShareSource 实现

```python
# sources/akshare_source.py 新增
def get_intraday_history(
    self, code: str, frequency: str, start_date: str, end_date: str
) -> pd.DataFrame:
    df = self._fetch_with_retry(
        self._ak.stock_zh_a_hist_min_em,
        "stock_zh_a_hist_min_em",
        symbol=code,
        period=frequency,
        start_date=f"{start_date} 09:30:00",
        end_date=f"{end_date} 15:00:00",
        adjust="qfq",
    )
    column_map = {
        "时间": "datetime",
        "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "amount",
        "涨跌幅": "pct_chg", "换手率": "turnover_rate",
    }
    df = df.rename(columns=column_map)
    df["datetime"] = pd.to_datetime(df["datetime"])
    available = [c for c in ["datetime","open","high","low","close",
                             "volume","amount","pct_chg","turnover_rate"]
                 if c in df.columns]
    return df[available].copy()
```

### 5. BaoStockSource 实现

```python
# sources/baostock_source.py 新增
def get_intraday_history(
    self, code: str, frequency: str, start_date: str, end_date: str
) -> pd.DataFrame:
    self._ensure_login()
    bs_code = self._to_bs_code(code)
    fields = "date,time,code,open,high,low,close,volume,amount"
    rs = self._bs.query_history_k_data_plus(
        bs_code, fields,
        start_date=start_date, end_date=end_date,
        frequency=frequency, adjustflag="2",
    )
    rows = []
    while (rs.error_code == "0") and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=rs.fields)
    # BaoStock time 格式: "20260316103000000" (YYYYMMDDHHMMSSmmm)
    # 直接从 time 字段前14位解析，不用 date 字段（date 带连字符会拼接出错）
    df["datetime"] = pd.to_datetime(
        df["time"].str[:14],  # "20260316103000"
        format="%Y%m%d%H%M%S"
    )
    numeric_cols = ["open","high","low","close","volume","amount"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["datetime","open","high","low","close","volume","amount"]].copy()
```

### 6. DataCollector 新增编排方法

```python
# collector.py 新增
def get_intraday_history(
    self, code: str, frequency: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """获取分钟级 K 线 — 逐级降级"""
    for source in self._sources:
        try:
            df = source.get_intraday_history(code, frequency, start_date, end_date)
            if df is not None and len(df) > 0:
                logger.debug(f"✅ {code} {frequency}min: {source.name} ({len(df)} 条)")
                return df
        except NotImplementedError:
            continue
        except Exception as e:
            logger.warning(f"⚠️ {source.name} {code} {frequency}min 失败: {e}")
    logger.error(f"❌ {code} {frequency}min 所有数据源均失败")
    return pd.DataFrame()
```

### 7. DuckDBStore 新增方法

表创建放在 `_init_tables()` 中（与现有 stock_daily 等表一起）：

```python
# store.py _init_tables() 中新增
self._conn.execute("""
    CREATE TABLE IF NOT EXISTS stock_kline_60m (
        code        VARCHAR NOT NULL,
        datetime    TIMESTAMP NOT NULL,
        open        DOUBLE,
        high        DOUBLE,
        low         DOUBLE,
        close       DOUBLE,
        volume      BIGINT,
        amount      DOUBLE,
        pct_chg     DOUBLE,
        turnover_rate DOUBLE,
        PRIMARY KEY (code, datetime)
    )
""")
```

频率白名单防止 SQL 注入：

```python
# store.py 新增

# 频率 → 表名白名单，防止 SQL 注入
VALID_KLINE_TABLES = {"60m": "stock_kline_60m"}

def _kline_table(self, frequency: str) -> str:
    """安全获取 K 线表名"""
    if frequency not in self.VALID_KLINE_TABLES:
        raise ValueError(f"不支持的 K 线频率: {frequency}")
    return self.VALID_KLINE_TABLES[frequency]

def save_kline(self, df: pd.DataFrame, frequency: str):
    """保存分钟级 K 线（UPSERT）"""
    table = self._kline_table(frequency)
    if df.empty:
        return
    # 确保 BaoStock 数据（无 pct_chg/turnover_rate）不会报错
    for col in ["pct_chg", "turnover_rate"]:
        if col not in df.columns:
            df[col] = None
    self._conn.execute(f"""
        INSERT OR REPLACE INTO {table}
        SELECT code, datetime, open, high, low, close,
               volume, amount, pct_chg, turnover_rate
        FROM df
    """)

def get_kline(
    self, code: str, frequency: str,
    start_datetime: str = "", end_datetime: str = ""
) -> pd.DataFrame:
    """查询分钟级 K 线"""
    table = self._kline_table(frequency)
    query = f"SELECT * FROM {table} WHERE code = ?"
    params = [code]
    if start_datetime:
        query += " AND datetime >= ?"
        params.append(start_datetime)
    if end_datetime:
        query += " AND datetime <= ?"
        params.append(end_datetime)
    query += " ORDER BY datetime"
    try:
        return self._conn.execute(query, params).fetchdf()
    except Exception:
        return pd.DataFrame()
```

### 8. DataEngine 门面方法

```python
# engine.py 新增
def get_kline(
    self, code: str, frequency: str = "60m", days: int = 5
) -> pd.DataFrame:
    """
    通用 K 线查询 — 本地优先，缺失时远程拉取并缓存

    Args:
        code: 股票代码
        frequency: "60m" (当前仅支持)
        days: 回溯交易日数，默认 5 天
    """
    import datetime
    freq_key = frequency.replace("m", "")  # "60m" → "60"

    end = datetime.date.today()
    start = end - datetime.timedelta(days=days + 5)  # 多拉几天补偿非交易日

    # 1. 先查本地
    local = self.store.get_kline(
        code, frequency,
        start_datetime=start.isoformat(),
        end_datetime=end.isoformat() + " 23:59:59",
    )
    # 60min 约 4 条/交易日，但 days 包含周末/节假日
    # 用 days * 2 作为保守阈值，避免非交易日导致反复远程拉取
    if len(local) >= days * 2:
        return local

    # 2. 本地不足，远程拉取
    df = self.collector.get_intraday_history(
        code, freq_key, start.isoformat(), end.isoformat()
    )
    if df.empty:
        return local if not local.empty else pd.DataFrame()

    # 3. 缓存到 DuckDB
    df["code"] = code
    self.store.save_kline(df, frequency)

    return self.store.get_kline(
        code, frequency,
        start_datetime=start.isoformat(),
        end_datetime=end.isoformat() + " 23:59:59",
    )
```

### 9. REST API 新增端点

```python
# routes.py 新增
from data_engine.schemas import KlineFrequency

@router.get("/kline/{code}")
async def get_kline(
    code: str,
    frequency: KlineFrequency = KlineFrequency.MIN_60,  # FastAPI 自动校验枚举
    days: int = 5,
):
    """获取分钟级 K 线数据"""
    if frequency == KlineFrequency.DAILY:
        raise HTTPException(status_code=400, detail="日线请使用 /daily/{code} 端点")
    df = await asyncio.to_thread(data_engine.get_kline, code, frequency.value, days)
    records = df.to_dict("records") if not df.empty else []
    return {"code": code, "frequency": frequency.value, "records": records, "count": len(records)}
```

### 10. 专家工具集成

量化专家和数据专家新增 `query_hourly` 工具（仅 engine_experts.py，不改 tools.py）：

> `expert/tools.py` 是 RAG 投资顾问的工具层，走 DataFetcher 抽象。小时线数据仅对 data/quant 引擎专家有意义，因此只在 `engine_experts.py` 的工具列表中添加，不扩展 RAG 工具集。

```python
# expert/engine_experts.py 中
# data expert 和 quant expert 的 TOOLS 列表新增:
{
    "name": "query_hourly",
    "description": "查询个股小时线K线数据（60分钟级别），返回最近N个交易日的OHLCV数据",
    "parameters": {"code": "股票代码", "days": "回溯天数，默认5"}
}
```

执行逻辑：
```python
async def _exec_query_hourly(self, code: str, days: int = 5) -> str:
    df = data_engine.get_kline(code, "60m", days)
    if df.empty:
        return f"{code} 暂无小时线数据"
    # 格式化返回最近的数据
    return df.tail(20).to_string(index=False)
```

## 数据流

```
Expert 调用 query_hourly("600519", 5)
    ↓
DataEngine.get_kline("600519", "60m", 5)
    ├─→ DuckDBStore.get_kline() — 本地查询
    │   └─→ 数据充足 → 直接返回
    └─→ 数据不足 → DataCollector.get_intraday_history()
        ├─→ AKShare stock_zh_a_hist_min_em(period="60") — Primary
        └─→ BaoStock query_history_k_data_plus(frequency="60") — Fallback
            ↓
        DuckDBStore.save_kline() — 缓存
            ↓
        返回结果
```

## 不做的事情

- 不做 1min/5min/15min/30min（接口预留，但不实现）
- 不做批量全市场分钟线拉取（按需单股查询即可）
- 不做分钟级实时推送（超出当前架构范围）
- 不修改现有 `get_daily_history` 接口（保持向后兼容）
- 不做分钟级技术指标计算（专家可基于原始 K 线自行计算）

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `engine/data_engine/sources/base.py` | 修改 | 新增 `get_intraday_history` 可选方法 |
| `engine/data_engine/sources/akshare_source.py` | 修改 | 实现 `get_intraday_history` |
| `engine/data_engine/sources/baostock_source.py` | 修改 | 实现 `get_intraday_history` |
| `engine/data_engine/collector.py` | 修改 | 新增 `get_intraday_history` 编排 |
| `engine/data_engine/store.py` | 修改 | 新增 `stock_kline_60m` 表 + `save_kline`/`get_kline` |
| `engine/data_engine/engine.py` | 修改 | 新增 `get_kline` 门面方法 |
| `engine/data_engine/routes.py` | 修改 | 新增 `/api/v1/data/kline/{code}` 端点 |
| `engine/expert/engine_experts.py` | 修改 | data/quant 专家新增 `query_hourly` 工具 |
