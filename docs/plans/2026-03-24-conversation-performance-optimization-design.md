# Conversation Performance Optimization Design

> 编写日期：2026-03-24
> 范围：为 `expert`、`arena`、`main agent` 抽取共享对话执行运行时，统一预取、依赖感知并行、快慢模型分层与渐进式 SSE 输出。

---

## 1. 背景

当前系统的三个核心链路都已经能工作，但性能优化策略是分散的：

1. `ExpertAgent` 已支持基础 SSE 和部分工具并行，但最终回答仍要等待整轮工具结束
2. `JudgeRAG` 复用了 `ExpertAgent` 的公开能力，但没有共享统一的执行上下文和模型分层
3. `AgentBrain` 有自己的分析和决策路径，和专家链路之间没有共享预取或模型路由机制

结果是：

- 并行策略只在局部生效，无法复用
- LLM 所有阶段默认都走同一配置，延迟较高
- 用户输入中已经暴露的股票信息没有被提前利用
- SSE 主要在“过程可见”，而不是“尽快给出有用结论”

这与本轮目标不匹配。用户明确要的是：

- 整体更快
- 不降低回答质量
- 继续保持 SSE 体验
- 长期上能支撑多个模块，而不是只修某一条链路

---

## 2. 目标

本模块完成后，应具备：

1. 三条主链路复用同一套性能能力层，而不是各自实现
2. `think` / `clarify` / `self_critique` 等轻阶段优先走快模型
3. 用户消息命中股票代码或名称时，可自动触发低成本数据预取
4. 工具执行从“硬编码阶段顺序”演进为“基于依赖关系的执行规划”
5. SSE 可先推送阶段性洞察，再持续输出最终完整回答
6. 现有 API 和主要事件命名保持兼容，前端无需同步重写

---

## 3. 非目标

本轮不做：

- 将 `expert`、`arena`、`main agent` 完全重写成同一个业务 orchestrator
- 引入复杂的跨请求分布式缓存
- 新增定时预热任务
- 改写 Main Agent 的交易执行规则或策略判断口径
- 重构前端整体事件协议

本轮是“共享运行时 + 渐进接入”，不是系统级重建。

---

## 4. 方案对比

### 方案 A：仅优化 `expert` 主链路

优点：

- 见效快
- 风险最低

缺点：

- `arena` 和 `main agent` 继续各自为政
- 很快会产生第二套、第三套性能逻辑

不采用。

### 方案 B：抽共享运行时，模块渐进接入

优点：

- 能覆盖当前 TODO 的四项性能需求
- 长期可复用
- 仍然控制在可落地范围内

缺点：

- 需要补基础抽象和回归测试
- 实现复杂度高于只修单链路

推荐采用。

### 方案 C：直接统一业务编排

优点：

- 理论上最整齐

缺点：

- 明显超出本轮范围
- 很容易把性能优化做成高风险架构迁移

不采用。

---

## 5. 核心设计

### 5.1 Shared Runtime 能力层

新增共享运行时层，放在后端公共位置，先服务三个模块：

- `ModelRouter`
- `ExecutionContext`
- `QueryPrefetcher`
- `ToolExecutionPlanner`
- `ProgressiveEmitter`

这层只负责“如何更快地跑”，不负责“业务上要做什么判断”。

### 5.2 ModelRouter

统一提供两类模型能力：

- `fast`
  - 用于 `think`
  - `clarify`
  - `self_critique`
  - `JudgeRAG.round_eval`
  - Main Agent 的轻量决策准备阶段
- `quality`
  - 用于最终回答流
  - 裁判最终裁决
  - Main Agent 的关键综合决策说明

配置策略：

- 默认继承现有 `LLM_*` 配置作为 `quality`
- 可选新增 `LLM_FAST_*` 配置
- 若 `fast` 未单独配置，则自动回退到 `quality`

这样可以做到“先快起来”，同时不强迫用户维护两套完全独立的 Provider。

### 5.3 ExecutionContext

每次对话或分析会话都创建一个本轮上下文，包含：

- `request`
  - 原始消息、history、persona、module
- `entities`
  - 股票代码、股票名、行业词、意图标签
- `prefetch`
  - 已预取的数据和命中状态
- `tool_state`
  - 工具任务、依赖、状态、产出
- `signals`
  - 可提前推给前端的阶段性洞察
- `artifacts`
  - reply、judge verdict、agent decision 等最终产物

该上下文只在本轮有效，不污染长期业务状态。

### 5.4 QueryPrefetcher

收到用户输入后，先做轻量实体识别：

- 六位股票代码
- 已知股票名称
- 典型行业词

命中股票时，后台并发预取低成本数据：

- `company_profile`
- `daily_history`
- 必要时的快照片段

预取原则：

- 只读
- 轻量
- 后台执行
- 失败不阻断主链路

预取结果放入 `ExecutionContext.prefetch`，供后续规划器和工具层复用。

### 5.5 ToolExecutionPlanner

当前 `ExpertAgent.execute_tools_streaming()` 只有一条写死规则：

- 同时存在 `expert.data` 和 `expert.quant` 时，量化专家后置

这会导致量化在很多并不依赖 data 的场景下也被迫等待。

新规划器改成最小依赖规划：

- 每个工具调用先推导依赖标签
  - `needs_code`
  - `needs_prefetched_history`
  - `independent`
- 预取已满足依赖时直接并行
- 只有缺少前置条件时才保守串行
- 若无法判断依赖，回退到当前保守策略

本轮先覆盖最常见场景：

- `expert.quant`
- `quant.get_factor_scores`
- `quant.get_technical_indicators`
- `expert.data`

### 5.6 ProgressiveEmitter

保留现有关键事件：

- `thinking_start`
- `graph_recall`
- `tool_call`
- `tool_result`
- `reply_token`
- `reply_complete`

新增可选早期事件：

- `prefetch_ready`
- `tool_partial`
- `early_insight`

输出原则：

1. 老调用方不识别新事件也不出错
2. 用户尽早看到“有用信息”，而不是只看到转圈
3. 最终完整回答仍由 `reply_complete` 兜底

### 5.7 三个模块的接入方式

`ExpertAgent`

- 第一优先级，完整接入运行时
- 吃满预取、planner、fast/quality 路由和早期 SSE

`JudgeRAG`

- 复用 `ModelRouter`
- 复用 planner 与 emitter
- 对外事件继续保持 `judge_*` 适配层

`AgentBrain`

- 本轮优先复用 `ModelRouter` 和 `QueryPrefetcher`
- 不重写整套候选分析/执行编排
- 只在轻量分析与最终决策处接入共享能力

---

## 6. 数据流

### 6.1 Expert 对话流

```text
message
  → ExecutionContext
  → QueryPrefetcher
  → graph/memory recall
  → fast think
  → ToolExecutionPlanner
  → tool execution + partial SSE
  → quality reply stream
  → fast self_critique
  → belief update / memory store
```

其中最关键的变化有两个：

1. 预取在 think 前就开始，不再浪费用户消息中的显式信息
2. 部分专家或工具一旦先返回，就能立即产出阶段性洞察

### 6.2 Arena Judge 流

```text
topic / verdict query
  → ExecutionContext
  → recall
  → fast think / fast round eval
  → planner + tools
  → quality final verdict
```

Judge 仍保留自己的 `judge_*` 事件名称，只把底层能力换成共享运行时。

### 6.3 Main Agent 流

```text
candidates
  → prefetch key stock context
  → fast lightweight analysis
  → quality final decision synthesis
  → existing execution flow
```

这样可以在不动交易规则的前提下，先拿到一部分模型阶段加速收益。

---

## 7. 兼容性与回退

兼容要求：

1. `ExpertAgent.chat()` 的既有事件和行为不应消失
2. `JudgeRAG` 继续输出 `judge_*` 前缀事件
3. `AgentBrain` 外部调用方式不变

回退策略：

- 预取失败：记日志并跳过
- `fast` 模型不可用：回退到 `quality`
- planner 无法判断依赖：回退到现有保守执行顺序
- 早期洞察生成失败：不影响最终流式回答

---

## 8. 测试策略

重点验证四类行为：

1. `ModelRouter`
   - `fast` / `quality` 路由正确
   - 缺少 `fast` 配置时能自动回退

2. `QueryPrefetcher`
   - 输入命中股票代码/名称时触发预取
   - 预取结果能进入上下文并被后续逻辑消费

3. `ToolExecutionPlanner`
   - `quant` 无需等待 `data` 时直接并行
   - 无法判断依赖时仍保持安全顺序

4. `ProgressiveEmitter`
   - 能在最终回答前发出 `prefetch_ready` / `early_insight`
   - 不破坏既有 `reply_complete`

同时需要做回归：

- 无 LLM 时 `ExpertAgent.chat()` 仍能完成
- 工具失败时仍能完成整轮流程
- `JudgeRAG` 和 `AgentBrain` 的原有测试不回归

---

## 9. 实施结论

采用方案 B，但落地成“共享运行时 + 渐进接入”。

本轮优先完成：

1. Shared Runtime 基础设施
2. `expert` 全量接入
3. `arena judge` 的低风险复用
4. `main agent` 的模型分层与预取复用

这能同时满足当前性能目标和长期演进方向，而不会把本轮实现升级为不可控的大重构。
