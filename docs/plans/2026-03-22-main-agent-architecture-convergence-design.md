# Main Agent Architecture Convergence Design

> 编写日期：2026-03-22
> 范围：Main Agent 架构收敛，为后续复盘闭环与 `/agent` 透明控制台提供稳定对象模型。

---

## 1. 背景

当前 Main Agent 已具备可运行骨架：

- 独立 DuckDB：`agent.portfolio_config`、`positions`、`position_strategies`、`trades`
- 操作建议：`trade_plans`
- 运行记录：`watchlist`、`brain_runs`、`brain_config`
- 最小前端：[`frontend/app/agent/page.tsx`](/Users/swannzhang/Workspace/AIProjects/A_Claude/frontend/app/agent/page.tsx)

现状的问题不是“没有功能”，而是“对象语义未收敛”：

- `brain_runs` 只记录一次运行结果，不代表 Agent 持续状态
- `trade_plans` / `position_strategies` / `trades` 生命周期交叉，但关系未显式化
- `AgentBrain` 同时承担分析、决策、执行、日志职责，后续加复盘会继续膨胀
- `/agent` 页绑定的是 run 结果，不是 Agent 的当前状态

这会直接导致后续两类返工：

1. 复盘系统会被迫反向侵入执行逻辑
2. `/agent` 页面会继续堆展示代码，但没有稳定读模型

---

## 2. 目标

本次收敛不重写 Main Agent，而是在现有实现上建立稳定的四层对象模型：

1. `AgentState`：持续状态
2. `DecisionRun`：单次运行快照
3. `ExecutionLedger`：执行台账
4. `ReviewMemory`：复盘与经验闭环

收敛后的系统必须满足：

- `/agent` 页面可以同时展示“当前状态”和“历史运行”
- 任何一笔交易都能追溯到来源 run、来源 plan、来源策略版本
- 复盘系统不需要直接推断 UI 语义，而是读取稳定的审计对象
- 决策前能注入历史规则，决策后能沉淀新的复盘记录

---

## 3. 非目标

本阶段不做：

- 实盘交易接入
- 多账户复杂权限系统
- 全事件溯源重写
- 专家系统与 Main Agent 的认知层完全统一

我们只做“中度收敛”，让后续 2 和 3 不返工。

---

## 4. 目标对象模型

### 4.1 AgentState

表示 Agent 当前“怎么想”，不是某次运行。

建议新增表：`agent.agent_state`

```sql
CREATE TABLE IF NOT EXISTS agent.agent_state (
    id VARCHAR PRIMARY KEY DEFAULT 'default',
    portfolio_id VARCHAR NOT NULL,
    market_view VARCHAR,              -- bullish / bearish / neutral
    market_reasoning TEXT,
    position_level DOUBLE,            -- 0~1
    sector_preferences JSON,          -- [{sector, weight, reason}]
    risk_alerts JSON,                 -- ["高位分歧加剧", ...]
    strategy_summary TEXT,            -- 当前总体策略摘要
    source_run_id VARCHAR,            -- 最近一次生成该状态的 brain_run
    updated_at TIMESTAMP DEFAULT now()
);
```

用途：

- `/agent` 中栏“策略大脑面板”直接读取
- 决策时作为下一次 run 的上下文
- 复盘时对比“当时状态”和“结果”

### 4.2 DecisionRun

现有 `brain_runs` 继续保留，但升级为真正的单次运行快照。

建议扩展字段：

- `thinking_process TEXT`
- `state_before JSON`
- `state_after JSON`
- `execution_summary JSON`

语义：

- `candidates` / `analysis_results` / `decisions`：输入与输出
- `thinking_process`：LLM 原始思维/输出文本
- `state_before` / `state_after`：状态迁移
- `execution_summary`：本次 run 最终落地了哪些台账动作

### 4.3 ExecutionLedger

ExecutionLedger 不是新表，而是对现有表语义收敛：

- `trade_plans`：策略意图层
- `position_strategies`：持仓管理层
- `trades`：执行事实层
- `positions`：持仓结果层

必须新增引用字段以形成链路：

#### `agent.trade_plans`

- `source_run_id VARCHAR`
- `source_state_id VARCHAR DEFAULT 'default'`

#### `agent.position_strategies`

- `source_run_id VARCHAR`

#### `agent.trades`

- `source_run_id VARCHAR`
- `source_plan_id VARCHAR`
- `source_strategy_id VARCHAR`
- `source_strategy_version INTEGER`

这样才能回答：

- 这笔交易来自哪次 run？
- 是执行哪个 plan？
- 执行时绑定的是哪个策略版本？

### 4.4 ReviewMemory

采用已有复盘设计方向，新增：

- `agent.review_records`
- `agent.weekly_summaries`
- `agent.agent_memories`

职责划分：

- `review_records`：事实复盘
- `weekly_summaries`：统计总结
- `agent_memories`：可注入下一次决策的规则库

---

## 5. 模块边界调整

### 5.1 现状

当前 [`backend/engine/agent/service.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/service.py) 同时负责：

- Portfolio CRUD
- Trades 执行
- Strategy CRUD
- Plan CRUD
- Watchlist CRUD
- BrainRuns CRUD
- BrainConfig CRUD

这在 MVP 阶段有效，但后续会演变为“万能 Service”。

### 5.2 目标模块

建议收敛为：

```text
backend/engine/agent/
├── state.py         # AgentState 读写与快照构建
├── brain.py         # 候选筛选 / 分析聚合 / LLM 决策
├── execution.py     # plan / strategy / trade / position 状态推进
├── review.py        # 日复盘 / 周复盘
├── memory.py        # 经验规则库管理
├── service.py       # 保留为轻量门面，逐步退化为组合协调层
└── routes.py        # 按 state / ledger / review / brain 暴露 API
```

拆分原则：

- `brain.py` 不直接操作多张业务表，只产出决策与运行记录
- `execution.py` 是唯一能把决策落到账本的地方
- `review.py` 不执行交易，只读取账本与 run
- `state.py` 只产出当前状态快照，不写交易事实

---

## 6. API 收敛方向

现有 API 可保留，但应新增更稳定的读取端点：

### 6.1 新增读取端点

- `GET /api/v1/agent/state?portfolio_id=live`
- `GET /api/v1/agent/ledger/overview?portfolio_id=live`
- `GET /api/v1/agent/review/records?portfolio_id=live`
- `GET /api/v1/agent/review/memories`

### 6.2 保留并升级

- `GET /api/v1/agent/brain/runs`
- `GET /api/v1/agent/brain/runs/{run_id}`

升级后返回：

- `thinking_process`
- `state_before`
- `state_after`
- `execution_summary`

这样 `/agent` 页面不必自行拼接“当前状态”。

---

## 7. 前端读模型收敛

目标不是继续扩展一个“run 详情页”，而是改成真正三栏控制台：

### 左栏：Conversation / Run Feed

- 最近运行记录
- 手动触发
- watchlist
- 后续可以接入 Agent 对话

### 中栏：Strategy Brain

读取 `AgentState`：

- 当前市场观点
- 仓位水平
- 行业偏好
- 风险警报
- 当前策略摘要
- 最近一次状态更新时间

再叠加 `DecisionRun`：

- 最近一次运行的候选、决策、thinking summary
- 决策时间线

### 右栏：Execution Ledger

读取 `ExecutionLedger`：

- 当前持仓
- 绑定策略版本
- 未完成 plan
- 最新交易记录
- 账户资产与收益

这样 UI 才是“Agent 当前状态 + 历史行为”，而不是只展示某次 run 的 JSON。

---

## 8. 推荐分阶段落地

### Phase A：语义收敛

目标：先把对象关系定住。

- 新增 `agent_state`
- 扩展 `brain_runs`
- 给 `trade_plans` / `trades` / `position_strategies` 补 source 引用字段
- 在执行路径中写入这些引用关系

### Phase B：复盘闭环

目标：让 Agent 能从历史里学习。

- 新增 `review_records` / `weekly_summaries` / `agent_memories`
- 决策前注入 `agent_memories`
- 决策后由 `ReviewEngine` 更新规则有效性

### Phase C：前端控制台升级

目标：让 `/agent` 展示稳定读模型。

- 左栏：run feed + watchlist
- 中栏：AgentState + 决策时间线
- 右栏：持仓、策略、交易、收益

---

## 9. 关键设计决策

### 决策 1：不重写现有 agent 表

原因：

- 当前 Phase 1A / 1B 代码已经能跑
- 重写成本高，且近期收益低
- 通过补引用关系与新增状态表即可完成 80% 收敛

### 决策 2：AgentState 独立于 brain_runs

原因：

- run 是离散事件
- state 是持续状态
- UI 和复盘都需要读取“当前状态”，不应每次从最后一个 run 反推

### 决策 3：ReviewMemory 独立于 ExecutionLedger

原因：

- 复盘结论不是交易事实
- 经验规则有生命周期与置信度，不应塞回 trades 或 plans

### 决策 4：Execution 作为独立边界

原因：

- 当前 `AgentBrain` 既决策又执行，后续难以调试
- 执行应成为唯一的“写账本”入口

---

## 10. 风险与控制

### 风险 1：Service 膨胀继续加剧

控制：

- 新功能优先进入 `state.py` / `execution.py` / `review.py`
- `service.py` 只做兼容门面，不再继续扩成万能类

### 风险 2：前端直接绑数据库形状

控制：

- 提供稳定聚合 API
- `/agent` 页面读取的是读模型，不是直接用表结构拼 UI

### 风险 3：复盘系统与决策系统互相污染

控制：

- `review.py` 只读台账和 run
- 决策只通过 `agent_memories` 接收复盘结果

---

## 11. 结论

推荐采用“中度收敛”路线，而不是继续零散补功能或彻底重写：

- 保留现有 agent 数据层和页面资产
- 增加 `AgentState`
- 升级 `brain_runs` 为完整 `DecisionRun`
- 将现有账本对象显式收敛为 `ExecutionLedger`
- 以 `ReviewMemory` 承接复盘闭环

这样后续的“复盘系统”和“/agent 三栏控制台”会落在稳定对象模型上，而不是各自发明一套语义。
