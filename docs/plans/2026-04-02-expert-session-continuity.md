# Expert Session Continuity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Expert 聊天在断连、用户停止和同专家切换 session 时都能保留 partial 内容，并保证原 session 在后台继续生成。

**Architecture:** 前端把流式状态从“按专家”收敛为“按 session 绑定”；后端新增显式 cancel 接口、消息中断元数据和统一 partial 持久化入口。主回复流与 resume 流统一通过中断原因分类写库，切 session 只切显示，不再中断原流。

**Tech Stack:** FastAPI, DuckDB, Pydantic, Next.js 15, Zustand, TypeScript, pytest, Node `node:test`

---

### Task 1: 后端中断元数据与 cancel API

**Files:**
- Modify: `backend/engine/expert/routes.py`
- Modify: `backend/engine/expert/schemas.py`
- Test: `tests/unit/expert/test_routes.py`

**Step 1: 写失败测试**

新增最小测试：

```python
def test_cancel_endpoint_marks_message_as_user_cancelled(client):
    ...

async def test_chat_cancelled_without_explicit_cancel_marks_client_disconnected(tmp_path):
    ...
```

**Step 2: 跑测试看它失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "user_cancelled or client_disconnected" -v
```

Expected: 因 cancel API 和 interruption metadata 尚未实现而失败。

**Step 3: 写最小实现**

- 为 `expert.messages` 增加中断元数据列
- 新增 cancel request schema
- 新增 `/api/v1/expert/chat/cancel`
- 重构 `_save_partial_message(...)` 支持 reason/detail
- 主 chat 流在 `CancelledError/Exception` 时写入不同原因

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "user_cancelled or client_disconnected" -v
```

Expected: PASS

### Task 2: resume 流复用统一 partial 持久化

**Files:**
- Modify: `backend/engine/expert/routes.py`
- Test: `tests/unit/expert/test_routes.py`

**Step 1: 写失败测试**

新增测试：

```python
async def test_resume_interrupted_updates_existing_message_with_resume_reason(tmp_path):
    ...
```

**Step 2: 跑测试确认失败**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "resume_reason" -v
```

Expected: 因 resume 中断原因字段尚未写入而失败。

**Step 3: 写最小实现**

- resume 中断改走统一更新入口
- 原消息维持同一 `message_id`
- 写入 `resume_interrupted`

**Step 4: 重跑测试确认通过**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "resume_reason" -v
```

Expected: PASS

### Task 3: 前端 session 级流控制

**Files:**
- Modify: `frontend/stores/useExpertStore.ts`
- Modify: `frontend/types/expert.ts`
- Test: `frontend/lib/expertSessionContinuity.test.ts`

**Step 1: 写失败测试**

新增测试：

```ts
test("switching session for same expert does not abort background stream", () => {
  ...
});

test("stream updates only the originating session history", () => {
  ...
});
```

**Step 2: 跑测试确认失败**

Run:

```bash
node --test frontend/lib/expertSessionContinuity.test.ts
```

Expected: 因 store 仍按 expert 维度中止/更新流而失败。

**Step 3: 写最小实现**

- 为流控制器引入 session 绑定
- 把当前流消息定位改成 `sessionId + messageId`
- `switchSession()` 不再 abort 原流
- 仅 `stopStreaming()` 停止当前 session 对应流

**Step 4: 重跑测试确认通过**

Run:

```bash
node --test frontend/lib/expertSessionContinuity.test.ts
```

Expected: PASS

### Task 4: 前端停止生成与中断原因展示

**Files:**
- Modify: `frontend/stores/useExpertStore.ts`
- Modify: `frontend/components/expert/MessageBubble.tsx`
- Modify: `frontend/lib/expertFeedback.ts`
- Test: `frontend/lib/expertFeedback.test.ts`

**Step 1: 写失败测试**

新增测试：

```ts
test("stop streaming reports user_cancelled before abort", () => {
  ...
});

test("feedback helper maps interruption reasons to default issue types", () => {
  ...
});
```

**Step 2: 跑测试确认失败**

Run:

```bash
node --test frontend/lib/expertFeedback.test.ts frontend/lib/expertSessionContinuity.test.ts
```

Expected: 因还未上报 cancel reason / 展示原因文案而失败。

**Step 3: 写最小实现**

- 停止生成前先请求 cancel API
- 消息模型增加 `interruptionReason`
- `PartialBanner` / 反馈默认项根据原因调整

**Step 4: 重跑测试确认通过**

Run:

```bash
node --test frontend/lib/expertFeedback.test.ts frontend/lib/expertSessionContinuity.test.ts
```

Expected: PASS

### Task 5: 回归与文档同步

**Files:**
- Modify: `tests/unit/expert/test_routes.py`
- Modify: `frontend/lib/expertFeedback.test.ts`
- Modify: `docs/plans/2026-04-02-expert-session-continuity-design.md`

**Step 1: 运行后端回归**

Run:

```bash
/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py -q
```

Expected: PASS

**Step 2: 运行前端回归**

Run:

```bash
node --test frontend/lib/expertFeedback.test.ts frontend/lib/clarificationSelection.test.ts frontend/lib/activePortfolio.test.ts frontend/lib/expertLearning.test.ts frontend/lib/expertTradePlan.test.ts frontend/lib/expertSessionContinuity.test.ts
```

Expected: PASS

**Step 3: 检查 diff 格式**

Run:

```bash
git diff --check
```

Expected: PASS

**Step 4: 提交**

```bash
git add backend/engine/expert/routes.py backend/engine/expert/schemas.py tests/unit/expert/test_routes.py frontend/stores/useExpertStore.ts frontend/types/expert.ts frontend/components/expert/MessageBubble.tsx frontend/lib/expertFeedback.ts frontend/lib/expertFeedback.test.ts frontend/lib/expertSessionContinuity.test.ts docs/plans/2026-04-02-expert-session-continuity-design.md docs/plans/2026-04-02-expert-session-continuity.md
git commit -m "fix: keep expert session streams alive across session switches"
```
