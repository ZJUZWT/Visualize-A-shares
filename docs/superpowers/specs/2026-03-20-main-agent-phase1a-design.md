# Main Agent Phase 1A — 数据层设计规格

> **目标**：为 Main Agent 构建数据地基，让 AI 能"持仓和交易"。
> 纯后端数据层 + CRUD API，不涉及 LLM 调用、前端页面、自动运行。

---

## 1. 架构概览

```
backend/engine/agent/          ← 新建目录
├── __init__.py
├── db.py                      ← AgentDB 单例（独立 DuckDB + 写锁）
├── models.py                  ← Pydantic 数据模型
├── validator.py               ← TradeValidator（A股交易规则校验）
├── service.py                 ← 业务逻辑层（建仓/交易/持仓计算）
└── routes.py                  ← FastAPI 路由（6 个 API 端点）
```

**关键决策**：
- 独立数据库文件 `data/agent.duckdb`，不与 `stockterrain.duckdb` / `expert_chat.duckdb` 共用
- AgentDB 单例持有长连接 + `asyncio.Lock` 序列化写操作
- 所有多表写操作用 DuckDB 事务包裹

---

## 2. 数据模型

### 2.1 Position（持仓）

```python
class Position(BaseModel):
    id: str                                     # UUID
    stock_code: str                             # "600519"
    stock_name: str                             # "贵州茅台"
    direction: Literal["long"] = "long"         # 虚拟盘只做多
    holding_type: Literal[
        "long_term",     # 长线（周期数月~数年）
        "mid_term",      # 中线（周期数周~数月）
        "short_term",    # 短线（周期数天）
    ]
    entry_price: float                          # 建仓均价
    current_qty: int                            # 当前持有数量
    cost_basis: float                           # 总成本（含手续费）
    entry_date: str                             # 建仓日期 YYYY-MM-DD
    entry_reason: str                           # 买入理由（AI 生成）
    status: Literal["open", "closed"] = "open"
    closed_at: str | None = None
    closed_reason: str | None = None
    created_at: str                             # ISO timestamp
```

**说明**：
- `direction` 固定为 `long`，虚拟盘不支持做空
- 去掉 `day_trade` 类型 — 做T是日内临时决策，通过 Trade 理由链表达，不是持仓属性
- `entry_price` 在加仓时自动重算为加权均价

### 2.2 PositionStrategy（操作策略）

```python
class PositionStrategy(BaseModel):
    id: str
    position_id: str
    holding_type: str                           # 冗余，方便查询

    # ── 通用字段 ──
    take_profit: float | None = None            # 止盈价
    stop_loss: float | None = None              # 止损价
    reasoning: str                              # 完整策略推理
    version: int = 1                            # 策略版本号（每次修改+1）
    created_at: str
    updated_at: str

    # ── 类型特有字段（JSON）──
    details: dict = {}
    # long_term 示例: {"fundamental_anchor": "硅料产能出清", "exit_condition": "行业景气见顶", "rebalance_trigger": "季报低于预期减仓1/3"}
    # mid_term 示例:  {"trend_indicator": "20日均线", "add_position_price": 45.0, "target_catalyst": "Q2业绩超预期"}
    # short_term 示例: {"hold_days": 3, "next_day_plan": "高开3%以上减半", "volume_condition": "缩量则离场"}
```

**说明**：
- 通用字段（止盈/止损/reasoning）直接存列，方便查询和展示
- 类型特有字段存 `details` JSON 列，灵活扩展，不改表结构
- `version` 每次 AI 修改策略自增，保留演化轨迹

### 2.3 Trade（交易记录）

```python
class Trade(BaseModel):
    id: str
    position_id: str                             # buy 时由 service 层创建 Position 后回填
    action: Literal["buy", "sell", "add", "reduce"]
    stock_code: str
    stock_name: str
    price: float                                # 成交价（含滑点估算）
    quantity: int                               # 成交数量（100的整数倍）
    amount: float                               # price × quantity

    # ── 理由链（全部必填）──
    reason: str                                 # 一句话理由
    thesis: str                                 # 交易论点（"为什么现在做这个操作"）
    data_basis: list[str]                       # 数据依据
    risk_note: str                              # 风险提示
    invalidation: str                           # 什么情况证明这笔操作是错的

    triggered_by: Literal["manual", "agent"] = "agent"
    created_at: str

    # ── 事后回填（复盘时填写，Phase 1B+）──
    review_result: str | None = None            # correct/wrong/too_early/too_late/pending
    review_note: str | None = None
    review_date: str | None = None
    pnl_at_review: float | None = None
```

**说明**：
- 去掉 `t_buy` / `t_sell` — 做T就是普通买卖，AI 在 `thesis` 里写意图即可
- 理由链全部 NOT NULL，AI 不写清楚就不允许下单
- `review_*` 字段 Phase 1A 建表时预留，Phase 1D 复盘时使用

### 2.4 TradeGroup（操作组）

```python
class TradeGroup(BaseModel):
    id: str
    position_id: str | None = None              # rebalance 组跨多个持仓时为 None
    group_type: Literal[
        "build_position",       # 建仓组（可能分多天完成）
        "reduce_position",      # 减仓组
        "close_position",       # 清仓组
        "day_trade_session",    # 当天同票有买有卖 → 事后归类为做T
        "rebalance",            # 调仓组（减A加B，跨持仓）
    ]
    trade_ids: list[str]                        # 包含的交易 ID（JSON array）
    position_ids: list[str] = []                # rebalance 时涉及的多个持仓 ID
    thesis: str                                 # 这组操作的整体论点
    planned_duration: str | None = None         # 预计执行周期
    status: Literal["executing", "completed", "abandoned"] = "executing"
    started_at: str
    completed_at: str | None = None

    # ── 延迟评价 ──
    review_eligible_after: str | None = None    # 最早可评价日期
    review_result: str | None = None            # correct/wrong/neutral
    review_note: str | None = None
    actual_pnl_pct: float | None = None
    created_at: str
```

**评价时机规则**：

| 操作类型 | 评价等待期 | 理由 |
|---------|-----------|------|
| build_position | 完成后 +5 交易日 | 建仓完成后需要时间验证方向 |
| reduce/close | 完成后 +3 交易日 | 看卖出后走势是否证明决策正确 |
| day_trade_session | 当天收盘即可 | 日内操作当天就有结果 |
| rebalance | 完成后 +5 交易日 | 看新旧持仓相对表现 |

### 2.5 虚拟账户

不单独建表，用一条配置记录表示：

```python
class Portfolio(BaseModel):
    """虚拟账户 — 持仓市值实时计算，现金余额事务性维护"""
    initial_capital: float          # 初始资金（固定，不可追加）
    cash_balance: float             # 当前现金（每笔交易事务性更新）
    total_asset: float              # 总资产 = cash_balance + 持仓市值
    total_pnl: float                # 总盈亏
    total_pnl_pct: float            # 总收益率
    positions: list[Position]       # 当前持仓
    created_at: str                 # 账户诞生日（成长时间线起点）
```

```sql
CREATE TABLE agent.portfolio_config (
    id VARCHAR PRIMARY KEY DEFAULT 'default',
    initial_capital DOUBLE NOT NULL,
    cash_balance DOUBLE NOT NULL,           -- 当前现金余额（每笔交易事务性更新）
    created_at TIMESTAMP DEFAULT now()
);
-- cash_balance 在每笔交易时事务性更新，避免每次 get_portfolio 全表扫描 trades。
-- 初始化时 cash_balance = initial_capital。
```

---

## 3. DuckDB 表设计

数据库文件：`data/agent.duckdb`

```sql
-- 创建 schema
CREATE SCHEMA IF NOT EXISTS agent;

-- 虚拟账户配置
CREATE TABLE agent.portfolio_config (
    id VARCHAR PRIMARY KEY DEFAULT 'default',
    initial_capital DOUBLE NOT NULL,
    cash_balance DOUBLE NOT NULL,               -- 每笔交易事务性更新
    created_at TIMESTAMP DEFAULT now()
);

-- 持仓
CREATE TABLE agent.positions (
    id VARCHAR PRIMARY KEY,
    stock_code VARCHAR NOT NULL,
    stock_name VARCHAR NOT NULL,
    direction VARCHAR DEFAULT 'long',
    holding_type VARCHAR NOT NULL,          -- long_term/mid_term/short_term
    entry_price DOUBLE NOT NULL,
    current_qty INTEGER NOT NULL,
    cost_basis DOUBLE NOT NULL,
    entry_date DATE NOT NULL,
    entry_reason TEXT NOT NULL,
    status VARCHAR DEFAULT 'open',          -- open/closed
    closed_at TIMESTAMP,
    closed_reason TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- 操作策略
CREATE TABLE agent.position_strategies (
    id VARCHAR PRIMARY KEY,
    position_id VARCHAR NOT NULL,
    holding_type VARCHAR NOT NULL,
    take_profit DOUBLE,
    stop_loss DOUBLE,
    reasoning TEXT NOT NULL,
    details JSON,                           -- 类型特有字段
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- 交易记录
CREATE TABLE agent.trades (
    id VARCHAR PRIMARY KEY,
    position_id VARCHAR NOT NULL,
    action VARCHAR NOT NULL,                -- buy/sell/add/reduce
    stock_code VARCHAR NOT NULL,
    stock_name VARCHAR NOT NULL,
    price DOUBLE NOT NULL,
    quantity INTEGER NOT NULL,
    amount DOUBLE NOT NULL,
    -- 理由链
    reason TEXT NOT NULL,
    thesis TEXT NOT NULL,
    data_basis JSON NOT NULL,               -- ["依据1", "依据2"]
    risk_note TEXT NOT NULL,
    invalidation TEXT NOT NULL,
    triggered_by VARCHAR DEFAULT 'agent',
    -- 事后回填
    review_result VARCHAR,
    review_note TEXT,
    review_date TIMESTAMP,
    pnl_at_review DOUBLE,
    created_at TIMESTAMP DEFAULT now()
);

-- 操作组
CREATE TABLE agent.trade_groups (
    id VARCHAR PRIMARY KEY,
    position_id VARCHAR,                       -- rebalance 组跨持仓时为 NULL
    group_type VARCHAR NOT NULL,
    trade_ids JSON NOT NULL,                -- ["trade_id_1", "trade_id_2"]
    position_ids JSON,                      -- rebalance 时涉及的多个持仓 ID
    thesis TEXT NOT NULL,
    planned_duration VARCHAR,
    status VARCHAR DEFAULT 'executing',     -- executing/completed/abandoned
    started_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP,
    review_eligible_after DATE,
    review_result VARCHAR,
    review_note TEXT,
    actual_pnl_pct DOUBLE,
    created_at TIMESTAMP DEFAULT now()
);

-- LLM 调用记录
CREATE TABLE agent.llm_calls (
    id VARCHAR PRIMARY KEY,
    caller VARCHAR NOT NULL,                -- agent_chat/wake_check/daily_review/...
    model VARCHAR,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TIMESTAMP DEFAULT now()
);
```

---

## 4. AgentDB 单例设计

```python
class AgentDB:
    """Main Agent 数据库 — 单例长连接 + 写锁"""

    _instance: "AgentDB | None" = None
    _conn: duckdb.DuckDBPyConnection
    _write_lock: asyncio.Lock

    @classmethod
    def get_instance(cls) -> "AgentDB":
        """获取单例。必须在 app startup 中调用 init_instance() 初始化。"""
        if cls._instance is None:
            raise RuntimeError("AgentDB not initialized. Call init_instance() first.")
        return cls._instance

    @classmethod
    def init_instance(cls) -> "AgentDB":
        """在 app startup 中调用一次，避免并发初始化竞态。"""
        if cls._instance is not None:
            return cls._instance
        cls._instance = cls.__new__(cls)
        cls._instance._conn = duckdb.connect(str(AGENT_DB_PATH))
        cls._instance._write_lock = asyncio.Lock()
        cls._instance._init_tables()
        return cls._instance

    def _init_tables(self):
        """建表（幂等，启动时调用）"""
        # 执行 CREATE TABLE IF NOT EXISTS ...

    async def execute_read(self, sql: str, params=None) -> list[dict]:
        """读操作，不加锁。用 to_thread 避免阻塞事件循环。"""
        return await asyncio.to_thread(self._sync_read, sql, params)

    def _sync_read(self, sql: str, params=None) -> list[dict]:
        result = self._conn.execute(sql, params).fetchdf()
        return result.to_dict("records")

    async def execute_write(self, sql: str, params=None):
        """单条写操作，加锁 + to_thread。"""
        async with self._write_lock:
            await asyncio.to_thread(self._conn.execute, sql, params)

    async def execute_transaction(self, queries: list[tuple[str, list]]):
        """事务性执行多条写 SQL"""
        async with self._write_lock:
            await asyncio.to_thread(self._sync_transaction, queries)

    def _sync_transaction(self, queries: list[tuple[str, list]]):
        self._conn.begin()
        try:
            for sql, params in queries:
                self._conn.execute(sql, params)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self):
        """关闭连接（app shutdown 时调用）"""
        self._conn.execute("CHECKPOINT")
        self._conn.close()
```

**注意事项**：
- `init_instance()` 在 `main.py` 的 `@app.on_event("startup")` 中调用一次，避免并发初始化竞态
- 所有 DuckDB 同步操作通过 `asyncio.to_thread()` 包装，避免阻塞 FastAPI 事件循环
- `_write_lock` 序列化写操作，DuckDB 单写者模型下必须

---

## 5. TradeValidator — A股交易规则校验

```python
class TradeValidator:
    """虚拟盘交易规则校验"""

    # 允许交易的股票代码前缀（沪深主板）
    ALLOWED_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")

    # 禁止交易的代码前缀
    BLOCKED_PREFIXES = (
        "300",   # 创业板
        "301",   # 创业板
        "688",   # 科创板
        "689",   # 科创板
        "8",     # 北交所
        "4",     # 北交所/三板
    )

    def validate(self, trade, position, portfolio_cash, market_data) -> tuple[bool, str]:
        """
        校验交易是否合法，返回 (通过, 原因)

        校验规则：
        1. 股票代码白名单 — 只允许沪深主板
        2. ST 检查 — 股票名称含 ST/*ST 则拒绝
        3. T+1 检查 — sell/reduce 时，持仓必须是昨天或更早买入的
        4. 涨跌停检查 — 涨停不能买入，跌停不能卖出
        5. 最小交易单位 — 数量必须是 100 的整数倍
        6. 资金充足检查 — buy/add 时 portfolio_cash >= price × quantity
        7. 持仓充足检查 — sell/reduce 时 position.current_qty >= quantity
        8. 滑点估算 — 买入价 = 现价 × 1.002，卖出价 = 现价 × 0.998
        """
```

**滑点模型**：
- 买入：实际成交价 = 委托价 × (1 + 0.2%)
- 卖出：实际成交价 = 委托价 × (1 - 0.2%)
- 简单固定比例，Phase 1D 可升级为基于成交量的动态滑点

**手续费模型**：
- 佣金：万2.5（买卖双向）
- 印花税：千1（仅卖出）
- 过户费：十万分之1（仅沪市）
- 最低佣金：5元

---

## 6. Service 层 — 业务逻辑

```python
class AgentService:
    """Main Agent 业务逻辑"""

    def __init__(self, db: AgentDB, validator: TradeValidator):
        self.db = db
        self.validator = validator

    async def init_portfolio(self, initial_capital: float) -> dict:
        """初始化虚拟账户（只能调用一次）"""

    async def get_portfolio(self) -> dict:
        """
        获取当前持仓概览
        - 从 portfolio_config 读取 cash_balance（已事务性维护）
        - 从 positions 表读取 open 持仓
        - 调用 DataEngine 获取最新价格计算持仓市值
        - total_asset = cash_balance + 持仓市值
        - 返回 Portfolio 结构
        """

    async def get_positions(self) -> list[dict]:
        """持仓列表（含策略详情）"""

    async def get_position(self, position_id: str) -> dict:
        """单个持仓详情"""

    async def get_trades(self, position_id: str = None, limit: int = 50) -> list[dict]:
        """交易记录（可按持仓过滤）"""

    async def execute_trade(self, trade_input: TradeInput) -> dict:
        """
        执行交易 — 核心方法

        流程：
        1. 通过 DataEngine.get_profiles() 解析 stock_code → stock_name（缓存命中）
        2. TradeValidator.validate() 校验
        3. 计算实际成交价（含滑点）和手续费
        4. 事务性写入（单个事务，保证原子性）：
           a. buy 操作：先 INSERT positions → 拿到 position_id → INSERT trades
           b. add 操作：UPDATE positions（重算均价和数量）→ INSERT trades
           c. sell/reduce 操作：UPDATE positions（减少数量）→ INSERT trades
           d. sell 且 current_qty == 0：UPDATE positions status='closed'
           e. 归入 TradeGroup（匹配现有 executing 组或创建新组）
        5. 返回交易结果（含实际成交价、手续费、更新后的持仓状态）
        """

    async def create_strategy(self, position_id: str, strategy_input: dict) -> dict:
        """
        为持仓创建/更新操作策略

        - buy 建仓时可选调用（AI 建仓后生成策略）
        - 更新时 version 自增，保留历史版本
        - Phase 1A 通过 API 手动创建，Phase 1B 由 Agent 自动生成
        """
```

**TradeInput**（API 入参）：

```python
class TradeInput(BaseModel):
    action: Literal["buy", "sell", "add", "reduce"]
    stock_code: str
    price: float                    # 委托价
    quantity: int                   # 委托数量
    holding_type: Literal["long_term", "mid_term", "short_term"] | None = None  # buy 时必填
    # 理由链
    reason: str
    thesis: str
    data_basis: list[str]
    risk_note: str
    invalidation: str
    triggered_by: Literal["manual", "agent"] = "agent"
```

---

## 7. API 端点

注册路径：`/api/v1/agent/*`，在 `backend/main.py` 中挂载。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agent/portfolio/init` | 初始化虚拟账户，body: `{initial_capital: float}` |
| GET | `/agent/portfolio` | 当前持仓概览（持仓 + 现金 + 总资产 + 盈亏） |
| GET | `/agent/positions` | 持仓列表（含策略），支持 `?status=open\|closed` |
| GET | `/agent/positions/{id}` | 单个持仓详情（含策略 + 关联交易） |
| GET | `/agent/trades` | 交易记录，支持 `?position_id=xxx&limit=50` |
| POST | `/agent/trades` | 录入交易，body: TradeInput |
| POST | `/agent/positions/{id}/strategy` | 创建/更新持仓策略 |
| GET | `/agent/positions/{id}/strategy` | 查看持仓策略（含历史版本） |

**错误响应**：
- 400: 校验失败（TradeValidator 拒绝，附原因）
- 404: 持仓不存在
- 409: 账户已初始化（重复 init）

---

## 8. 与现有系统的集成

- **DataEngine**：`get_portfolio()` 调用 `DataEngine.get_realtime_quotes()` 获取最新价格计算持仓市值。TradeValidator 调用同一接口获取涨跌停状态。
- **config.py**：新增 `AGENT_DB_PATH = DATA_DIR / "agent.duckdb"` 常量
- **main.py**：startup 时初始化 AgentDB，shutdown 时关闭连接。挂载 agent routes。
- **不依赖**：LLM、ExpertAgent、ScheduledTaskManager — 这些是 Phase 1B+ 的事

---

## 9. 不在 Phase 1A 范围内

以下内容明确推迟：

| 内容 | 推迟到 | 理由 |
|------|--------|------|
| strategy_snapshots 表 | Phase 1B | 需要 Agent 对话才有内容 |
| decision_logs 表 | Phase 1C | 需要自动运行才有内容 |
| daily_reviews / weekly_reflections 表 | Phase 1D | 复盘系统 |
| watch_signals / info_digests 表 | Phase 1C | 信号监控 + 信息免疫 |
| TokenBudgetManager | Phase 1B | 无 LLM 调用，先记录 llm_calls 积累数据 |
| 前端 /agent 页面 | Phase 1B | 数据层先行 |
| Agent Chat / SSE | Phase 1B | 需要 LLM |
| 自动运行 / APScheduler | Phase 1C | 需要 Agent Brain |
| 产业链认知层 | Phase 1C | 需要 IndustryEngine 接驳 |
| 回测模式 | Phase 1D | 需要完整 Agent |
