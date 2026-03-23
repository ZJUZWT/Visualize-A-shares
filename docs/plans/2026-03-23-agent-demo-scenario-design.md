# Agent Demo Scenario Verification Design

> 编写日期：2026-03-23
> 范围：为 Main Agent MCP 验证链路补一套 deterministic demo scenario，使 `prepare + verify` 可以稳定跑通整轮进化闭环。

---

## 1. 背景

当前系统已经有：

- `verify_agent_cycle`
  - 能验证一次 agent 轮回
  - 输出 `stages / checks / evolution_diff`
- `inspect_agent_snapshot`
  - 能看当前状态快照

问题是它仍然依赖“当前库里刚好有合适数据”：

- 不同环境里 portfolio 状态不一致
- weekly review 是否产生新规则不稳定
- daily review 是否能拿到 trade 取决于 run 时间和输入数据
- 真实 `AgentBrain` 还会受市场数据和 LLM 行为影响

这会让 MCP 很难作为“整轮闭环验证工具”稳定使用。

---

## 2. 目标

本批次一次性完成：

1. 提供一个 deterministic 的 demo scenario seeder
2. 提供一个一键 `seed + verify` 的 MCP tool
3. 保持现有 `verify_agent_cycle` 语义不变
4. 让 demo 验证不依赖前端，不依赖实时行情，不依赖真实 LLM

---

## 3. 非目标

本批次不做：

- 多套复杂 demo 场景管理系统
- 真实策略回测引擎
- 对现有真实 `AgentBrain` 做更深 mockable 架构改造
- 前端 demo 操作面板

---

## 4. 方案选择

### A. 把 seed 逻辑塞进 `verify_agent_cycle`

优点：

- 调用最短

缺点：

- 污染通用 tool 语义
- 真实 portfolio 验证和 demo 验证耦合

### B. 新增 `prepare_demo_agent_portfolio` + `verify_demo_agent_cycle`

优点：

- `verify_agent_cycle` 保持纯净
- 日常使用只要调用 `verify_demo_agent_cycle`
- 出问题时还能单独调 `prepare_demo_agent_portfolio`

缺点：

- MCP tool 会多两个入口

### C. 只做 seeder，不做 verify tool

优点：

- 后端改动最少

缺点：

- 仍需手工串调用

本批次采用 B。

---

## 5. 数据隔离策略

当前 schema 有一个现实问题：

- `daily_reviews`
- `weekly_summaries`
- `weekly_reflections`
- `agent_memories`
- `watchlist`

这些表并不都按 portfolio 隔离。

因此 demo scenario 不能靠“清空表”来 reset，只能做有界清理。

本批次采用：

- 固定 `scenario_id = demo-evolution`
- 固定 `portfolio_id = demo-evolution`
- 固定未来周窗口
  - 例如 `as_of_date = 2042-01-10`
  - `week_start` 由代码计算
- 所有 demo 种子数据都带可识别前缀
  - `source_run_id = demo-seed:demo-evolution`
  - watchlist `added_by = demo-seed`
  - historical run id / review id / trade id 带 `demo-evolution-` 前缀

这样可以安全地清理 demo 自己的数据，而不碰真实数据。

---

## 6. Demo Scenario 结构

### 6.1 baseline

`prepare_demo_agent_portfolio` 会创建：

- training mode portfolio
- agent state
- 2 条 watchlist
- 1 条低置信度 active memory
- 2 条历史 completed brain run
- 2 条 loss 类型 review record

其中低置信度 memory 满足：

- `verify_count >= 3`
- `confidence < 0.5`

这样 weekly review 时能稳定触发 `retired_rules`。

### 6.2 demo brain run

`verify_demo_agent_cycle` 不走真实 `AgentBrain`，而是走 deterministic demo brain：

- 创建一个新的 manual brain run
- 生成 1 条 buy trade
- 更新 run 的 `candidates / decisions / trade_ids / state_before / state_after / execution_summary`
- 把 `started_at / completed_at` 固定写到 scenario 日期窗口内

这样 daily review 就能稳定拿到该 trade。

### 6.3 review 演化结果

然后走现有 verification pipeline：

- `daily_review`
  - 为 demo brain trade 写入 1 条新 review record
- `weekly_review`
  - 看到该周已有 loss 多于 win
  - 新增 weekly rule
  - 退休低置信度 memory
  - 写入 weekly summary
  - 写入 weekly reflection

最终 `evolution_diff` 稳定命中：

- `review_records_delta`
- `memories_added`
- `memories_retired`
- `reflections_added`
- `weekly_summaries_delta`

---

## 7. 架构

新增模块：

- `backend/engine/agent/demo_scenarios.py`

内部提供：

- `DemoAgentScenarioSeeder`
  - `prepare_scenario()`
  - `build_brain_factory()`

`AgentVerificationHarness` 增加：

- `prepare_demo_portfolio()`
- `verify_demo_cycle()`

MCP wrapper 增加：

- `prepare_demo_agent_portfolio`
- `verify_demo_agent_cycle`

---

## 8. MCP 输出

### 8.1 prepare

返回：

- `scenario_id`
- `portfolio_id`
- `as_of_date`
- `week_start`
- seeded artifacts summary

### 8.2 verify

在原有 verification report 基础上补：

- `Demo Seed`
- `Scenario ID`
- `Portfolio`
- `As Of Date`
- `Seed Summary`

---

## 9. 测试策略

后端单元测试覆盖：

1. `prepare_scenario()` 能生成 baseline
2. `prepare_scenario()` 重复执行不累计脏数据
3. `verify_demo_cycle()` 能稳定返回 `pass`
4. `verify_demo_cycle()` 返回 `seed_summary`

MCP 测试覆盖：

- 新 tool 文本输出
- server 注册了这两个 tool

---

## 10. 代码落点

- `backend/engine/agent/demo_scenarios.py`
  - 新增 deterministic seeder + demo brain
- `backend/engine/agent/verification.py`
  - 新增 demo prepare / verify 编排
- `backend/mcpserver/agent_verification.py`
  - 新增 prepare / verify demo wrapper
- `backend/mcpserver/server.py`
  - 注册新 tools
- `tests/unit/test_agent_demo_scenarios.py`
  - 新增 seeder tests
- `tests/unit/test_agent_verification.py`
  - 新增 demo verify harness test
- `tests/unit/mcpserver/test_agent_verification_tools.py`
  - 新增 wrapper tests
- `tests/unit/mcpserver/test_http_transport.py`
  - 更新注册断言

