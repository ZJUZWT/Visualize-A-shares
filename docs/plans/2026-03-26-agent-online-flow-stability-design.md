# Agent Online Flow Stability Design

> 编写日期：2026-03-26
> 目标：在不做大改的前提下，保证 Main Agent 的前端链路和 MCP 在线链路都能稳定跑通，并在服务不可用时明确报错。

---

## 1. 背景

当前问题不是单个按钮失效，而是“在线服务、MCP、前端状态”三者之间存在基础链路错误：

- 在线服务启动后会长期持有 `data/main_agent.duckdb`
- `backend/mcpserver` 中的 agent 工具仍直接初始化 `AgentDB`
- 导致 MCP 与在线服务争抢同一个 DuckDB 文件锁
- 前端宠物页把训练运行态、历史训练结果、账户切换后的残留状态混在一起

结果是：

- 服务在线时，agent MCP 可能完全不可用
- 前端训练状态可能和真实运行状态不一致
- 切换账户后可能看到旧训练结果

---

## 2. 设计目标

本次只追求“流程跑通且错误暴露清楚”，不追求 agent 结论质量。

必须满足：

1. 前端在线链路可跑通：
   - 进入 `/agent`
   - 读取账户与快照
   - 手动 Run
   - 运行训练 suite
   - 宠物 / 训练 / 模拟盘页面不因基础状态错误中断
2. MCP 在线链路可跑通：
   - 通过 MCP 读取 agent snapshot
   - 通过 MCP 触发 demo verification / suite
3. 服务不在线时：
   - agent 前端和 agent MCP 都 fail fast
   - 明确暴露“服务不可用”，不做本地降级

---

## 3. 非目标

本次不做：

- `/agent/page.tsx` 大规模拆分
- 宠物状态机重构
- 新 UI 设计
- agent 结论质量优化
- 离线 agent 模式修复

---

## 4. 方案

### 4.1 在线服务成为唯一权威入口

对于 agent 相关读写与验证能力，统一改为：

- 前端 -> HTTP API
- MCP -> HTTP API

不再允许 MCP 直接初始化 `AgentDB` 或直接访问 agent harness 的本地数据库单例。

这样可以保证：

- 在线服务是唯一写者
- MCP 与前端共享同一条业务入口
- 一旦失败，问题集中在 HTTP / 业务逻辑，不再是跨进程锁冲突

### 4.2 MCP 侧只保留 fail-fast 在线模式

对 agent MCP 工具增加统一在线访问层：

- 启动时探测 `/api/v1/health`
- 在线时调用 agent HTTP route
- 离线时直接返回明确错误

本次不做 agent 的 DuckDB read-only 降级。原因很简单：当前目标是暴露所有基础错误，而不是掩盖错误。

### 4.3 前端只修阻断流程的状态问题

前端不做大拆，只做三类最小修补：

1. `suiteRunningMode` 与 `suiteResult` 分离
   - 运行中看 `suiteRunningMode`
   - 历史结果看 `suiteResult`
2. 切换 `portfolioId` 时清理训练相关脏状态
   - `suiteResult`
   - `suiteError`
   - 可能被旧 suite 覆盖的宠物训练展示
3. 服务不可用时统一显式报错
   - 页面初始化读取失败
   - 训练运行失败
   - Run 失败

### 4.4 后端仅补薄路由，不改业务

如果 MCP 需要的在线能力当前没有 route，则补最薄的一层 route：

- route 只做参数接收、调用现有 service/harness、返回 JSON
- 不新增新的业务判断

优先复用已有：

- `/api/v1/agent/verification-suite/run`
- 现有 portfolio / state / ledger / run / backtest 路由

---

## 5. 需要改动的模块

### MCP

- `backend/mcpserver/agent_verification.py`
- `backend/mcpserver/agent_verification_suite.py`
- 如有必要，新增轻量 HTTP client helper

### Backend

- `backend/engine/agent/routes.py`
- 如缺失则补 snapshot / verification 对应 route

### Frontend

- `frontend/app/agent/page.tsx`
- `frontend/app/agent/lib/petConsoleViewModel.ts`
- 对应测试文件

---

## 6. 错误处理

统一原则：

- 服务离线：明确报 `Agent service unavailable`
- HTTP 非 2xx：保留后端 detail
- 训练结果解析失败：明确提示，不静默吞掉
- MCP 遇到服务离线：直接失败，不尝试本地 DB

---

## 7. 验证标准

### 7.1 MCP

- 在线时：
  - agent snapshot 可读
  - demo verification 可触发
  - verification suite 可触发
- 离线时：
  - 返回明确服务不可用错误

### 7.2 Frontend Logic

- 训练进行中时宠物状态不依赖旧训练结果
- 切换账户后不会残留上一账户训练结果
- 旧训练结果不会压过正在运行的 brain run 状态

### 7.3 回归

- agent verification suite route 测试通过
- MCP verification suite 工具测试通过
- pet view-model 测试覆盖新增状态

---

## 8. 为什么这版合适

这版不追求漂亮结构，只做一件事：

把 “在线服务 + MCP + 前端” 三条链收回到同一条在线入口上，消除当前最致命的基础错误来源。
