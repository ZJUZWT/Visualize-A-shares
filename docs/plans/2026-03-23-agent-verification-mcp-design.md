# Agent Verification MCP Design

> 编写日期：2026-03-23
> 范围：为 Main Agent 增加一个面向验证的 MCP harness，直接读取和驱动 backend，验证“运行一次大脑循环并完成复盘”是否真的能跑通，而不是只做静态数据查询。

---

## 1. 背景

当前系统已经具备 Main Agent 的核心后端能力：

- `AgentBrain` 可执行一次完整的候选筛选、分析、决策、执行流程
- `agent_state`、`brain_runs`、`positions`、`trades`、`review_records`、`daily_reviews`、`weekly_reflections`、`agent_memories` 已有真实写路径
- MCP server 已有一批数据查询类 tool，但没有一个 tool 能回答：
  - “这次 agent 轮回有没有真的跑完？”
  - “失败断在候选、分析、执行还是复盘？”
  - “当前 state / ledger / review / memory 是否相互自洽？”

这导致我们虽然能看单点数据，但没法用 MCP 直接验证主 Agent 的闭环是否健康。

---

## 2. 目标

本批次只做“验证 harness”，不扩新业务功能：

1. 给 MCP 增加一个可直接触发 Main Agent 单次轮回验证的入口
2. 验证完成后，返回结构化的 `pass / warn / fail` 结论
3. 对失败提供明确断点和证据，而不是只有异常堆栈
4. 提供一个只读快照工具，快速查看 agent 当前核心状态
5. 让验证逻辑优先直连 backend service / engine，而不是依赖前端页面

---

## 3. 非目标

本批次不做：

- 前端页面改造
- 新的交易策略逻辑
- 交易表现评分或收益优化
- 通用 MCP 自动化平台
- 完整的 CI 编排系统

另外，`strategy_memos` 目前尚未在默认分支稳定落地，因此“memo 边界验证”只保留为设计扩展位，不纳入第一批强制交付范围。

---

## 4. 方案对比

### 方案 A：只读静态审计

做法：

- MCP 只查询已有 `brain_runs`、`reviews`、`memories`
- 不触发新的 agent 流程

优点：

- 实现最简单
- 风险最低

缺点：

- 不能证明“这次流程真的能从运行到复盘跑完”
- 更像 dashboard，不是 harness

### 方案 B：验证编排器直连 backend

做法：

- MCP tool 直接调用 backend 的 `AgentService`、`AgentBrain`、`ReviewEngine`
- 在一个工具调用里完成：
  - 创建 `brain_run`
  - 执行 `AgentBrain`
  - 可选触发 `daily_review`
  - 校验不变量
  - 汇总结论

优点：

- 最贴近“验证整个演化轮回跑通”
- 不依赖前端
- 比走 HTTP API 更稳定，便于测试

缺点：

- 需要在 MCP 层引入 agent backend 编排依赖
- 需要额外的验证聚合和格式化逻辑

### 方案 C：外部 CLI / pytest harness

做法：

- 单独写命令行脚本或集成测试
- 不进入 MCP

优点：

- 适合 CI

缺点：

- 不方便我日常通过 MCP 直接排查
- 不满足“这是给 agent 自己用的验证入口”

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 新增验证编排层

新增一个 backend 内部验证模块，例如：

- `backend/engine/agent/verification.py`

职责：

- 编排一次完整验证
- 聚合 state / run / ledger / review / memory 证据
- 执行通过标准判断
- 输出结构化验证结果

它不是新业务引擎，而是一个只面向验证的 orchestration layer。

### 5.2 MCP 只做薄包装

MCP 层新增薄包装工具，例如：

- `backend/mcpserver/agent_verification.py`

职责：

- 调用验证编排层
- 把结果格式化为 AI 友好的 Markdown

`server.py` 只注册新 tool，不承载验证业务逻辑。

### 5.3 直接调用 backend，不走前端

验证 tool 不依赖前端页面，也不依赖 UI 状态。

优先路径：

1. 直接实例化 `AgentService`
2. 创建 `brain_run`
3. 直接 `await AgentBrain(...).execute(run_id)`
4. 可选执行 `ReviewEngine.daily_review()`
5. 读取 DB 中真实落库结果并校验

这比“通过 MCP 调 API，再由 API 起异步任务，再轮询 HTTP”更适合验证场景，也更容易写单测。

---

## 6. Tool Contract

### 6.1 `verify_agent_cycle`

```python
async def verify_agent_cycle(
    portfolio_id: str,
    as_of_date: str | None = None,
    include_review: bool = True,
    include_weekly: bool = False,
    require_trade: bool = False,
    timeout_seconds: int = 30,
) -> str:
    ...
```

语义：

- 触发并等待一次真实 `AgentBrain` 运行完成
- 可选触发一次 `daily_review`
- 可选触发一次 `weekly_review`
- 对本次轮回执行通过标准判断
- 返回验证摘要、失败阶段、关键证据

返回结果至少包含：

- `verification_status`: `pass` / `warn` / `fail`
- `brain_run_status`
- `failed_stage`
- `checks`
- `evidence`
- `next_actions`

### 6.2 `inspect_agent_snapshot`

```python
async def inspect_agent_snapshot(
    portfolio_id: str,
    run_id: str | None = None,
) -> str:
    ...
```

语义：

- 只读聚合当前 agent 关键状态
- 不触发任何写操作

聚合内容：

- 当前 `agent_state`
- 最近一次或指定 `brain_run`
- `ledger_overview`
- 最近 review stats
- active memories 数量和前几条

### 6.3 `verify_memo_boundary`（保留扩展位）

这个 tool 暂不进入第一批实现强约束。

原因：

- 默认分支还没有稳定的 `strategy_memos` contract
- 过早实现会把验证 harness 绑定到未并入主线的数据模型

保留目标：

- 未来验证“收藏/忽略 memo”不会污染 `agent_state`、`brain_runs`、`positions`、`trades`、`agent_memories`

---

## 7. 通过标准

### 7.1 `verify_agent_cycle` 的通过条件

当次验证满足以下条件时，判定为 `pass`：

1. `brain_run` 被成功创建
2. `AgentBrain.execute()` 在超时内完成
3. `brain_run.status == "completed"`
4. `state_before` 已落库
5. `state_after` 已落库
6. `execution_summary` 存在且字段自洽
7. `plan_ids`、`trade_ids` 与实际落库记录一致
8. 若 `include_review=True`，则 `daily_review` 成功执行，且出现：
   - 新 `daily_reviews` 记录，或
   - 新 `review_records`，或
   - 明确的“当日无可复盘交易但复盘流程完成”结果

### 7.2 `warn` 的条件

以下情况判为 `warn`，而不是 `fail`：

- 无候选股票，导致本次没有分析和交易，但流程完整结束
- 有候选和分析，但最终决策为空，流程完整结束
- 无新增交易，导致 review 只生成空结果或仅更新 journal

### 7.3 `fail` 的条件

以下情况判为 `fail`：

- `brain_run` 创建失败
- `AgentBrain` 执行超时
- `brain_run.status == "failed"`
- `state_before / state_after / execution_summary` 缺失
- `plan_ids / trade_ids` 与数据库不一致
- 请求了 review，但 review 流程执行报错

---

## 8. 结果结构

内部验证结果建议统一为结构化 dict，再由 MCP 格式化：

```python
{
  "verification_status": "pass",
  "portfolio_id": "demo-live",
  "run_id": "run-123",
  "failed_stage": None,
  "checks": [
    {"name": "brain_run_completed", "status": "pass"},
    {"name": "state_before_present", "status": "pass"},
    {"name": "review_completed", "status": "warn", "detail": "no reviewable trades"}
  ],
  "evidence": {
    "execution_summary": {...},
    "ledger_overview": {...},
    "review_result": {...}
  },
  "next_actions": []
}
```

这样好处是：

- backend 内部便于单测
- MCP 文本格式可调整
- 将来 CLI / CI 也能复用

---

## 9. 错误处理

### 9.1 分阶段失败定位

验证过程分为以下阶段：

- `setup`
- `brain_run_create`
- `brain_execute`
- `review_daily`
- `review_weekly`
- `invariant_check`

任何失败都必须回报阶段，而不是只返回通用失败文本。

### 9.2 超时策略

- `verify_agent_cycle` 使用 `asyncio.wait_for`
- 超时后返回 `fail`
- 若 `brain_run` 已落库但未完成，结果中要带上当前 run 状态和已知证据

### 9.3 最小侵入原则

验证 harness 不新增交易行为，不修改业务决策逻辑。

它只：

- 调用现有流程
- 读取现有结果
- 做验证判断

---

## 10. 测试策略

### 10.1 单元测试

新增：

- `tests/unit/test_agent_verification.py`
- `tests/unit/mcpserver/test_agent_verification_tools.py`

覆盖：

- `pass / warn / fail` 分支
- `brain_run failed` 场景
- timeout 场景
- review 可选开关
- ledger / id consistency 校验

### 10.2 回归测试

保留并回归：

- `tests/unit/test_agent_phase1a.py`
- `tests/unit/test_agent_review_memory.py`
- `tests/unit/mcpserver/test_http_transport.py`

保证本次新增不会破坏现有 agent 写路径与 MCP server 导入。

---

## 11. 第一批落地范围

第一批只交付：

1. `verify_agent_cycle`
2. `inspect_agent_snapshot`
3. backend 验证编排层
4. MCP wrapper 和测试

不交付：

- `verify_memo_boundary`
- `explain_cycle_failure`
- 前端联动

这样可以先把“真实轮回是否跑通”的最小闭环做出来。

