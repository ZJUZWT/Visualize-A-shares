# Expert Learning Progress And Intent Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Expert 页增加“学习进度”右侧折叠卡，并在聊天入口前加入意图分流，让概念/教学类问题不再误进股票分析流程。

**Architecture:** 后端新增 Expert 学习画像聚合 read model 与轻量 intent router；分析类请求继续复用现有 `ExpertAgent` / `EngineExpert` 主链，概念/教学类请求走无工具直答流；前端增加 portfolio 上下文 helper、学习卡组件与 Expert 页面布局调整，并补齐前后端测试。

**Tech Stack:** FastAPI, DuckDB, Pydantic, Loguru, Next.js 15, React 19, Zustand, Node `node:test`, pytest

---

### Task 1: 设计与计划文档落盘

**Files:**
- Create: `docs/plans/2026-04-02-expert-learning-progress-design.md`
- Create: `docs/plans/2026-04-02-expert-learning-progress.md`

**Step 1: 写设计文档**

覆盖：

- 意图类型与分流矩阵
- 无工具直答模式
- 学习画像 read model
- portfolio 上下文来源
- Expert 右侧折叠卡结构

**Step 2: 写实施计划**

把后端意图路由、学习聚合、前端侧卡和验证命令拆成独立任务。

**Step 3: 保存文档**

确认两个文件路径正确。

### Task 2: 后端意图分流

**Files:**
- Create: `backend/engine/expert/intent.py`
- Modify: `backend/engine/expert/routes.py`
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/expert/engine_experts.py`
- Modify: `backend/engine/expert/schemas.py`
- Test: `tests/unit/expert/test_agent.py`
- Test: `tests/unit/expert/test_routes.py`

**Step 1: 写失败测试**

新增最小测试：

```python
async def test_rag_concept_question_routes_to_direct_reply_without_clarify():
    ...

async def test_engine_expert_concept_question_routes_to_direct_reply_without_tools():
    ...
```

**Step 2: 跑测试看它失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py -k "direct_reply or intent" -v
```

Expected: 因 intent router / direct reply 还不存在而失败。

**Step 3: 写最小实现**

- 新建 `intent.py`，实现规则优先、LLM 兜底的 intent classifier
- 在 `routes.py` 进入 clarification / chat 前调用 classifier
- 为 `EngineExpert` 和 `ExpertAgent` 增加无工具直答流式方法
- 在 `schemas.py` 增加意图返回类型

**Step 4: 重新跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py -k "direct_reply or intent" -v
```

Expected: PASS

### Task 3: 后端学习画像聚合接口

**Files:**
- Create: `backend/engine/expert/learning.py`
- Modify: `backend/engine/expert/routes.py`
- Modify: `backend/engine/expert/schemas.py`
- Test: `tests/unit/expert/test_routes.py`

**Step 1: 写失败测试**

新增测试：

```python
def test_learning_profile_aggregates_reviews_memories_and_reflections(client):
    ...

def test_learning_profile_orders_focus_by_expert_type(client):
    ...
```

**Step 2: 跑测试确认失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "learning_profile" -v
```

Expected: 因接口和聚合器尚未实现而失败。

**Step 3: 写最小实现**

- 新建 `learning.py`，基于 AgentDB / AgentService 聚合：
  - review stats
  - memories
  - reflections
  - expert source plans
- 在 `routes.py` 新增 `GET /api/v1/expert/learning/profile`
- 在 `schemas.py` 增加 score card、knowledge item、source summary 等响应模型

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "learning_profile" -v
```

Expected: PASS

### Task 4: 前端 portfolio 上下文与学习卡 view model

**Files:**
- Create: `frontend/lib/expertLearning.ts`
- Create: `frontend/lib/expertLearning.test.ts`
- Create: `frontend/lib/activePortfolio.ts`
- Create: `frontend/lib/activePortfolio.test.ts`
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/types/expert.ts`

**Step 1: 写失败测试**

新增两个 helper 测试：

```ts
test("pickExpertLearningPortfolio prefers remembered portfolio", () => {
  ...
});

test("normalizeExpertLearningProfile builds expert-specific sections", () => {
  ...
});
```

**Step 2: 跑测试确认失败**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts frontend/lib/activePortfolio.test.ts
```

Expected: helper 不存在或结构不匹配而失败。

**Step 3: 写最小实现**

- 增加 active portfolio localStorage helper
- 在 Agent 页切换 portfolio 时写入 remembered portfolio
- 增加 learning profile normalization / sorting helper
- 在 `types/expert.ts` 补 learning profile 类型

**Step 4: 重跑测试确认通过**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts frontend/lib/activePortfolio.test.ts
```

Expected: PASS

### Task 5: Expert 页右侧折叠学习卡

**Files:**
- Create: `frontend/components/expert/ExpertLearningRail.tsx`
- Modify: `frontend/app/expert/page.tsx`
- Modify: `frontend/stores/useExpertStore.ts`
- Modify: `frontend/components/expert/MessageBubble.tsx`

**Step 1: 写失败测试**

新增卡片数据组织测试：

```ts
test("learning rail shows empty state when profile has no evidence", () => {
  ...
});
```

如果当前仓库没有现成组件测试基建，就至少把 view model 测试写全。

**Step 2: 跑测试确认失败**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts
```

Expected: 因缺少空态 / 展示字段而失败。

**Step 3: 写最小实现**

- store 增加：
  - 当前 learning profile
  - loading / error
  - fetch action
- Expert 页增加右侧中部折叠卡
- MessageBubble 保存 trade plan 时补写 `source_conversation_id`

**Step 4: 重跑测试确认通过**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts frontend/lib/activePortfolio.test.ts
```

Expected: PASS

### Task 6: 回归验证

**Files:**
- Modify: `tests/unit/expert/test_routes.py`
- Modify: `tests/unit/expert/test_agent.py`
- Modify: `frontend/lib/expertLearning.test.ts`
- Modify: `frontend/lib/activePortfolio.test.ts`

**Step 1: 跑后端回归**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py -q
```

Expected: PASS

**Step 2: 跑前端回归**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts frontend/lib/activePortfolio.test.ts frontend/lib/expertFeedback.test.ts frontend/lib/clarificationSelection.test.ts
```

Expected: PASS

**Step 3: 做最小人工检查**

- `Expert` 页打开后右侧可见折叠学习卡
- 输入“什么是市盈率”不进入澄清/选股链路
- 输入个股问题仍可正常分析

**Step 4: 整理提交**

按实现粒度提交代码，避免把无关改动混入同一个 commit。
