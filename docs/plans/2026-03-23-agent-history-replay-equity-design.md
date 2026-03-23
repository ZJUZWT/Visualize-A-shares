# Agent History Replay And Equity Design

> 编写日期：2026-03-23
> 范围：为 Main Agent 补齐“AI 历史决策回放”和“账户净值曲线”后端闭环，先做真实读模型与 API，不扩成完整回测引擎。

---

## 1. 背景

当前 `/agent` 右栏已经有部分账本与策略历史能力：

- `GET /api/v1/agent/portfolio/{portfolio_id}/ledger/overview`
- `GET /api/v1/agent/strategy/history`
- `GET /api/v1/agent/reviews`
- `GET /api/v1/agent/reflections`
- `GET /api/v1/agent/brain/runs`

但还有两个关键空洞没有补上：

1. 账户概览仍按 `entry_price * qty` 近似持仓市值，不能回答“某一天账户当时值多少钱”
2. 没有日级回放视图，无法对照“当时 AI 知道什么、做了什么、后来发生了什么”

这会直接卡住 Main Agent 的验证闭环。我们可以看到单点数据，但不能重建时间序列上的决策和账户变化。

---

## 2. 目标

本批次只做后端最小闭环：

1. 提供账户净值时间线接口
2. 同时返回两种净值口径：
   - `mark_to_market`
   - `realized_only`
3. 提供按日历史回放接口
4. 回放结果聚合：
   - 当日账户摘要
   - 当日持仓快照
   - 当日相关 brain runs
   - 当日 plan / trade
   - 当日 review / reflection 摘要
   - `what_ai_knew`
   - `what_happened`
5. 单测覆盖重建逻辑、价格缺失回退、路由 contract

---

## 3. 非目标

本批次不做：

- 完整回测引擎
- 重跑历史日内撮合
- 防未来函数的事件驱动仿真框架
- 前端复杂图表和交互
- 基于 replay 自动打分或自动调参

换句话说，这次是“历史状态重建 + 可验证读模型”，不是“重新模拟市场”。

---

## 4. 方案对比

### 方案 A：只看成交历史，不做价格重建

做法：

- 只用 `trades` 做 realized PnL 聚合
- 不接历史行情

优点：

- 实现最简单
- 不依赖价格数据

缺点：

- 无法回答“账户当天总资产”
- 无法做持仓浮盈亏曲线
- 不能支撑“历史回放”

### 方案 B：按成交记录重建每日账户状态，再接历史收盘价估值

做法：

- 以 `trades` 为事实来源重建每天现金和持仓数量
- 用 `DataEngine.get_daily_history()` 获取历史收盘价
- 生成两条净值曲线和日级回放快照

优点：

- 贴近真实账本
- 只做读模型，不改变现有写路径
- 容易写单测，适合当前 demo 阶段

缺点：

- 对价格缺失要定义回退规则
- 需要自己做 position timeline 聚合

### 方案 C：先做完整回测引擎再暴露 replay

优点：

- 理论上最完整

缺点：

- 远超当前范围
- 会把“验证闭环”拖成长期工程

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 总体思路

新增一层只读 timeline 聚合逻辑，输入是：

- `portfolio_config`
- `positions`
- `trades`
- `brain_runs`
- `trade_plans`
- `review_records`
- `daily_reviews`
- `weekly_reflections`
- 历史行情收盘价

输出是两个稳定读模型：

1. `equity_timeline`
2. `replay_snapshot`

这层逻辑放在 `AgentService` 内即可，不单独拆新 engine。原因是它本质上仍是 agent read model。

### 5.2 账户状态重建

事实来源只认 `agent.trades`，不反推 UI 状态。

按交易时间升序遍历后维护：

- `cash_balance`
- `positions_by_id`
  - `stock_code`
  - `stock_name`
  - `holding_type`
  - `qty`
  - `cost_basis`
  - `avg_entry_price`
  - `realized_pnl`

规则：

- `buy` / `add`
  - 现金减少 `amount`
  - 持仓数量增加
  - 成本基础增加
- `sell` / `reduce`
  - 现金增加 `amount`
  - 持仓数量减少
  - 按平均成本结转已实现盈亏
- 某日回放时，只纳入 `created_at <= replay_date 23:59:59` 的交易

### 5.3 净值曲线定义

#### `mark_to_market`

每天：

- `equity = cash_balance + sum(open_qty * close_price_as_of_day)`

其中 `close_price_as_of_day` 规则：

1. 优先使用该交易日收盘价
2. 若该日无数据，回退到该日前最近一个可用收盘价
3. 若自建仓日起仍无任何价格，则回退到持仓均价

这条曲线反映“如果当天按收盘估值，账户值多少钱”。

#### `realized_only`

每天：

- `equity = initial_capital + cumulative_realized_pnl`

也可以等价表示为：

- `cash_balance + remaining_cost_basis`

其中未实现盈亏不进入曲线。

这条曲线反映“只看已经落袋的交易结果，账户演化如何”。

### 5.4 时间轴边界

默认时间范围：

- 起点：`portfolio.sim_start_date`，若为空则取首笔 trade 日期，若仍为空则取 `created_at`
- 终点：最后一笔 trade 日期与今天中的较早者

首批不做分钟级；粒度固定为“日”。

如果时间范围内没有成交：

- 仍返回至少一条起始日记录
- 两条曲线都等于 `initial_capital`

### 5.5 历史回放聚合

新增回放接口按某一天返回快照，核心结构：

- `date`
- `portfolio_id`
- `account`
- `positions`
- `brain_runs`
- `plans`
- `trades`
- `reviews`
- `reflections`
- `what_ai_knew`
- `what_happened`

其中：

- `account`
  - `cash_balance`
  - `position_value_mark_to_market`
  - `position_cost_basis_open`
  - `total_asset_mark_to_market`
  - `total_asset_realized_only`
  - `realized_pnl`
  - `unrealized_pnl`
- `positions`
  - 该日收盘后的持仓快照
  - 每个持仓同时带 `close_price`, `market_value`, `unrealized_pnl`
- `brain_runs`
  - 当天 `started_at` 或 `completed_at` 落在该日的 run
- `plans`
  - 当天创建或更新过的 plan
- `trades`
  - 当天成交
- `reviews`
  - 当天 `review_records`
- `reflections`
  - 当天 daily review

### 5.6 `what_ai_knew` 与 `what_happened`

这两个字段先做规则化聚合，不引入 LLM 再总结。

`what_ai_knew` 包含：

- 当天 brain run 的 `thinking_process`
- `state_before`
- `state_after`
- `execution_summary`
- 关联 plan 的 `reasoning`
- 当天 trade 的 `thesis` / `reason` / `data_basis`

`what_happened` 包含：

- 当天成交列表
- 当天收盘后账户变化
- 当天 review 结果
- 若有下一交易日价格数据，附上 `next_day_move_pct`

这样首批就能回答：

- AI 当时基于什么信息做决定
- 决定执行了没有
- 执行后当日和次日发生了什么

### 5.7 价格读取策略

历史价格统一走现有 `DataEngine.get_daily_history(code, start, end)`。

实现上增加内部 helper：

- 先收集时间窗内全部出现过的 `stock_code`
- 逐个拉历史行情
- 转成 `{code: {date: close}}`
- 估值时做“向前回退”查找

首批不做批量价格缓存表；进程内局部缓存即可。

---

## 6. API Contract

### 6.1 `GET /api/v1/agent/timeline/equity`

查询参数：

- `portfolio_id` 必填
- `start_date` 可选，格式 `YYYY-MM-DD`
- `end_date` 可选，格式 `YYYY-MM-DD`

返回：

```json
{
  "portfolio_id": "live",
  "start_date": "2026-03-18",
  "end_date": "2026-03-23",
  "mark_to_market": [
    {
      "date": "2026-03-18",
      "equity": 1000000.0,
      "cash_balance": 820000.0,
      "position_value": 180000.0,
      "realized_pnl": 0.0,
      "unrealized_pnl": 0.0
    }
  ],
  "realized_only": [
    {
      "date": "2026-03-18",
      "equity": 1000000.0,
      "cash_balance": 820000.0,
      "position_cost_basis_open": 180000.0,
      "realized_pnl": 0.0
    }
  ]
}
```

### 6.2 `GET /api/v1/agent/timeline/replay`

查询参数：

- `portfolio_id` 必填
- `date` 必填，格式 `YYYY-MM-DD`

返回：

```json
{
  "portfolio_id": "live",
  "date": "2026-03-20",
  "account": {},
  "positions": [],
  "brain_runs": [],
  "plans": [],
  "trades": [],
  "reviews": [],
  "reflections": [],
  "what_ai_knew": {},
  "what_happened": {}
}
```

错误语义：

- 组合不存在：`404`
- 日期格式非法：`400`
- 日期早于组合起始：`400`

---

## 7. 代码落点

首批涉及文件：

- `backend/engine/agent/service.py`
  - 新增 timeline / replay read model
  - 新增价格加载和状态重建 helper
- `backend/engine/agent/routes.py`
  - 新增两个 GET route
- `backend/engine/agent/models.py`
  - 如有必要补充 response model；若当前路由仍走 dict，可先不强推 Pydantic
- `tests/unit/test_agent_timeline_read_models.py`
  - 新增主测试文件

首批不改写路径，不新增数据库表。

---

## 8. 测试策略

重点做纯后端单测，价格数据全部 stub：

1. 净值曲线能正确处理买入、加仓、减仓、卖出
2. `mark_to_market` 与 `realized_only` 数值分离正确
3. 价格缺失时会向前回退，仍缺失则回退到均价
4. 无成交组合仍返回稳定时间线
5. 回放接口能正确聚合同日 `brain_runs` / plans / trades / reviews / reflections
6. 次日价格存在时，`what_happened` 带出 `next_day_move_pct`
7. route 层 200 / 400 / 404 contract 稳定

---

## 9. 后续扩展位

本批次做完后，再自然往下接：

- 前端 `/agent` 右栏收益曲线
- 历史回放 UI
- 决策命中率和策略版本表现分析
- 防未来函数的真正 replay / backtest engine

但这些都应建立在本次稳定的 timeline read model 之上，而不是反过来。
