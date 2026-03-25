# Agent Backtest Engine Design

> 编写日期：2026-03-23
> 范围：为 Main Agent 增加一个日级事件驱动的历史模拟内核，验证 agent 在历史时间线上是否能稳定完成“分析、决策、执行、复盘、记忆演化”的完整轮回。

---

## 1. 背景

当前 Main Agent 后端已经具备三类真实能力：

- `AgentBrain` 可以执行一次候选筛选、分析、决策、执行
- `ReviewEngine` 可以写入日复盘、周复盘、memory 演化
- `timeline/equity` 与 `timeline/replay` 已经能重建历史读模型

但这仍然缺一个真正的“历史模拟内核”：

- 现在只能看“历史上发生了什么”
- 不能让 agent 在某段历史区间里重新按天推进
- 不能回答“如果只给它当时能看到的数据，它能否连续完成多天决策与复盘”

这意味着当前系统更接近可视化和验证 harness，而不是 agent 自己可运行的历史轮回环境。

---

## 2. 目标

本批次只做日级 backtest engine，目标是尽快形成可验证闭环：

1. 按交易日推进 Main Agent 历史模拟
2. 每天严格冻结在 `as_of_date`，禁止未来数据泄漏
3. 在历史区间里真实产出：
   - `brain_run`
   - `trade_plan`
   - `trade`
   - `daily_review`
   - `weekly_review`
   - `memory` 变化
4. 输出既可看绩效，也可看 agent 演化证据
5. 暴露后端 API 和 MCP tool，方便直接验证与调试

---

## 3. 非目标

本批次不做：

- 分钟级或 tick 级撮合
- 限价单排队、盘口冲击、部分成交
- 券商级交易成本建模
- 复杂组合优化和参数搜索
- 全自动策略调参闭环

这次交付的是“日级 agent 历史轮回引擎”，不是券商级高精度回测平台。

---

## 4. 方案对比

### 方案 A：只在 replay 之上做历史评分

做法：

- 复用已有 `timeline/replay`
- 对历史已发生交易做评分与聚合

优点：

- 实现最快
- 风险最小

缺点：

- 不能重新驱动 agent 做决策
- 不是回测，只是复盘统计

### 方案 B：日级事件驱动的 agent backtest

做法：

- 在隔离环境中按交易日推进
- 每个交易日给 agent 一个冻结到当日的历史上下文
- 真实运行 `AgentBrain -> Execution -> Review -> Memory`

优点：

- 与现有 Main Agent 写路径复用度最高
- 能验证“agent 是否会进化”
- 实现成本可控，适合 demo 阶段

缺点：

- 只能做日级近似成交
- 不覆盖分钟级细节

### 方案 C：完整事件驱动撮合引擎

做法：

- 独立订单状态机
- 分钟级数据、盘口、排队撮合

优点：

- 理论上最完整

缺点：

- 显著超出当前节奏
- 会推迟验证主线目标

本批次采用方案 B。

---

## 5. 核心设计

> Implementation note (2026-03-23):
> 当前实现已经落地 Tasks 1-5，并在 Task 6 中补了一轮真实验证修正。
> `backtest_runs` 仍保持最小写模型，聚合指标通过 summary read model 实时计算；
> `backtest_days` 已扩展为逐日证据表，包含 `brain_run_id`、`review_created`、`memory_delta`。

### 5.1 总体架构

新增一个独立模块：

- `backend/engine/agent/backtest.py`

核心对象：

- `AgentBacktestEngine`

它负责：

1. 创建隔离的 backtest run
2. 创建隔离的模拟 portfolio
3. 在指定日期区间内逐日推进
4. 为每一天构造历史冻结上下文
5. 驱动 `AgentBrain`、`ReviewEngine`
6. 写入回测日结果与总结果

它不是读模型增强，而是一层新的写路径 orchestration。

### 5.2 数据隔离策略

回测不能直接复用用户当前 live/training portfolio 写数据，否则会污染真实演化记录。

采用：

- 源组合：`source_portfolio_id`
- 模拟组合：`backtest_portfolio_id = "bt:{run_id}"`

规则：

- 从源组合复制初始资金、起始状态、watchlist、active memories、可选持仓快照
- 后续所有 `brain_runs / trades / reviews / reflections / memories` 写入模拟组合上下文
- 原 live/training 组合不被修改

这样既能最大化复用现有 service，又能保持数据隔离。

### 5.3 Backtest 数据模型

新增两张表：

#### `agent.backtest_runs`

记录一次历史模拟的最小写模型：

- `id`
- `source_portfolio_id`
- `backtest_portfolio_id`
- `start_date`
- `end_date`
- `execution_price_mode`
- `status`
- `created_at`

首版实现里，总收益、回撤、trade/review/memory 聚合指标不直接写入该表，
而是在 `GET /backtest/run/{run_id}` summary read model 中按 ledger / review / backtest_days 实时聚合。

#### `agent.backtest_days`

记录逐日推进结果：

- `id`
- `run_id`
- `portfolio_id`
- `trade_date`
- `brain_run_id`
- `review_created`
- `memory_delta`
- `created_at`

首版没有把 `daily_review_id / weekly_summary_id / weekly_reflection_id / equity_close`
等字段直接落库，而是把“足够驱动 API / MCP 验证”的证据优先写入：

- `brain_run_id`
- `review_created`
- `memory_delta`

这两张表一张看 run 级最小状态，一张看逐日证据。

### 5.4 日推进语义

每个交易日固定执行：

1. 设置 `sim_current_date = trade_date`
2. 构造冻结在 `trade_date` 的历史数据上下文
3. 创建 `brain_run(run_type="backtest")`
4. 执行 `AgentBrain.execute(run_id)`
5. 用统一成交规则完成执行落账
6. 执行 `daily_review(as_of_date=trade_date)`
7. 若命中周锚点，再执行 `weekly_review(as_of_date=trade_date)`
8. 写入 `backtest_day`

这条链路的重点不是收益极致，而是确保每天都能生成完整 agent 生命周期证据。

### 5.5 历史冻结上下文

为避免未来函数，所有数据入口都必须受 `as_of_date` 限制。

首版统一约束：

- 行情：只返回 `<= as_of_date` 的历史数据
- 新闻 / 公告：只返回 `<= as_of_date` 的记录
- 技术指标：只基于截止 `as_of_date` 的日线计算
- 回测过程中调用到的数据 hunger / quant / replay，都使用相同的历史截断

实现上不追求大而全的依赖注入框架，优先用一个简洁的历史 market context adapter 来集中提供“按日期截断”的 fetcher。

补充约束：

- `AgentBrain` 内部直接走 `engine.data.get_data_engine()` 的分析路径会被 adapter 截断
- quant 技术指标分支在 backtest context 下改为进程内计算，避免 HTTP route 重新回到 `date.today()`
- timeline / summary 读模型也必须走动态 data-engine 绑定，避免绕回 service 模块的旧引用

### 5.6 成交规则

首版只支持两个执行模式：

- `next_open`
- `same_close`

默认采用 `next_open`。

语义：

- `next_open`：第 `T` 天做决策，第 `T+1` 个可用交易日开盘成交
- `same_close`：第 `T` 天收盘成交，只用于演示和快速验证

不支持：

- 部分成交
- 挂单未成交
- 盘口排队

这是有意简化，为的是先让 agent 历史轮回跑通。

### 5.7 结果指标

首版除日曲线外，固定聚合 6 个高价值指标：

- `total_return`
- `max_drawdown`
- `trade_count`
- `win_rate`
- `review_count`
- `buy_and_hold_return`

同时统计 agent 演化指标：

- `memory_added`
- `memory_updated`
- `memory_retired`

这样能同时回答：

- “赚没赚钱”
- “agent 有没有复盘”
- “agent 有没有因为复盘发生策略演化”

---

## 6. API 与 MCP Contract

### 6.1 REST API

新增：

- `POST /api/v1/agent/backtest/run`
- `GET /api/v1/agent/backtest/run/{run_id}`
- `GET /api/v1/agent/backtest/run/{run_id}/days`

语义：

- `run` 负责创建并执行一次 backtest
- `summary` 返回总结果
- `days` 返回逐日记录和证据

### 6.2 MCP Tools

新增：

- `run_agent_backtest(...)`
- `get_agent_backtest_summary(run_id)`
- `get_agent_backtest_day(run_id, date)`

MCP 仍保持薄包装：

- backend engine 返回结构化 dict
- MCP 负责输出 operator / agent 都易读的摘要

day tool 的逐日证据不再依赖 `created_at` 时间窗猜测，而是通过 `backtest_days.brain_run_id`
反查 `trades.source_run_id`，这样在历史回放日期与真实写入时间不一致时仍能稳定拿到证据。

---

## 7. 测试策略

第一批测试覆盖：

1. 回测 run 创建与隔离 portfolio 复制
2. 日推进顺序是否正确
3. `next_open` / `same_close` 成交规则
4. 历史冻结是否阻止未来数据读取
5. summary 聚合指标
6. route contract
7. MCP tool contract

最小端到端 fixture 只需 3 到 5 个交易日，就足够验证：

- 至少一个 `brain_run`
- 至少一笔 `trade`
- 至少一个 `daily_review`
- 至少一次 `memory` 变化

---

## 8. 为什么这版值得先做

这版不是最精细，但在当前阶段最有效：

- 它比 replay 更进一步，能真正让 agent 在历史里“活起来”
- 它比券商级回测简单很多，不会把 demo 节奏拖死
- 它把重点放在 agent 自身闭环：
  - 决策
  - 执行
  - 复盘
  - 演化

如果这条链路跑通，后面再加分钟级、真实撮合或更复杂的风险模型，才有意义。
