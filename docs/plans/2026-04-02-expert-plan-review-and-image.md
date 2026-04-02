# Expert Plan Review And Image Grounding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 Expert 图片理解链路，并让 Expert 生成的策略卡支持手动复盘、学习回流和右侧学习栏展示。

**Architecture:** 后端分两条线推进：一条修复 `ContextGuard` 前后的多模态消息保持，并增加轻量图片结构化摘要；另一条在 `agent.trade_plans` 旁新增独立 `plan_reviews` 记录与复盘接口，再通过 Expert 学习画像接口把这些结果回流到右侧学习栏和 Expert prompt。前端只在现有策略卡和学习栏上增量扩展，不开新页面。

**Tech Stack:** FastAPI, DuckDB, Pydantic, Loguru, Next.js 15, React 19, Zustand, pytest, Node `node:test`

---

### Task 1: 文档落盘与设计提交

**Files:**
- Create: `docs/plans/2026-04-02-expert-plan-review-and-image-design.md`
- Create: `docs/plans/2026-04-02-expert-plan-review-and-image.md`

**Step 1: 写设计文档**

覆盖：

- 图片丢失根因
- 图片结构化摘要
- `plan_reviews` 数据模型
- 学习回流与 UI 方案

**Step 2: 写实施计划**

把数据库、服务层、Expert 链路、前端卡片、学习栏拆成独立任务。

**Step 3: 提交文档**

Run:

```bash
git add docs/plans/2026-04-02-expert-plan-review-and-image-design.md docs/plans/2026-04-02-expert-plan-review-and-image.md
git commit -m "docs: add expert plan review and image grounding design"
```

Expected: 文档单独成 commit，作为后续实现基线。

### Task 2: 锁住图片链路回归测试

**Files:**
- Modify: `tests/unit/expert/test_agent.py`
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/llm/context_guard.py`

**Step 1: 写失败测试**

新增最小测试：

```python
async def test_reply_stream_preserves_user_images_after_context_guard():
    ...

async def test_direct_reply_preserves_user_images_after_context_guard():
    ...
```

断言：

- 进入 `chat_stream()` 的最后一条 user message 仍带 `images`
- `ContextGuard` 不会丢失多模态内容

**Step 2: 跑测试确认失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py -k "preserves_user_images" -q
```

Expected: FAIL，当前实现会丢失 `images`。

**Step 3: 写最小实现**

- 调整 `ContextGuard` 输入结构，保留 `images`
- 调整 `ExpertAgent._reply_stream()` / `direct_reply()` 重建 `ChatMessage` 时保留 `images`

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py -k "preserves_user_images" -q
```

Expected: PASS

### Task 3: 图片结构化摘要

**Files:**
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/expert/schemas.py`
- Test: `tests/unit/expert/test_agent.py`

**Step 1: 写失败测试**

新增测试：

```python
async def test_reply_stream_injects_image_summary_when_images_exist():
    ...
```

断言：

- 有图片时会调用一个轻量摘要步骤
- 最终发送给主回复模型的 user content 中包含图片摘要文字

**Step 2: 跑测试确认失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py -k "image_summary" -q
```

Expected: FAIL，当前不存在图片摘要。

**Step 3: 写最小实现**

- 在 `ExpertAgent` 新增轻量图片摘要 helper
- 使用流式收集短 JSON，不阻断主链路
- 将摘要注入最终 user message 或 system notice

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py -k "image_summary" -q
```

Expected: PASS

### Task 4: 计划复盘数据模型

**Files:**
- Modify: `backend/engine/agent/db.py`
- Modify: `backend/engine/agent/models.py`
- Modify: `backend/engine/agent/service.py`
- Test: `tests/unit/test_trade_plans.py`

**Step 1: 写失败测试**

新增测试：

```python
def test_trade_plan_input_accepts_source_message_id():
    ...

def test_plan_reviews_table_exists(tmp_path):
    ...
```

**Step 2: 跑测试确认失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/test_trade_plans.py -k "source_message_id or plan_reviews" -q
```

Expected: FAIL，模型和表结构尚未补齐。

**Step 3: 写最小实现**

- 为 `TradePlanInput` / `TradePlan` 增加 `source_message_id`
- 为 `agent.trade_plans` 增加对应列
- 新增 `agent.plan_reviews` 表

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/test_trade_plans.py -k "source_message_id or plan_reviews" -q
```

Expected: PASS

### Task 5: 计划复盘生成接口

**Files:**
- Modify: `backend/engine/agent/service.py`
- Modify: `backend/engine/agent/routes.py`
- Test: `tests/unit/test_trade_plans.py`
- Test: `tests/unit/test_agent_review_memory.py`

**Step 1: 写失败测试**

新增测试：

```python
def test_review_plan_generates_deterministic_plan_review():
    ...

def test_plan_review_does_not_write_review_records():
    ...
```

断言：

- 手动复盘一张计划会生成 `plan_reviews` 记录
- 不会写入 `review_records`

**Step 2: 跑测试确认失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py -k "plan_review" -q
```

Expected: FAIL

**Step 3: 写最小实现**

- 在 `AgentService` 增加 `review_plan(plan_id, review_date=None, review_window=...)`
- 用确定性历史行情回放逻辑生成：
  - `entry_hit`
  - `take_profit_hit`
  - `stop_loss_hit`
  - `max_gain_pct`
  - `max_drawdown_pct`
  - `outcome_label`
  - `summary`
- 在 `routes.py` 暴露手动复盘接口

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py -k "plan_review" -q
```

Expected: PASS

### Task 6: Expert 学习画像接入计划复盘

**Files:**
- Modify: `backend/engine/expert/learning.py`
- Modify: `backend/engine/expert/routes.py`
- Modify: `backend/engine/expert/tool_tracker.py`
- Test: `tests/unit/expert/test_routes.py`

**Step 1: 写失败测试**

新增测试：

```python
def test_learning_profile_includes_recent_plan_review_lessons(client):
    ...
```

断言：

- `recent_lessons` 会带出最近策略卡复盘结论
- `pending_plan_summary` 会继续返回待验证数量

**Step 2: 跑测试确认失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "plan_review_lessons" -q
```

Expected: FAIL

**Step 3: 写最小实现**

- `learning.py` 读取 `plan_reviews`
- 混合进 `recent_lessons`
- 为 Expert prompt 增加简短的近期策略卡复盘摘要入口

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "plan_review_lessons" -q
```

Expected: PASS

### Task 7: 前端策略卡复盘交互

**Files:**
- Modify: `frontend/components/plans/TradePlanCard.tsx`
- Modify: `frontend/components/expert/MessageBubble.tsx`
- Modify: `frontend/lib/expertTradePlan.ts`
- Create: `frontend/lib/planReview.ts`
- Create: `frontend/lib/planReview.test.ts`

**Step 1: 写失败测试**

新增测试：

```ts
test("mapPlanReview builds badge and summary from review payload", () => {
  ...
});
```

**Step 2: 跑测试确认失败**

Run:

```bash
node --test frontend/lib/planReview.test.ts
```

Expected: FAIL

**Step 3: 写最小实现**

- 卡片增加“复盘这张卡”按钮
- 调用新的手动复盘接口
- 展示 loading、badge、summary、浮盈/回撤、命中情况
- 保存策略卡时补写 `source_message_id`

**Step 4: 重跑测试确认通过**

Run:

```bash
node --test frontend/lib/planReview.test.ts
```

Expected: PASS

### Task 8: 前端学习栏展示计划复盘结论

**Files:**
- Modify: `frontend/lib/expertLearning.ts`
- Modify: `frontend/components/expert/ExpertLearningRail.tsx`
- Create: `frontend/lib/expertLearning.test.ts`

**Step 1: 写失败测试**

新增测试：

```ts
test("normalizeExpertLearningProfile maps recent plan review lessons into recentLessons", () => {
  ...
});
```

**Step 2: 跑测试确认失败**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts
```

Expected: FAIL

**Step 3: 写最小实现**

- 扩展 learning profile normalizer
- 学习栏显示策略卡复盘带来的 `recentLessons`
- 待验证策略卡计数维持现有底部展示

**Step 4: 重跑测试确认通过**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts frontend/lib/planReview.test.ts
```

Expected: PASS

### Task 9: 回归验证

**Files:**
- Modify: `tests/unit/expert/test_agent.py`
- Modify: `tests/unit/expert/test_routes.py`
- Modify: `tests/unit/test_trade_plans.py`
- Modify: `tests/unit/test_agent_review_memory.py`
- Modify: `frontend/lib/expertLearning.test.ts`
- Modify: `frontend/lib/planReview.test.ts`

**Step 1: 跑后端回归**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert -q
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py -q
```

Expected: PASS

**Step 2: 跑前端回归**

Run:

```bash
node --test frontend/lib/expertLearning.test.ts frontend/lib/planReview.test.ts frontend/lib/expertTradePlan.test.ts
```

Expected: PASS

**Step 3: 手动验证关键路径**

验证：

- 上传图片后，Expert 能根据图中内容回答
- 保存策略卡后，能手动触发复盘
- 右侧学习栏能看到新产生的策略卡复盘结论

**Step 4: 提交实现**

Run:

```bash
git add backend/engine/expert/agent.py backend/llm/context_guard.py backend/engine/agent/db.py backend/engine/agent/models.py backend/engine/agent/service.py backend/engine/agent/routes.py backend/engine/expert/learning.py backend/engine/expert/routes.py backend/engine/expert/tool_tracker.py frontend/components/plans/TradePlanCard.tsx frontend/components/expert/MessageBubble.tsx frontend/components/expert/ExpertLearningRail.tsx frontend/lib/expertTradePlan.ts frontend/lib/planReview.ts tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py frontend/lib/expertLearning.test.ts frontend/lib/planReview.test.ts
git commit -m "feat: add expert plan review and image grounding"
```

Expected: 实现与测试一起提交。
