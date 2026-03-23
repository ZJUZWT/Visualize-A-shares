# Agent Evolution Verification Design

> 编写日期：2026-03-23
> 范围：把现有 `verify_agent_cycle` 从“单次 brain run 核查”升级为可验证 Main Agent 进化轮回的 MCP 后端闭环。

---

## 1. 背景

当前系统已经具备两块基础能力：

- `verify_agent_cycle`
  - 触发一次真实 `manual` brain run
  - 检查 `state_before / state_after / execution_summary`
  - 可选执行 `daily_review`
- `inspect_agent_snapshot`
  - 聚合 `state / latest_run / ledger / review_stats / memories`

这意味着“流程能跑”已经初步存在，但还缺一层关键语义：

- 不能明确说明本轮是否真的发生了“演化”
- 没有统一的 `before/after` 快照证据
- `memory / reflection / strategy history` 变化没有被结构化输出
- operator 看到报告后，仍需要自己人工拼接判断

用户当前需要的是一个可以让 MCP 直接验证“AI 进化轮回是否跑通”的工具，因此需要把现有能力扩成一个完整闭环，而不是继续堆散点接口。

---

## 2. 目标

本批次一次性完成：

1. 为 `verify_agent_cycle` 增加 `before/after snapshot`
2. 输出阶段化验证结果
3. 输出结构化 `evolution_diff`
4. 明确区分“执行链路通过”和“是否发生演化”
5. 让 MCP 文本结果可直接用于 operator 判断，不依赖前端

---

## 3. 非目标

本批次不做：

- 新增前端页面或新控制台 UI
- 实盘级回测引擎
- 历史多日批量仿真器
- 强制要求每次轮回都必须生成交易
- 引入额外外部数据依赖

---

## 4. 方案选择

### A. 强化现有 `verify_agent_cycle`

优点：

- 复用现有 MCP tool 名称与调用入口
- 对 operator 最直接
- 一次调用即可看到链路和演化结果

缺点：

- `verify_cycle` 结果结构会更丰富

### B. 新增 `verify_agent_evolution_loop`

优点：

- 概念上更独立

缺点：

- MCP 接口分裂
- 与现有 `verify_agent_cycle` 高度重叠

### C. 只做 snapshot diff 工具

优点：

- 改动最小

缺点：

- 仍需人工串联
- 不能形成闭环判定

本批次采用 A。

---

## 5. 判定语义

`verify_agent_cycle` 的结果分三层：

### 5.1 `fail`

以下任一情况：

- brain run 创建失败
- brain run 超时或失败
- invariant 校验失败
- review 执行失败

### 5.2 `warn`

执行链路完整通过，但未观察到明确演化变化，例如：

- 没有新增 review 记录
- 没有 memory 新增 / 更新 / 退役
- 没有 reflection 增量
- strategy history 未出现可感知变化

这表示“系统能跑”，但“本轮未证明自主进化”。

### 5.3 `pass`

执行链路完整通过，且 `evolution_diff` 至少命中一类有效演化证据：

- `review_records_delta > 0`
- `memories_added > 0`
- `memories_updated > 0`
- `memories_retired > 0`
- `reflections_added > 0`
- `strategy_history_changed = true`

---

## 6. 快照模型

新增统一快照采集逻辑，供 `verify_cycle` 和 `inspect_snapshot` 复用。

快照包含：

- `portfolio_id`
- `state`
- `latest_run`
- `ledger`
- `review_stats`
- `memories`
- `strategy_history`
- `reflections`
- `weekly_summaries`

默认 memory 使用 `status="all"`，因为“退役规则”本身就是进化证据，不能只看 active。

---

## 7. Diff 模型

新增 `evolution_diff`：

- `brain_runs_delta`
- `review_records_delta`
- `weekly_summaries_delta`
- `reflections_added`
- `strategy_history_count_delta`
- `strategy_history_changed`
- `memories_added`
- `memories_updated`
- `memories_retired`
- `memory_change_ids`
- `signals`

其中：

- `memories_added`
  - `after` 有、`before` 没有
- `memories_updated`
  - 同一 `id` 的 `confidence / verify_count / verify_win / status` 任一变化
- `memories_retired`
  - `status: active -> retired`
- `strategy_history_changed`
  - `after` 比 `before` 新增 completed brain run 记录

`signals` 用于给 MCP 渲染层直接展示“为什么是 pass/warn”。

---

## 8. 阶段化验证

`verify_cycle` 返回中新增 `stages`：

- `snapshot_before`
- `brain_execute`
- `invariant_check`
- `daily_review`
- `weekly_review`
- `snapshot_after`
- `evolution_diff`

每个 stage 至少返回：

- `name`
- `status`
- `detail`

其中 `weekly_review` 仅在 `include_weekly=true` 时执行。

---

## 9. MCP 输出

MCP 文本报告新增以下区块：

- Summary
- Stages
- Checks
- Evolution Diff
- Evidence
- Next Actions

其中 `Evolution Diff` 用于直接回答：

- 是否产生 review
- 是否有记忆变化
- 是否有 reflection
- 是否出现新的 strategy history

---

## 10. 测试策略

后端单元测试新增至少两个主场景：

1. 链路通过但无演化变化
   - 结果应为 `warn`
   - `evolution_diff.signals` 为空

2. 链路通过且触发演化变化
   - 结果应为 `pass`
   - `evolution_diff` 中至少一个演化指标大于 0

MCP wrapper 测试补充：

- 新增 `Stages` 和 `Evolution Diff` 区块渲染
- 结果中能正确输出 diff 字段

---

## 11. 代码落点

- `backend/engine/agent/verification.py`
  - 新增 snapshot 采集与 diff 逻辑
  - 扩展 `verify_cycle` 返回结构
- `backend/mcpserver/agent_verification.py`
  - 渲染 `stages` 与 `evolution_diff`
- `tests/unit/test_agent_verification.py`
  - 新增 fail-first 场景测试
- `tests/unit/mcpserver/test_agent_verification_tools.py`
  - 新增 MCP 输出断言

