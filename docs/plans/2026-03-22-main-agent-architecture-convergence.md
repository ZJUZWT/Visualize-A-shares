# Main Agent Architecture Convergence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 收敛 Main Agent 的状态、运行、执行、复盘边界，让后续复盘闭环和 `/agent` 控制台建立在稳定对象模型上。

**Architecture:** 在现有 `backend/engine/agent` 基础上做中度收敛，不重写现有表和 API。先新增 `agent_state` 与 `brain_runs` 扩展字段，再补执行引用关系与复盘记忆层，最后升级 `/agent` 页面到稳定读模型。

**Tech Stack:** Python 3.11, FastAPI, DuckDB, Pydantic v2, APScheduler, React 19, Next.js 15, TypeScript

---

## Task 1: 收敛数据库对象语义

**Files:**
- Modify: `backend/engine/agent/db.py`
- Modify: `backend/engine/agent/models.py`
- Modify: `tests/unit/test_agent_brain.py`
- Modify: `tests/unit/test_agent_phase1a.py`

**Step 1: 写 `agent_state` 和引用字段的失败测试**

在 `tests/unit/test_agent_brain.py` 增加表断言与模型断言：

- `agent_state` 表存在
- `brain_runs` 包含 `thinking_process`
- `trades` 包含 `source_run_id/source_plan_id/source_strategy_id/source_strategy_version`
- `trade_plans` / `position_strategies` 包含 `source_run_id`

**Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -v`

Expected:

- FAIL，缺少新增表或字段

**Step 3: 在 `db.py` 中补建表和字段**

在 [`backend/engine/agent/db.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/db.py)：

- 新增 `agent.agent_state`
- 扩展 `agent.brain_runs`
- 扩展 `agent.trade_plans`
- 扩展 `agent.position_strategies`
- 扩展 `agent.trades`

使用幂等的 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`

**Step 4: 在 `models.py` 中新增/扩展模型**

在 [`backend/engine/agent/models.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/models.py)：

- 新增 `AgentState`
- 扩展 `BrainRun`
- 扩展 `TradePlan`
- 扩展 `Trade`
- 扩展 `PositionStrategy`

**Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_phase1a.py::TestAgentDB -v`

Expected:

- PASS

**Step 6: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/models.py tests/unit/test_agent_brain.py tests/unit/test_agent_phase1a.py
git commit -m "feat(agent): add state and execution linkage schema"
```

---

## Task 2: 引入 AgentState 读写边界

**Files:**
- Create: `backend/engine/agent/state.py`
- Modify: `backend/engine/agent/service.py`
- Modify: `backend/engine/agent/routes.py`
- Test: `tests/unit/test_agent_brain.py`

**Step 1: 写失败测试**

新增测试覆盖：

- 初始化后能读到默认 `agent_state`
- 可以更新 `market_view/position_level/sector_preferences/risk_alerts`
- 新增 `GET /api/v1/agent/state?portfolio_id=...`

**Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k state -v`

Expected:

- FAIL，缺少状态管理接口

**Step 3: 创建 `state.py` 最小实现**

在 [`backend/engine/agent/state.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/state.py) 实现：

- `get_state(portfolio_id)`
- `upsert_state(portfolio_id, updates, source_run_id=None)`
- `build_state_snapshot(...)` 占位函数

先不做复杂推理，只保证稳定状态读写。

**Step 4: 暴露 API**

在 [`backend/engine/agent/routes.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/routes.py) 增加：

- `GET /state`
- `PATCH /state`

**Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k state -v`

Expected:

- PASS

**Step 6: Commit**

```bash
git add backend/engine/agent/state.py backend/engine/agent/service.py backend/engine/agent/routes.py tests/unit/test_agent_brain.py
git commit -m "feat(agent): add persistent agent state"
```

---

## Task 3: 升级 brain_runs 为完整 DecisionRun

**Files:**
- Modify: `backend/engine/agent/brain.py`
- Modify: `backend/engine/agent/service.py`
- Modify: `backend/engine/agent/models.py`
- Test: `tests/unit/test_agent_brain.py`

**Step 1: 写失败测试**

新增测试覆盖：

- `_make_decisions()` 结束后会写入 `thinking_process`
- `execute()` 会更新 `state_before/state_after`
- `brain_runs` 返回完整结构

**Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "thinking or decision" -v`

Expected:

- FAIL，字段未写入

**Step 3: 修改 `brain.py`**

在 [`backend/engine/agent/brain.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/brain.py)：

- `execute(run_id)` 开始时读取 `state_before`
- `_make_decisions(..., run_id)` 写入 `thinking_process`
- 执行完成后生成 `execution_summary`
- 结束时写入 `state_after`

先允许 `state_after` 为最小摘要，不做复杂状态生成。

**Step 4: 修改 `service.py`**

使 `update_brain_run()` 支持：

- `thinking_process`
- `state_before`
- `state_after`
- `execution_summary`

**Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "thinking or decision" -v`

Expected:

- PASS

**Step 6: Commit**

```bash
git add backend/engine/agent/brain.py backend/engine/agent/service.py backend/engine/agent/models.py tests/unit/test_agent_brain.py
git commit -m "feat(agent): persist decision run artifacts"
```

---

## Task 4: 收敛 ExecutionLedger 引用关系

**Files:**
- Create: `backend/engine/agent/execution.py`
- Modify: `backend/engine/agent/brain.py`
- Modify: `backend/engine/agent/service.py`
- Test: `tests/unit/test_agent_phase1a.py`
- Test: `tests/unit/test_agent_brain.py`

**Step 1: 写失败测试**

新增测试覆盖：

- Agent 自动生成 `trade_plan` 时写入 `source_run_id`
- 执行 trade 时写入 `source_plan_id`
- `position_strategy` 可以写入 `source_run_id`

**Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_phase1a.py tests/unit/test_agent_brain.py -k "source_run or source_plan" -v`

Expected:

- FAIL，引用关系为空

**Step 3: 创建 `execution.py`**

在 [`backend/engine/agent/execution.py`](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/execution.py) 实现最小协调器：

- `create_plan_from_decision(run_id, decision)`
- `execute_plan(run_id, plan_id, decision)`

目的不是重写交易逻辑，而是把“写账本”边界从 `brain.py` 抽出来。

**Step 4: 修改 `brain.py` 调用执行协调器**

让 `brain.py` 只负责：

- 筛选
- 分析
- 决策
- 调 execution

不再直接同时管 plan + trade 细节。

**Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_phase1a.py tests/unit/test_agent_brain.py -k "source_run or source_plan" -v`

Expected:

- PASS

**Step 6: Commit**

```bash
git add backend/engine/agent/execution.py backend/engine/agent/brain.py backend/engine/agent/service.py tests/unit/test_agent_phase1a.py tests/unit/test_agent_brain.py
git commit -m "refactor(agent): isolate execution ledger writes"
```

---

## Task 5: 新增 ReviewMemory 基础设施

**Files:**
- Create: `backend/engine/agent/review.py`
- Create: `backend/engine/agent/memory.py`
- Modify: `backend/engine/agent/db.py`
- Modify: `backend/engine/agent/models.py`
- Test: `tests/unit/test_agent_brain.py`

**Step 1: 写失败测试**

新增测试覆盖：

- 表 `review_records` / `weekly_summaries` / `agent_memories` 存在
- `MemoryManager.get_active_rules()` 可读出规则
- `MemoryManager.update_verification()` 会更新 confidence

**Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "review or memory" -v`

Expected:

- FAIL，缺少表和类

**Step 3: 在 `db.py` 中补 3 张表**

按设计文档新增：

- `agent.review_records`
- `agent.weekly_summaries`
- `agent.agent_memories`

**Step 4: 创建 `memory.py`**

实现：

- `get_active_rules(limit=20)`
- `list_rules(status=None)`
- `add_rules(rules, source_run_id)`
- `update_verification(rule_id, validated)`
- `retire_rules(rule_ids)`

**Step 5: 创建 `review.py` 最小骨架**

实现：

- `daily_review()` 占位版
- `weekly_review()` 占位版

先完成数据链路，不急于把 LLM 周报做复杂。

**Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "review or memory" -v`

Expected:

- PASS

**Step 7: Commit**

```bash
git add backend/engine/agent/review.py backend/engine/agent/memory.py backend/engine/agent/db.py backend/engine/agent/models.py tests/unit/test_agent_brain.py
git commit -m "feat(agent): add review and memory infrastructure"
```

---

## Task 6: 在决策前注入经验规则

**Files:**
- Modify: `backend/engine/agent/brain.py`
- Modify: `backend/engine/agent/scheduler.py`
- Test: `tests/unit/test_agent_brain.py`

**Step 1: 写失败测试**

新增测试覆盖：

- 当有 active rules 时，决策 prompt 包含规则文本
- 调度器初始化时创建 `ReviewEngine` 与 `MemoryManager`

**Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "rules or scheduler" -v`

Expected:

- FAIL，prompt 或调度器未接入

**Step 3: 修改 `brain.py`**

在决策前：

- 读取 `MemoryManager.get_active_rules()`
- 将规则注入 prompt

**Step 4: 修改 `scheduler.py`**

新增：

- `daily_review` job
- `weekly_review` job

保持现有 brain job 不变。

**Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "rules or scheduler" -v`

Expected:

- PASS

**Step 6: Commit**

```bash
git add backend/engine/agent/brain.py backend/engine/agent/scheduler.py tests/unit/test_agent_brain.py
git commit -m "feat(agent): inject review memories into decisions"
```

---

## Task 7: 升级 `/agent` 为稳定读模型控制台

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Create: `frontend/components/agent/AgentStatePanel.tsx`
- Create: `frontend/components/agent/DecisionRunPanel.tsx`
- Create: `frontend/components/agent/ExecutionLedgerPanel.tsx`

**Step 1: 写前端验收清单**

在任务说明中明确可见行为：

- 左栏：run feed + watchlist + 手动运行
- 中栏：当前状态 + 最近一次决策摘要
- 右栏：持仓、交易、计划、收益

**Step 2: 先拆组件，不改视觉大框架**

从 [`frontend/app/agent/page.tsx`](/Users/swannzhang/Workspace/AIProjects/A_Claude/frontend/app/agent/page.tsx) 抽出三个组件。

**Step 3: 接入 `/state` 和聚合读接口**

页面状态改为同时拉取：

- `/api/v1/agent/state`
- `/api/v1/agent/brain/runs`
- `/api/v1/agent/ledger/overview`

**Step 4: 做最小 UI 升级**

不要一次做完根 TODO 所有华丽视觉，只先把语义稳定下来：

- 当前状态卡片
- 风险提醒
- 最近决策摘要
- 持仓和交易台账

**Step 5: 手动验证**

Run:

```bash
cd frontend && npm run dev
```

Expected:

- `/agent` 页面可同时看到“当前状态”“最近运行”“执行台账”

**Step 6: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/components/agent
git commit -m "feat(agent): upgrade dashboard to state-ledger-run layout"
```

---

## Task 8: 全链路回归验证

**Files:**
- Modify: `tests/unit/test_agent_brain.py`
- Modify: `tests/unit/test_agent_phase1a.py`
- Modify: `tests/unit/test_trade_plans.py`

**Step 1: 补完整回归测试**

覆盖：

- 建仓 / 加仓 / 卖出
- plan -> trade -> strategy source 链路
- state 持续更新
- brain run thinking/process 存档
- memory 注入
- review 表写入

**Step 2: 运行后端测试**

Run:

```bash
python3 -m pytest tests/unit/test_agent_phase1a.py tests/unit/test_trade_plans.py tests/unit/test_agent_brain.py -v
```

Expected:

- PASS

**Step 3: 手动验证接口**

Run:

```bash
cd backend && python3 main.py
```

然后验证：

- `GET /api/v1/agent/state`
- `GET /api/v1/agent/brain/runs`
- `GET /api/v1/agent/portfolio/live`

**Step 4: Commit**

```bash
git add tests/unit/test_agent_phase1a.py tests/unit/test_trade_plans.py tests/unit/test_agent_brain.py
git commit -m "test(agent): add convergence regression coverage"
```

