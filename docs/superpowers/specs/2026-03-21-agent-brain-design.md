# Phase 1B-2: Agent Brain — 设计规格

> **目标**：给 Main Agent 一个"大脑"，让它能全自主地分析市场、做出交易决策、在虚拟持仓上执行，用户可以查看完整的思考过程。
> 纯模拟环境，Agent 全自主运行，不涉及实际交易。

---

## 1. 架构概览

```
定时触发（每日收盘后 15:30）
    │
    ▼
Agent Brain
├── 1. 标的筛选
│   ├── 关注列表（watchlist 表）
│   └── 量化筛选（QuantEngine 因子打分 top N）
│
├── 2. 逐标的分析（调用现有专家引擎工具层）
│   ├── 行情数据（日K、涨跌幅）
│   ├── 技术指标（MACD、RSI、布林带等）
│   ├── 因子评分
│   ├── 新闻情感（最近3天）
│   └── (可选) 辩论引擎 → 深度分析
│
├── 3. LLM 综合决策
│   ├── 输入：分析结果 + 当前持仓 + 账户状态
│   ├── 输出：结构化决策 JSON
│   └── 每个 buy/sell 决策 → 生成 trade_plan
│
└── 4. 自动执行
    ├── trade_plan → execute_trade（复用 Phase 1A）
    └── 记录到 brain_runs
```

**新增/修改点**：
- 后端：`brain.py`（核心决策）、`watchlist.py`（关注列表）、`scheduler.py`（定时调度）
- 后端：`watchlist` 表 + `brain_runs` 表 + `brain_config` 表
- 后端：watchlist + brain_runs CRUD API
- 前端：`/agent` 页面（运行记录 + 思考过程展示）

---

## 2. 数据模型

### 2.1 watchlist 表

```sql
CREATE TABLE IF NOT EXISTS agent.watchlist (
    id VARCHAR PRIMARY KEY,
    stock_code VARCHAR NOT NULL,
    stock_name VARCHAR NOT NULL,
    reason TEXT,
    added_by VARCHAR DEFAULT 'manual',  -- manual/agent
    created_at TIMESTAMP DEFAULT now()
);
```

### 2.2 brain_runs 表

```sql
CREATE TABLE IF NOT EXISTS agent.brain_runs (
    id VARCHAR PRIMARY KEY,
    portfolio_id VARCHAR NOT NULL,
    run_type VARCHAR DEFAULT 'scheduled',  -- scheduled/manual
    status VARCHAR DEFAULT 'running',      -- running/completed/failed
    candidates JSON,          -- 筛选出的候选标的列表
    analysis_results JSON,    -- 各专家分析摘要
    decisions JSON,           -- 最终决策列表
    plan_ids JSON,            -- 生成的 trade_plan IDs
    trade_ids JSON,           -- 执行的 trade IDs
    error_message TEXT,       -- 失败时的错误信息
    llm_tokens_used INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP
);
```

### 2.3 brain_config 表

```sql
CREATE TABLE IF NOT EXISTS agent.brain_config (
    id VARCHAR PRIMARY KEY DEFAULT 'default',
    enable_debate BOOLEAN DEFAULT false,
    max_candidates INTEGER DEFAULT 30,
    quant_top_n INTEGER DEFAULT 20,
    max_position_count INTEGER DEFAULT 10,
    single_position_pct DOUBLE DEFAULT 0.15,
    schedule_time VARCHAR DEFAULT '15:30',
    updated_at TIMESTAMP DEFAULT now()
);
```

### 2.4 Pydantic 模型

```python
class WatchlistItem(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    reason: str | None = None
    added_by: Literal["manual", "agent"] = "manual"
    created_at: str

class WatchlistInput(BaseModel):
    stock_code: str
    stock_name: str
    reason: str | None = None

class BrainRun(BaseModel):
    id: str
    portfolio_id: str
    run_type: Literal["scheduled", "manual"] = "scheduled"
    status: Literal["running", "completed", "failed"] = "running"
    candidates: list[dict] | None = None
    analysis_results: list[dict] | None = None
    decisions: list[dict] | None = None
    plan_ids: list[str] | None = None
    trade_ids: list[str] | None = None
    error_message: str | None = None
    llm_tokens_used: int = 0
    started_at: str
    completed_at: str | None = None

class BrainConfig(BaseModel):
    enable_debate: bool = False
    max_candidates: int = 30
    quant_top_n: int = 20
    max_position_count: int = 10
    single_position_pct: float = 0.15
    schedule_time: str = "15:30"
```

复用现有表：`trade_plans`（source_type="agent"）、`trades`（triggered_by="agent"）。

---

## 3. Agent Brain 决策流程

### 3.1 Step 1: 标的筛选

```python
async def _select_candidates(self) -> list[dict]:
    # 1. 关注列表
    watchlist = await self.db.execute_read("SELECT * FROM agent.watchlist")

    # 2. 量化筛选 — 调用 QuantEngine
    quant_top = await self._quant_screen(top_n=config.quant_top_n)

    # 3. 已有持仓（必须分析）
    positions = await self.service.get_positions(portfolio_id, "open")

    # 4. 合并去重，限制总数
    candidates = merge_and_dedup(watchlist, quant_top, positions)
    return candidates[:config.max_candidates]
```

### 3.2 Step 2: 逐标的分析

对每个候选标的，直接调用专家引擎的工具层（`engine/expert/tools.py`），不走完整对话：

```python
async def _analyze_candidate(self, code: str) -> dict:
    results = {}

    # 行情数据
    results["daily"] = await tools.execute("data", "get_daily", {"code": code, "days": 60})

    # 技术指标
    results["indicators"] = await tools.execute("quant", "get_indicators", {"code": code})

    # 因子评分
    results["factor_score"] = await tools.execute("quant", "get_factor_score", {"code": code})

    # 新闻情感
    results["news"] = await tools.execute("info", "get_news_sentiment", {"code": code, "days": 3})

    # (可选) 辩论
    if config.enable_debate:
        results["debate"] = await self._run_debate(code)

    return results
```

### 3.3 Step 3: LLM 综合决策

将所有分析结果 + 持仓状态喂给 LLM，要求输出结构化 JSON：

```python
async def _make_decisions(self, candidates_analysis: list, portfolio: dict) -> list[dict]:
    prompt = f"""你是一个专业的 A 股投资 Agent，基于以下分析数据做出交易决策。

当前账户状态：
- 现金余额：{portfolio['cash_balance']}
- 总资产：{portfolio['total_asset']}
- 当前持仓：{format_positions(portfolio['positions'])}

候选标的分析：
{format_analysis(candidates_analysis)}

请对每个标的给出决策，输出 JSON 数组：
[
  {{
    "stock_code": "600519",
    "stock_name": "贵州茅台",
    "action": "buy",          // buy/sell/add/reduce/hold/ignore
    "price": 1750.0,          // 目标价格
    "quantity": 100,           // 数量（100的整数倍）
    "holding_type": "mid_term", // long_term/mid_term/short_term
    "reasoning": "...",        // 决策理由
    "take_profit": 2100.0,     // 止盈价
    "stop_loss": 1650.0,       // 止损价
    "confidence": 0.8          // 信心度 0-1
  }}
]

规则：
1. 单只股票仓位不超过总资产的 {config.single_position_pct*100}%
2. 同时持仓不超过 {config.max_position_count} 只
3. 只输出 action 不是 hold/ignore 的标的
4. quantity 必须是 100 的整数倍
5. 必须设置止盈和止损价格
"""

    # 使用流式收集模式
    response = await llm_collect(prompt)
    decisions = parse_json(response)
    return decisions
```

### 3.4 Step 4: 自动执行

```python
async def _execute_decisions(self, decisions: list[dict]) -> tuple[list[str], list[str]]:
    plan_ids = []
    trade_ids = []

    for d in decisions:
        if d["action"] in ("hold", "ignore"):
            continue

        # 1. 生成 trade_plan
        plan = await self.service.create_plan(TradePlanInput(
            stock_code=d["stock_code"],
            stock_name=d["stock_name"],
            direction="buy" if d["action"] in ("buy", "add") else "sell",
            entry_price=d["price"],
            position_pct=d.get("position_pct"),
            take_profit=d.get("take_profit"),
            stop_loss=d.get("stop_loss"),
            reasoning=d["reasoning"],
            source_type="agent",
        ))
        plan_ids.append(plan["id"])

        # 2. 执行交易
        trade_result = await self.service.execute_trade(
            portfolio_id, TradeInput(...), trade_date
        )
        trade_ids.append(trade_result["trade"]["id"])

        # 3. 更新 plan 状态
        await self.service.update_plan(plan["id"], {"status": "executing"})

    return plan_ids, trade_ids
```

---

## 4. API 端点

### 4.1 Watchlist API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/agent/watchlist` | 添加关注 |
| GET | `/api/v1/agent/watchlist` | 关注列表 |
| DELETE | `/api/v1/agent/watchlist/{id}` | 取消关注 |

### 4.2 Brain API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/agent/brain/run` | 手动触发一次运行 |
| GET | `/api/v1/agent/brain/runs` | 运行记录列表 |
| GET | `/api/v1/agent/brain/runs/{id}` | 单次运行详情 |
| GET | `/api/v1/agent/brain/config` | 获取配置 |
| PATCH | `/api/v1/agent/brain/config` | 更新配置 |

---

## 5. 定时调度

复用 APScheduler（专家引擎已在用），在 `main.py` startup 中注册：

```python
# 每个交易日 15:30 运行
scheduler.add_job(brain.run, CronTrigger(hour=15, minute=30),
                  id="agent_brain_daily")
```

需要判断是否为交易日（排除周末和节假日）。

---

## 6. 前端：/agent 页面

### 6.1 路由与导航

- 路由：`/agent`
- 导航栏新增：🤖 Agent

### 6.2 页面布局

```
/agent 页面
├── 顶部状态栏
│   ├── Agent 状态（运行中/空闲）
│   ├── 上次运行时间
│   ├── 持仓概览（总资产、现金、盈亏）
│   └── 手动运行按钮
│
├── 左侧：运行记录列表
│   ├── 时间
│   ├── 状态标签（running/completed/failed）
│   └── 决策数量摘要
│
└── 右侧：选中运行的详情
    ├── 候选标的（来源标注：watchlist/quant/position）
    ├── 分析摘要（每个标的的关键指标）
    ├── 决策列表（action + 理由 + 信心度）
    └── 执行结果（成交价、费用、持仓变化）
```

### 6.3 关注列表管理

在 /agent 页面底部或侧边加一个关注列表面板：
- 显示当前关注的股票
- 支持添加/删除
- 显示添加来源（手动/Agent自动发现）

---

## 7. 与现有系统的集成

- **AgentDB**：复用单例，`_init_tables()` 新增 3 张表
- **AgentService**：新增 watchlist CRUD + brain_runs CRUD
- **QuantEngine**：调用因子打分做全市场筛选
- **Expert Tools**：直接调用 `tools.py` 获取行情/指标/新闻数据
- **辩论引擎**：可选，通过开关控制
- **trade_plans**：复用 1B-1 的表，source_type="agent"
- **execute_trade**：复用 Phase 1A 的交易执行

---

## 8. 不在 Phase 1B-2 范围内

| 内容 | 推迟到 | 理由 |
|------|--------|------|
| 盘中实时决策 | 数据源升级后 | 需要实时行情数据 |
| 自动复盘 | Phase 1D | 需要复盘系统 |
| Agent 专用辩论人格 | 后续 | 当前辩论人格面向用户展示 |
| 多 Agent 协作 | Phase 3 | 当前单 Agent |
| 配置前端页面 | 后续 | 先硬编码默认值 |
| 交易日历（节假日） | 后续 | 先用简单的周末判断 |
