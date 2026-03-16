# 分钟级 K 线数据引擎扩展 — 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展数据引擎支持 60min K 线查询，通用接口预留多频率扩展能力

**Architecture:** 在现有三级降级采集器上新增 `get_intraday_history` 方法，DuckDB 按频率分表存储，DataEngine 门面提供 `get_kline` 统一入口，REST API 和引擎专家工具同步扩展

**Tech Stack:** Python, FastAPI, DuckDB, AKShare, BaoStock, Pandas

---

## Chunk 1: 数据源层

### Task 1: BaseDataSource 新增 get_intraday_history 接口

**Files:**
- Modify: `engine/data_engine/sources/base.py:62-69`

- [ ] **Step 1: 在 base.py 的可选方法区域新增 get_intraday_history**

在 `get_announcements` 方法之后、`UNIFIED_QUOTE_COLUMNS` 之前添加：

```python
def get_intraday_history(
    self,
    code: str,
    frequency: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """获取分钟级 K 线 — 子类可选实现

    Args:
        code: 股票代码（6位纯数字）
        frequency: "60"/"30"/"15"/"5"
        start_date: "2026-03-10"
        end_date: "2026-03-16"
    Returns:
        DataFrame: datetime, open, high, low, close, volume, amount[, pct_chg, turnover_rate]
    """
    raise NotImplementedError
```

- [ ] **Step 2: 验证语法**

Run: `cd engine && python -c "from data_engine.sources.base import BaseDataSource; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/sources/base.py
git commit -m "feat(data): BaseDataSource 新增 get_intraday_history 接口"
```

### Task 2: AKShareSource 实现 get_intraday_history

**Files:**
- Modify: `engine/data_engine/sources/akshare_source.py`

- [ ] **Step 1: 在 akshare_source.py 末尾（get_announcements 之后）添加方法**

```python
def get_intraday_history(
    self, code: str, frequency: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """
    获取分钟级 K 线数据
    底层接口: ak.stock_zh_a_hist_min_em()
    """
    logger.debug(f"[AKShare] 拉取 {code} {frequency}min {start_date} ~ {end_date}")

    df = self._fetch_with_retry(
        self._ak.stock_zh_a_hist_min_em,
        "stock_zh_a_hist_min_em",
        symbol=code,
        period=frequency,
        start_date=f"{start_date} 09:30:00",
        end_date=f"{end_date} 15:00:00",
        adjust="qfq",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    column_map = {
        "时间": "datetime",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_chg",
        "换手率": "turnover_rate",
    }
    df = df.rename(columns=column_map)
    df["datetime"] = pd.to_datetime(df["datetime"])

    available = [c for c in ["datetime", "open", "high", "low", "close",
                             "volume", "amount", "pct_chg", "turnover_rate"]
                 if c in df.columns]
    df = df[available].copy()

    # 类型标准化
    numeric_cols = [c for c in available if c != "datetime"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"[AKShare] {code} {frequency}min 获取成功: {len(df)} 条")
    return df
```

- [ ] **Step 2: 验证语法**

Run: `cd engine && python -c "from data_engine.sources.akshare_source import AKShareSource; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/sources/akshare_source.py
git commit -m "feat(data): AKShareSource 实现 get_intraday_history"
```

### Task 3: BaoStockSource 实现 get_intraday_history

**Files:**
- Modify: `engine/data_engine/sources/baostock_source.py`

- [ ] **Step 1: 在 baostock_source.py 的 get_financial_data 之后、__del__ 之前添加方法**

```python
def get_intraday_history(
    self, code: str, frequency: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """
    获取分钟级 K 线数据
    底层接口: bs.query_history_k_data_plus(frequency="60"/"30"/"15"/"5")
    注意: BaoStock 分钟线不含 pct_chg/turnover_rate
    """
    self._ensure_login()
    bs_code = self._to_bs_code(code)
    logger.debug(f"[BaoStock] 拉取 {bs_code} {frequency}min {start_date} ~ {end_date}")

    fields = "date,time,code,open,high,low,close,volume,amount"
    rs = self._bs.query_history_k_data_plus(
        bs_code,
        fields,
        start_date=start_date,
        end_date=end_date,
        frequency=frequency,
        adjustflag="2",  # 前复权
    )

    rows = []
    while (rs.error_code == "0") and rs.next():
        rows.append(rs.get_row_data())

    if not rows:
        logger.warning(f"[BaoStock] {bs_code} {frequency}min 无数据")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=rs.fields)

    # BaoStock time 格式: "20260316103000000" (YYYYMMDDHHMMSSmmm)
    # 直接从 time 字段前14位解析
    df["datetime"] = pd.to_datetime(
        df["time"].str[:14],
        format="%Y%m%d%H%M%S",
    )

    numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"[BaoStock] {bs_code} {frequency}min 获取成功: {len(df)} 条")
    return df[["datetime", "open", "high", "low", "close", "volume", "amount"]].copy()
```

- [ ] **Step 2: 验证语法**

Run: `cd engine && python -c "from data_engine.sources.baostock_source import BaoStockSource; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/sources/baostock_source.py
git commit -m "feat(data): BaoStockSource 实现 get_intraday_history"
```

---

## Chunk 2: 编排层 + 存储层

### Task 4: DataCollector 新增 get_intraday_history 编排

**Files:**
- Modify: `engine/data_engine/collector.py`

- [ ] **Step 1: 在 collector.py 的 get_announcements 方法之后、available_sources 之前添加**

```python
def get_intraday_history(
    self, code: str, frequency: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """获取分钟级 K 线 — 逐级降级"""
    for source in self._sources:
        try:
            df = source.get_intraday_history(code, frequency, start_date, end_date)
            if df is not None and len(df) > 0:
                logger.debug(
                    f"✅ {code} {frequency}min: {source.name} ({len(df)} 条)"
                )
                return df
        except NotImplementedError:
            continue
        except Exception as e:
            logger.warning(f"⚠️ {source.name} {code} {frequency}min 失败: {e}")

    logger.error(f"❌ {code} {frequency}min 所有数据源均失败")
    return pd.DataFrame()
```

- [ ] **Step 2: 验证语法**

Run: `cd engine && python -c "from data_engine.collector import DataCollector; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/collector.py
git commit -m "feat(data): DataCollector 新增 get_intraday_history 编排"
```

### Task 5: DuckDBStore 新增 stock_kline_60m 表和读写方法

**Files:**
- Modify: `engine/data_engine/store.py`

- [ ] **Step 1: 在 _init_tables() 中 cluster_results 建表之后、info schema 之前添加建表语句**

```python
# 分钟级 K 线表（按频率分表）
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

- [ ] **Step 2: 在 DuckDBStore 类中 get_stock_count 方法之前添加白名单和读写方法**

```python
# ── 分钟级 K 线 ──

# 频率 → 表名白名单，防止 SQL 注入
VALID_KLINE_TABLES: dict[str, str] = {"60m": "stock_kline_60m"}

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
    logger.debug(f"K线保存: {len(df)} 条 → {table}")

def get_kline(
    self, code: str, frequency: str,
    start_datetime: str = "", end_datetime: str = "",
) -> pd.DataFrame:
    """查询分钟级 K 线"""
    table = self._kline_table(frequency)
    query = f"SELECT * FROM {table} WHERE code = ?"
    params: list = [code]
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

- [ ] **Step 3: 验证语法**

Run: `cd engine && python -c "from data_engine.store import DuckDBStore; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add engine/data_engine/store.py
git commit -m "feat(data): DuckDBStore 新增 stock_kline_60m 表和读写方法"
```

---

## Chunk 3: 门面层 + 枚举

### Task 6: schemas.py 新增 KlineFrequency 枚举

**Files:**
- Modify: `engine/data_engine/schemas.py`

- [ ] **Step 1: 在 schemas.py 文件顶部 import 区域添加 Enum，在最后一个 class 之后添加枚举**

```python
from enum import Enum

class KlineFrequency(str, Enum):
    """K 线频率枚举 — 用于 REST API 参数校验和 store 白名单"""
    DAILY = "daily"
    MIN_60 = "60m"
    # 未来扩展:
    # MIN_15 = "15m"
    # MIN_5 = "5m"
```

- [ ] **Step 2: 验证语法**

Run: `cd engine && python -c "from data_engine.schemas import KlineFrequency; print(KlineFrequency.MIN_60.value)"`
Expected: 60m

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/schemas.py
git commit -m "feat(data): 新增 KlineFrequency 枚举"
```

### Task 7: DataEngine 新增 get_kline 门面方法

**Files:**
- Modify: `engine/data_engine/engine.py`

- [ ] **Step 1: 在 engine.py 的 get_daily_history_batch 方法之后添加 get_kline**

```python
# ── 分钟级 K 线 ──

def get_kline(
    self, code: str, frequency: str = "60m", days: int = 5
) -> pd.DataFrame:
    """
    通用 K 线查询 — 本地优先，缺失时远程拉取并缓存

    Args:
        code: 股票代码
        frequency: "60m"（当前仅支持）
        days: 回溯天数，默认 5
    """
    freq_key = frequency.replace("m", "")  # "60m" → "60"

    end = datetime.date.today()
    start = end - datetime.timedelta(days=days + 5)  # 多拉几天补偿非交易日

    # 1. 先查本地
    local = self._store.get_kline(
        code, frequency,
        start_datetime=start.isoformat(),
        end_datetime=end.isoformat() + " 23:59:59",
    )
    # 60min 约 4 条/交易日，但 days 包含周末/节假日
    # 用 days * 2 作为保守阈值，避免非交易日导致反复远程拉取
    if len(local) >= days * 2:
        return local

    # 2. 本地不足，远程拉取
    df = self._collector.get_intraday_history(
        code, freq_key, start.isoformat(), end.isoformat()
    )
    if df.empty:
        return local if not local.empty else pd.DataFrame()

    # 3. 缓存到 DuckDB
    df["code"] = code
    self._store.save_kline(df, frequency)

    return self._store.get_kline(
        code, frequency,
        start_datetime=start.isoformat(),
        end_datetime=end.isoformat() + " 23:59:59",
    )
```

- [ ] **Step 2: 验证语法**

Run: `cd engine && python -c "from data_engine.engine import DataEngine; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/engine.py
git commit -m "feat(data): DataEngine 新增 get_kline 门面方法"
```

---

## Chunk 4: REST API + 专家工具

### Task 8: routes.py 新增 /kline/{code} 端点

**Files:**
- Modify: `engine/data_engine/routes.py`

- [ ] **Step 1: 在 routes.py 顶部添加 import**

在现有 import 区域添加：
```python
from .schemas import KlineFrequency
```

- [ ] **Step 2: 在 get_daily 端点之后添加 kline 端点**

```python
@router.get("/kline/{code}")
async def get_kline(
    code: str,
    frequency: KlineFrequency = KlineFrequency.MIN_60,
    days: int = Query(5, description="回溯天数"),
):
    """获取分钟级 K 线数据"""
    if frequency == KlineFrequency.DAILY:
        raise HTTPException(
            status_code=400,
            detail="日线请使用 /daily/{code} 端点",
        )
    de = get_data_engine()
    df = await asyncio.to_thread(de.get_kline, code, frequency.value, days)
    if df.empty:
        return {"code": code, "frequency": frequency.value, "records": [], "count": 0}
    records = df.to_dict(orient="records")
    return {
        "code": code,
        "frequency": frequency.value,
        "records": records,
        "count": len(records),
    }
```

- [ ] **Step 3: 验证语法**

Run: `cd engine && python -c "from data_engine.routes import router; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add engine/data_engine/routes.py
git commit -m "feat(data): 新增 /api/v1/data/kline/{code} 端点"
```

### Task 9: engine_experts.py data/quant 专家新增 query_hourly 工具

**Files:**
- Modify: `engine/expert/engine_experts.py`

- [ ] **Step 1: 在 _get_available_tools_desc 的 data 工具描述中添加 query_hourly**

在 `data` 的工具描述字符串中 `run_screen` 之后添加一行：
```
- query_hourly(code: str, days: int): 查询个股小时线K线（60分钟级别），默认5个交易日
```

- [ ] **Step 2: 在 quant 的工具描述中也添加 query_hourly**

在 `quant` 的工具描述字符串中 `run_screen` 之后添加一行：
```
- query_hourly(code: str, days: int): 查询个股小时线K线（60分钟级别），默认5个交易日
```

- [ ] **Step 3: 在 _exec_data_tool 方法中 run_screen 分支之后添加 query_hourly 处理**

```python
elif action == "query_hourly":
    code = self._resolve_code(params.get("code", ""))
    days = int(params.get("days", 5))
    df = await asyncio.to_thread(de.get_kline, code, "60m", days)
    if df is None or df.empty:
        return json.dumps({"error": f"无 {code} 小时线数据"}, ensure_ascii=False)
    records = df.tail(20).to_dict("records")
    return json.dumps({"code": code, "frequency": "60m", "records": records,
                        "total_bars": len(df)},
                      ensure_ascii=False, default=str)
```

- [ ] **Step 4: 在 _exec_quant_tool 方法中 run_screen 分支之后添加 query_hourly 处理**

```python
elif action == "query_hourly":
    code = self._resolve_code(params.get("code", ""))
    days = int(params.get("days", 5))
    df = await asyncio.to_thread(de.get_kline, code, "60m", days)
    if df is None or df.empty:
        return json.dumps({"error": f"无 {code} 小时线数据"}, ensure_ascii=False)
    records = df.tail(20).to_dict("records")
    return json.dumps({"code": code, "frequency": "60m", "records": records,
                        "total_bars": len(df)},
                      ensure_ascii=False, default=str)
```

- [ ] **Step 5: 验证语法**

Run: `cd engine && python -c "from expert.engine_experts import EngineExpert; print('OK')"`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add engine/expert/engine_experts.py
git commit -m "feat(expert): data/quant 专家新增 query_hourly 工具"
```

---

## Chunk 5: 端到端验证

### Task 10: 启动后端并通过 REST API 验证

- [ ] **Step 1: 启动后端**

Run: `cd engine && python main.py` (后台运行)

- [ ] **Step 2: 验证 /kline 端点**

Run: `curl -s http://localhost:8000/api/v1/data/kline/600519?days=3 | python -m json.tool | head -30`
Expected: 返回 JSON，包含 code, frequency, records, count 字段

- [ ] **Step 3: 验证无效频率返回 422**

Run: `curl -s http://localhost:8000/api/v1/data/kline/600519?frequency=invalid`
Expected: HTTP 422 (FastAPI 枚举校验)

- [ ] **Step 4: 验证 daily 频率返回 400**

Run: `curl -s http://localhost:8000/api/v1/data/kline/600519?frequency=daily`
Expected: HTTP 400，detail 包含 "日线请使用 /daily/{code} 端点"

- [ ] **Step 5: 通过 MCP 工具验证专家可用**

使用 `mcp__stockterrain__query_history` 确认后端正常，然后手动测试 query_hourly 工具是否在专家工具描述中出现。

- [ ] **Step 6: 停止后端，最终 Commit**

```bash
git add -A
git commit -m "feat: 分钟级K线数据引擎扩展完成 — 60min支持"
```
