# Main Agent Core Closure Design

> 编写日期：2026-03-23
> 范围：一次性收敛 `Main Agent Core`，把当前已经落地的大部分能力整理成一个语义闭合、接口一致、可验证的完整模块。

---

## 1. 背景

当前仓库里的 `Main Agent Core` 已经不是空白骨架，而是由多批次能力叠加而成：

- `backend/engine/agent` 已具备 portfolio / execution / review / memory / wake / backtest / verification
- `frontend/app/agent` 已具备 chat、strategy brain、right rail、wake、pet console、training、backtest
- `backend/mcpserver` 已暴露 verification / backtest 等 Main Agent 验证工具

真正的问题已经从“没有功能”转为“模块边界与 TODO 语义没有一次性收拢”：

- 根 `TODO.md` 中有些项其实已落地，但没有被当作模块完成态统一核对
- 还有少数项只做到半截，尤其集中在信息免疫、digest 审计、重放学习
- `/agent` 页面和 backend / MCP surface 已基本齐，但仍缺少一条完整的“历史学习”闭环

因此本批次不再做新的大方向，而是对 `Main Agent Core` 做一次收尾式收敛。

---

## 2. 目标

本批次完成后，`Main Agent Core` 应满足：

1. `/agent` 页面覆盖：
   - chat
   - strategy brain
   - execution ledger / timeline / replay
   - wake / info digests
   - review / memory / reflection
   - training suite
   - backtest
2. Main Agent 的信息链路具备最小“信息免疫”语义：
   - digest 不只记录抓了什么，还记录为什么不能轻易改策略
   - 决策 trace 能明确引用本次消化了哪些 digest
3. Main Agent 具备最小“Replay Learning”闭环：
   - 选定某天回放
   - 输出“当时知道什么 / 后来发生什么 / 如果重来一次会怎样做”
4. Main Agent 的 REST / MCP / frontend contract 统一，可直接验证

---

## 3. 非目标

本批次不做：

- `expert / debate` 体系功能扩张
- `industry / chain` 独立模块增强
- 多市场数据适配
- Docker / 生产部署 / Cloudflare / 服务器运维
- 对话性能专项优化
- 新的复杂自治交易调度器

这些要么跨模块，要么不属于当前 `Main Agent Core` 收尾。

---

## 4. 剩余缺口

### 4.1 已基本完成但需要纳入模块闭环的部分

- `watch_signals`
- `info_digests`
- `daily / weekly info review`
- `agent backtest`
- `verification suite`
- `/agent` pet console / training / battle / backtest

这些能力已存在，本批次主要保证它们的 contract 和语义闭合。

### 4.2 当前仍未收口的核心缺口

#### 缺口 A：信息免疫语义仍然过弱

[`backend/engine/agent/data_hunger.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/data_hunger.py) 当前会生成 digest，但更接近“抓取结果摘要”，还不足以表达：

- 当前信息属于哪一层可信度
- 是否足以改变策略
- 缺少哪些 Tier 1 证据
- 哪些信息只是情绪、共识或噪音
- 最终建议应该是 `ignore / monitor / reassess`

这正对应根 `TODO.md` 中的：

- `DataHunger Prompt 改造`
- `Agent System Prompt`

#### 缺口 B：决策 trace 没有稳定记录“消化了哪些 digest”

当前 `brain_runs` 已有：

- `thinking_process`
- `info_digest_ids`

但还没有一个稳定、前后端都能理解的结构化字段，明确表达：

- 本次决策真正消费了哪些 digest
- 每个 digest 在决策中扮演什么角色
- gate 为何接受 / 拒绝动作

这对应根 `TODO.md` 中的：

- `DecisionLog 扩展`

#### 缺口 C：Replay 只有回放，没有“重放学习”

当前已有：

- `timeline/equity`
- `timeline/replay`
- `backtest`

但仍缺：

- “如果重来一次，你会怎么做不同”的学习视角
- 用统一结构把 `what_ai_knew`、`what_happened`、`counterfactual action` 串起来

这对应根 `TODO.md` 中的：

- `Replay Learning`

---

## 5. 设计决策

### 5.1 不新增 `decision_logs` 表

虽然根 TODO 使用了 `DecisionLog` 的表述，但当前系统已经把 run 级审计对象收敛到 `brain_runs.thinking_process`。

本批次不新建独立日志表，而是在 `thinking_process` 中新增稳定子结构：

- `decision_trace`
  - `info_digests`
  - `triggered_signals`
  - `gate_summary`

原因：

- 避免重复写一套日志
- 复用现有 `brain_runs` / `/agent` 时间线
- 更适合当前模块收尾阶段

### 5.2 DataHunger 先做“结构化免疫模板”，不引入新 LLM 编排层

`execute_and_digest()` 当前已经能聚合多源数据。

本批次不新增独立 digest LLM orchestration，而是在现有 digest 输出中补充：

- `evidence_tier`
- `strategy_change_bias`
- `immunity_checks`
- `suggested_action`
- `missing_tier1_evidence`

原则是先把结构稳定下来，再考虑后续快模型 digest / 大模型决策分层。

### 5.3 Replay Learning 基于现有 replay read model 扩展

不新建独立回测学习引擎。

复用：

- `AgentService.get_replay_snapshot()`

新增：

- `AgentService.get_replay_learning()`
- `GET /api/v1/agent/timeline/replay-learning`
- 前端 replay learning card

这样可以把“重看当日决策”做成现有回放的附加层，而不是再造一个系统。

---

## 6. 模块完成定义

本批次完成后，`Main Agent Core` 被视为“已收尾”的标准是：

1. Main Agent 相关后端读写路径无明显 contract 缺口
2. `/agent` 作为主控台可直接覆盖训练、作战、回放、复盘、历史学习
3. 信息 digest、decision trace、replay learning 三者形成最小闭环
4. Main Agent 相关单测、MCP 测试、前端 view-model 测试、前端 build 均通过

---

## 7. 测试策略

本批次只做模块内验证：

- `tests/unit/test_agent_data_hunger.py`
- `tests/unit/test_agent_brain.py`
- `tests/unit/test_agent_timeline_read_models.py`
- `tests/unit/test_agent_backtest.py`
- `tests/unit/test_agent_verification.py`
- `tests/unit/test_agent_verification_suite_routes.py`
- `tests/unit/mcpserver/test_agent_backtest_tools.py`
- `tests/unit/mcpserver/test_agent_verification_suite_tools.py`
- `tests/unit/mcpserver/test_http_transport.py`
- `frontend/app/agent/lib/*.test.ts`
- `npm run build`

---

## 8. 结论

`Main Agent Core` 不再缺少“大功能方向”，而是缺最后一轮模块收敛。

本批次采用：

- 不跨模块
- 不大重构
- 不重复造表
- 在现有 `brain_runs / replay / digest / review / pet console` 上一次性补齐剩余语义

这样能以最低返工成本把 Main Agent 真正收成一个完整模块。
