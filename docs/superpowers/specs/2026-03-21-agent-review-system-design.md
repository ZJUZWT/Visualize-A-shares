# Agent 复盘系统设计规格

## 目标

为 Agent Brain 构建完整的复盘闭环：事后对账（收益归因、胜率统计）、思维回放（完整决策过程展示）、自我进化（结构化经验规则库，自动积累和淘汰）。

## 需求清单

1. 每日自动对账：对比历史决策 vs 实际市场走势，计算收益率、胜率
2. 思维回放：存储并展示 Agent 决策时的完整思维链
3. 经验规则库：Agent 自动提炼结构化规则，规则有置信度和生命周期
4. 规则注入：AgentBrain 决策前自动读取有效规则作为参考
5. 每周深度总结：周度统计 + 规则提炼/淘汰
6. 前端展示：复盘记录、经验规则、思维回放

## 架构

```
AgentBrain (决策时读取 memories)
    ↓ 运行完毕
ReviewEngine (独立引擎)
    ├── DailyReview  — 每日 15:45，对账 T-1~T-5 决策 vs 实际走势
    ├── WeeklyReview — 每周五 16:00，周度统计 + 规则提炼/淘汰
    └── MemoryManager — 管理 agent_memories 规则库
        ├── 写入新规则（LLM 提炼）
        ├── 淘汰失效规则（置信度过低 → retired）
        └── 读取有效规则（AgentBrain 决策前调用）
```

ReviewEngine 与 AgentBrain 解耦，通过数据库共享数据（brain_runs、review_records、agent_memories）。

## 数据模型

所有表在 `agent` schema 下（与现有 `agent.positions`、`agent.brain_runs` 等一致）。

### agent.review_records 表（新增）

```sql
CREATE TABLE IF NOT EXISTS agent.review_records (
    id VARCHAR PRIMARY KEY,
    brain_run_id VARCHAR,
    trade_id VARCHAR,              -- 关联 agent.trades 表，唯一定位到具体交易
    stock_code VARCHAR,
    stock_name VARCHAR,
    action VARCHAR,
    decision_price DOUBLE,         -- 取自 agent.trades.price（实际成交价）
    review_price DOUBLE,           -- 复盘时从 DuckDB 快照读取的当前市价
    pnl_pct DOUBLE,
    holding_days INTEGER,
    status VARCHAR,
    review_date DATE,
    review_type VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trade_id, review_date) -- 幂等：同一笔交易同一天不重复复盘
)
```

- `action`: buy/sell/add/reduce
- `decision_price`: 取自 `agent.trades.price`（实际成交价，含滑点），不是 LLM 决策时的目标价
- `review_price`: 复盘时从 DuckDB 快照读取的最新收盘价
- `pnl_pct`: (review_price - decision_price) / decision_price（买入方向）；卖出方向取反
- `status`: win (pnl_pct > 0) / loss (pnl_pct < 0) / holding（仍在持仓）
- `review_type`: daily / weekly
- 幂等保证：`UNIQUE (trade_id, review_date)` 约束，同一笔交易同一天重跑不会产生重复记录（INSERT OR IGNORE）

### agent.weekly_summaries 表（新增）

```sql
CREATE TABLE IF NOT EXISTS agent.weekly_summaries (
    id VARCHAR PRIMARY KEY,
    week_start DATE,               -- 本周一日期
    week_end DATE,                 -- 本周五日期
    total_trades INTEGER,
    win_count INTEGER,
    loss_count INTEGER,
    win_rate DOUBLE,
    total_pnl_pct DOUBLE,
    best_trade_id VARCHAR,
    worst_trade_id VARCHAR,
    insights TEXT,                  -- LLM 生成的周报摘要
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (week_start)
)
```

周报摘要独立存表，不挂在 review_records 上，避免数据冗余。

### agent.agent_memories 表（新增）

```sql
CREATE TABLE IF NOT EXISTS agent.agent_memories (
    id VARCHAR PRIMARY KEY,
    rule_text VARCHAR,
    category VARCHAR,
    source_run_id VARCHAR,
    status VARCHAR DEFAULT 'active',
    confidence DOUBLE DEFAULT 0.5,
    verify_count INTEGER DEFAULT 0,
    verify_win INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retired_at TIMESTAMP
)
```

- `category`: timing / risk / sector / position 等分类
- `status` 状态机：
  - `active` — 有效规则，会被注入决策 prompt
  - `retired` — 已淘汰，不再使用
  - 只有两个状态，没有 `inactive` 中间态。LLM 主动淘汰和自动淘汰都直接走 `retired`。
- `confidence`: 每次更新 `verify_count` / `verify_win` 后立即重算 `confidence = verify_win / verify_count` 并写入 DB
- 自动淘汰规则：`confidence < 0.3` 且 `verify_count >= 5` → 自动设 `status=retired, retired_at=now`

### agent.brain_runs 表扩展

新增字段：`thinking_process TEXT`

写入时机：在 `AgentBrain._make_decisions()` 中，流式收集完成后（`raw = "".join(chunks)`），将 `raw` 作为 `thinking_process` 通过 `update_brain_run` 写入：

```python
# brain.py _make_decisions() 末尾，return decisions 之前
# 注意：_make_decisions 需要新增 run_id 参数
await self.service.update_brain_run(run_id, {
    "thinking_process": raw,
})
```

`_make_decisions()` 签名变更：新增 `run_id: str` 参数，由 `execute()` 传入。

## ReviewEngine 核心流程

### 日复盘（每日 15:45）

1. 检查今天是否为交易日（`weekday() < 5`，后续数据源升级后切换到 TradingCalendar）
2. 查找最近 5 个交易日内所有 `brain_runs`（status=completed）的 `trade_ids`
3. 对每个 `trade_id`，从 `agent.trades` 表读取实际成交价（`decision_price`）和 `stock_code`
4. 从 DuckDB 快照读取该 `stock_code` 的最新收盘价（`review_price`）
5. 计算 `pnl_pct`、`holding_days`（trade_date 到今天的交易日数）、`status`（win/loss/holding）
6. 写入 `agent.review_records`（INSERT OR IGNORE，幂等）
7. 统计当日指标：胜率、平均收益率、最大亏损
8. 规则验证：将统计结果 + 活跃规则列表 + 今日对账详情交给 LLM

LLM 规则验证输出格式：

```json
{
  "rule_updates": [
    {
      "rule_id": "xxx",
      "relevant": true,
      "validated": true,
      "reason": "今天追高买入的标的确实亏损了，验证了该规则"
    },
    {
      "rule_id": "yyy",
      "relevant": true,
      "validated": false,
      "reason": "今天止损执行及时，但该规则建议的止损位过宽"
    }
  ]
}
```

- `relevant=true` 的规则：`verify_count += 1`
- `relevant=true` 且 `validated=true`：`verify_win += 1`
- 更新后重算 `confidence = verify_win / verify_count`
- 触发自动淘汰检查

### 周复盘（每周五 16:00）

1. 汇总本周所有 `agent.review_records`（review_date 在本周一到本周五之间）
2. 代码计算周度统计：总交易数、胜率、总收益率、最佳/最差交易
3. 将周度统计 + 全部活跃规则 + 本周典型案例（最佳+最差各 3 条）交给 LLM

LLM 周复盘输出格式：

```json
{
  "new_rules": [
    {"rule_text": "连涨3天后追高胜率低，应等回调再入场", "category": "timing"},
    {"rule_text": "板块轮动初期介入优于末期追涨", "category": "sector"}
  ],
  "retire_rules": ["rule_id_1", "rule_id_2"],
  "insights": "本周整体偏保守，错过了两个板块轮动机会。止损执行较好，但选股集中度过高..."
}
```

4. `new_rules` → 写入 `agent.agent_memories`（status=active, confidence=0.5）
5. `retire_rules` → 设 `status=retired, retired_at=now`
6. 写入 `agent.weekly_summaries`（统计数据 + insights）

### AgentBrain 决策注入

在 `AgentBrain.execute()` 中，调用 `_make_decisions()` 之前：

1. `MemoryManager.get_active_rules(limit=20)` — 读取 `status=active` 的规则，按 confidence 降序
2. 注入到决策 prompt 的 system message：

```
【历史经验】
以下是你从过去交易中积累的经验规则，请在决策时参考：
1. {rule_text} (置信度: {confidence:.0%})
2. ...
```

3. 拼接到 `_make_decisions()` 的 prompt 中（在"决策规则"之后追加）

## MemoryManager 接口

```python
class MemoryManager:
    """Agent 经验规则管理器"""

    def __init__(self, db: AgentDB): ...

    # —— 读取 ——
    def get_active_rules(self, limit: int = 20) -> list[dict]:
        """读取活跃规则，按 confidence 降序"""
        ...

    def list_rules(self, status: str | None = None) -> list[dict]:
        """列出规则，可按状态筛选"""
        ...

    # —— 写入 ——
    def add_rules(self, rules: list[dict], source_run_id: str) -> list[str]:
        """批量写入新规则，返回 id 列表"""
        ...

    # —— 更新 ——
    def update_verification(self, rule_id: str, validated: bool):
        """更新验证计数，重算 confidence，触发自动淘汰检查"""
        ...

    def retire_rules(self, rule_ids: list[str]):
        """批量淘汰规则"""
        ...
```

`ReviewEngine` 通过 `MemoryManager` 操作规则，不直接操作 DB。

## 调度

`AgentScheduler` 新增两个 job。`ReviewEngine` 实例在 `AgentScheduler.start()` 中创建：

```python
class AgentScheduler:
    def start(self, portfolio_id: str | None = None):
        # ... 现有 brain job ...

        # 创建 ReviewEngine 实例
        from engine.agent.review import ReviewEngine
        from engine.agent.memory import MemoryManager
        db = AgentDB.get_instance()
        memory_mgr = MemoryManager(db)
        self._review_engine = ReviewEngine(db=db, memory_mgr=memory_mgr)

        self._scheduler.add_job(
            self._review_engine.daily_review,
            CronTrigger(hour=15, minute=45, day_of_week="mon-fri"),
            id="agent_review_daily",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._review_engine.weekly_review,
            CronTrigger(hour=16, minute=0, day_of_week="fri"),
            id="agent_review_weekly",
            replace_existing=True,
        )
```

## 前端

### /agent 页面改造

顶部新增 tab 栏切换：`运行记录` | `复盘记录` | `经验规则`

现有的左侧运行记录列表 + 右侧详情保持不变，作为"运行记录" tab 的内容。

### 复盘记录 tab

- 顶部统计卡片：总胜率、总收益率、本周胜率、本周收益率（调用 `/api/v1/agent/reviews/stats`）
- 下方列表：每条对账记录
  - 股票代码/名称、操作方向、决策价 → 实际价、收益率（绿涨红跌）、持有天数、状态标签
- 筛选：按日期、按 daily/weekly
- 周报摘要：从 `/api/v1/agent/reviews/weekly` 获取，折叠展示

### 经验规则 tab

- 规则列表，每条显示：
  - 规则文本
  - 分类标签（timing/risk/sector/position）
  - 置信度进度条
  - 验证次数（verify_win / verify_count）
  - 状态标签（active 绿 / retired 红）
- 按状态筛选：active / retired / 全部
- 只读，不提供编辑操作

### 思维回放

- 在现有运行详情页（"运行记录" tab 的右侧面板），decisions 区域下方新增"思维过程"折叠面板
- 展示 `brain_runs.thinking_process` 的完整 LLM 输出
- Markdown 渲染
- `thinking_process` 字段已通过现有 `GET /api/v1/agent/brain/runs/{run_id}` 端点自动返回（DB 加字段后 service 层 `_sync_read` 自动包含）

## API 端点

```
GET  /api/v1/agent/reviews?days=7&type=daily|weekly        — 复盘记录列表
GET  /api/v1/agent/reviews/stats?days=30                   — 统计指标（胜率、收益率等）
GET  /api/v1/agent/reviews/weekly?limit=10                 — 周报摘要列表
GET  /api/v1/agent/memories?status=active|retired|all      — 经验规则列表
```

现有端点无需修改：
- `GET /api/v1/agent/brain/runs/{run_id}` — 自动返回新增的 `thinking_process` 字段

## 文件结构

```
backend/engine/agent/
├── brain.py          — 修改：_make_decisions 新增 run_id 参数，存储 thinking_process，注入 memories
├── review.py         — 新增：ReviewEngine（daily_review, weekly_review）
├── memory.py         — 新增：MemoryManager（规则 CRUD、验证更新、自动淘汰）
├── scheduler.py      — 修改：start() 中创建 ReviewEngine，新增两个 review job
├── db.py             — 修改：_init_tables 新增 review_records、weekly_summaries、agent_memories 表，brain_runs 加 thinking_process 字段
├── models.py         — 修改：新增 ReviewRecord、WeeklySummary、AgentMemory 模型
├── service.py        — 修改：新增 review/memory 相关 CRUD
├── routes.py         — 修改：新增 reviews、memories 端点
└── ...

frontend/app/agent/page.tsx  — 修改：新增 tab 切换、复盘记录、经验规则展示
```

## 不做的事情

- 不允许用户手动编辑经验规则（Agent 自己管理）
- 不做实时盈亏推送（复盘是定时批处理）
- 不做复杂的归因分析（如因子归因），用简单的价格对比
- 不做分页（规则和复盘记录量级可控，后续需要再加）
