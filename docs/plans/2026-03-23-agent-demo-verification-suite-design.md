# Agent Demo Verification Suite Design

> 编写日期：2026-03-23
> 范围：新增一个 MCP 统一编排入口，把 demo 闭环验证和短窗口历史回测串成一次机器可消费的验收流程。

---

## 1. 背景

当前 backend 已经具备两类能力：

- demo 闭环验证：
  - `prepare_demo_agent_portfolio`
  - `verify_demo_agent_cycle`
  - `get_demo_agent_cycle_summary`
- 历史回测：
  - `run_agent_backtest`
  - `get_agent_backtest_summary`
  - `get_agent_backtest_day`

这两组能力分别可用，但还缺一个“统一验收入口”回答更直接的问题：

- Main Agent 的 demo 进化轮回现在还能不能跑通？
- 放进历史时间窗里，回测链路还能不能正常重放？
- 这两段链路合在一起时，当前版本是否还能视为“可继续演化验证”？

用户当前目标不是再做新的 UI，而是先把后端闭环跑通并便于 agent 自己反复调用验证。

---

## 2. 目标

新增一个新的 MCP tool，完成以下事情：

1. 准备 deterministic demo scenario
2. 运行一次 demo 闭环验证
3. 基于同一个 demo portfolio 运行一次短窗口回测
4. 返回一份统一 JSON 摘要，供 agent 自动验收和后续编排消费

这个入口是“统一验证 orchestrator”，不是新的业务引擎。

---

## 3. 非目标

本批次不做：

- 新前端页面
- 新 CLI
- 新数据库表
- 新回测指标体系
- 解析已有 markdown 再拼装结果

也不在这里追求“券商级回测”，只做一条最小可验证闭环。

---

## 4. 方案对比

### 方案 A：复用现有 MCP 文本接口，做字符串拼装

做法：

- 调用现有 markdown / JSON tool
- 在新入口里解析字符串并重新拼装

优点：

- 改动范围小

缺点：

- 脆弱，依赖展示格式
- 错误语义不稳定
- 不适合机器消费

### 方案 B：新增 MCP 编排器，直接复用 harness 和 backtest engine

做法：

- 直接调用 `AgentVerificationHarness.verify_demo_cycle()`
- 直接调用 `AgentBacktestEngine.run_backtest()` 和 `get_run_summary()`
- 在 MCP 层统一归并状态与证据

优点：

- 不侵入主业务层
- 不需要新增 backend engine 模块
- 返回结构化结果，适合 agent 自动消费

缺点：

- 需要在 MCP 层维护一份统一 contract

### 方案 C：新增 backend orchestration service

做法：

- 在 `backend/engine/agent` 再加一层 suite service
- MCP 只做薄包装

优点：

- 分层更严格

缺点：

- 当前需求过小，属于过度设计

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 新 tool

新增 MCP tool：

- `run_demo_agent_verification_suite`

位置：

- `backend/mcpserver/agent_verification_suite.py`

`server.py` 只做注册，不承载编排逻辑。

### 5.2 默认流程

统一入口按固定顺序执行：

1. 调用 `AgentVerificationHarness.verify_demo_cycle(scenario_id, timeout_seconds)`
2. 从返回值中读取 `seed_summary.portfolio_id`
3. 决定 backtest 窗口：
   - 若传入 `backtest_start_date` / `backtest_end_date`，优先使用用户输入
   - 若未传入，则默认使用 `seed_summary.week_start -> seed_summary.as_of_date`
4. 调用 `AgentBacktestEngine.run_backtest(...)`
5. 再调用 `AgentBacktestEngine.get_run_summary(run_id)`
6. 聚合成统一 JSON

这里不额外调用 `prepare_demo_agent_portfolio`，因为 `verify_demo_cycle()` 内部已经会先 prepare scenario，再触发真实验证。

### 5.3 `smoke_mode`

新增显式开关：

- `smoke_mode: bool = False`

语义：

- `False`：保持当前业务语义，backtest 输入完全来自用户参数或 demo seed 默认窗口
- `True`：suite 仍然先跑真实 `verify_demo_cycle()`，但 backtest 阶段切换到稳定 smoke 环境

smoke 环境只影响 suite 内部的 backtest 输入准备，不改 `AgentVerificationHarness`、不改 `AgentBacktestEngine` 的默认业务行为。

smoke backtest 的目标不是评估策略表现，而是稳定验证 replay 链路本身：

- 使用一段 deterministic 内置历史行情
- 使用 suite 内部的 deterministic smoke brain 产出最小决策
- 避免依赖外部行情拉取、实时快照或 LLM/专家分析

这样可以让 agent 直接调用一个真实但稳定的工程验收入口，而不会被 `2042` demo 日期或外部数据状态拖垮。

### 5.4 输出 contract

返回 JSON 字符串，结构固定为：

```json
{
  "mode": "default|smoke",
  "overall_status": "pass|warn|fail",
  "scenario_id": "demo-evolution",
  "portfolio_id": "demo-evolution",
  "seed_summary": {},
  "demo_verification": {},
  "backtest": {},
  "evidence": {
    "verification_run_id": "run-...",
    "backtest_run_id": "bt-..."
  },
  "next_actions": []
}
```

字段语义：

- `mode`：标识本次 suite 运行的是默认业务验证还是工程 smoke 验收
- `seed_summary`：直接透出 demo seed 关键信息
- `demo_verification`：基于现有 `_build_demo_cycle_summary()` 输出的结构化摘要
- `backtest`：回测运行参数 + summary
- `evidence`：本次 suite 级别的关键 run id 和窗口信息
- `next_actions`：统一给 agent 的下一步动作建议

### 5.5 默认回测窗口

若用户不传日期，则使用 demo seed 自带窗口：

- `backtest_start_date = seed_summary.week_start`
- `backtest_end_date = seed_summary.as_of_date`

原因：

- deterministic
- 与 demo 场景上下文一致
- 足够形成一个短窗口 smoke replay

当 `smoke_mode=True` 且用户未显式传入日期时，suite 改用内置 smoke 窗口：

- `backtest_start_date = 2026-03-18`
- `backtest_end_date = 2026-03-20`

这个窗口只服务 deterministic smoke 历史行情，不对外宣称真实业务含义。

---

## 6. 状态归并规则

### 6.1 `fail`

满足任一条件即 `fail`：

- demo 验证返回 `verification_status == "fail"`
- demo 验证未返回可用 `portfolio_id`
- backtest 运行抛错
- backtest summary 无法获取

这是因为当前目标是“统一验证链路跑通”，其中任一主链路中断都不算完成。

### 6.2 `warn`

满足以下任一条件且不属于 `fail` 时为 `warn`：

- demo 验证返回 `warn`
- backtest summary 返回成功但弱指标异常，例如：
  - `trade_count == 0`
  - `review_count == 0`
  - `memory_added == 0` 且 `memory_updated == 0` 且 `memory_retired == 0`

### 6.3 `pass`

满足以下条件时为 `pass`：

- demo 验证为 `pass`
- backtest 成功完成并能返回 summary
- 不触发任何 warn 条件

---

## 7. 错误处理

统一策略是“硬失败早停，软异常下沉”：

- demo 验证失败：
  - 不继续 backtest
  - 直接返回 `overall_status = fail`
  - 保留已有 seed / verification 证据
- backtest 失败：
  - 保留 verification 成功证据
  - 整体仍记为 `fail`
- 弱异常：
  - 不抛异常
  - 通过 `overall_status = warn` + `next_actions` 暴露

---

## 8. 测试设计

最小测试闭环如下：

1. `tests/unit/mcpserver/test_agent_verification_suite_tools.py`
   - 验证默认顺序是 `verify_demo_cycle -> run_backtest -> get_run_summary`
   - 验证默认日期窗口来自 `seed_summary.week_start/as_of_date`
   - 验证 `pass / warn / fail` 归并逻辑
   - 验证 backtest 失败时仍保留 verification 证据
2. `tests/unit/mcpserver/test_http_transport.py`
   - 验证新 tool 已注册

本批次不额外要求真实 DB 集成测试，因为底层 harness/backtest 已有覆盖；suite 只验证编排 contract。

---

## 9. 为什么这个设计够用

这个方案保持了三个边界：

- 不新增 backend 业务层抽象
- 不解析展示文本
- 不引入 UI 依赖

它能给 agent 一个真正能反复调用的统一入口，用最小代价验证：

- demo 进化闭环还活着
- 历史回放链路还活着
- 当前版本是否值得继续演化和测试
