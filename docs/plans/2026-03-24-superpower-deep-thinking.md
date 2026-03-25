# Superpower Deep Thinking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `expert` 对话链路中的投资顾问与短线专家增加 clarification、thinking out loud 和 self critique，使深度思考模式变成可交互的深度问答流程。

**Architecture:** 采用 `POST /expert/clarify/{expert_type}` 独立生成澄清选项，前端在用户选择后再发起原有 `chat` SSE；后端在 `chat` 中新增 `reasoning_summary` 与 `self_critique` 结构化事件，前端把 clarification、推理摘要、自我质疑统一落到 `thinking` 面板与消息持久化中。

**Tech Stack:** Python 3.11, FastAPI, Pydantic, Next.js, TypeScript, Zustand, pytest

---

### Task 1: Add failing schema and route tests for clarification flow

**Files:**
- Modify: `tests/unit/expert/test_routes.py`
- Modify: `tests/unit/expert/test_agent.py`
- Modify: `backend/engine/expert/schemas.py`

**Step 1: Write the failing test**

Add tests covering:

- clarification request/response models can be instantiated
- `POST /api/v1/expert/clarify/rag` returns summary + options + skip option
- invalid expert type or missing agent returns controlled error payload

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py -q`

Expected: FAIL because clarification models and route do not exist.

**Step 3: Write minimal implementation**

In `backend/engine/expert/schemas.py`:

- add clarification models
- add chat request extension for clarification selection
- add self critique model

In `backend/engine/expert/routes.py`:

- add `POST /clarify/{expert_type}`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py backend/engine/expert/schemas.py backend/engine/expert/routes.py
git commit -m "feat(expert): add clarification API contract"
```

### Task 2: Add failing backend tests for reasoning summary and self critique events

**Files:**
- Modify: `tests/unit/expert/test_agent.py`
- Modify: `backend/engine/expert/agent.py`

**Step 1: Write the failing test**

Add coverage proving:

- `agent.chat()` emits `reasoning_summary` when `ThinkOutput.reasoning` is present
- `agent.chat()` emits `self_critique` before `reply_complete`
- clarification selection affects the prompt context sent into chat

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/expert/test_agent.py -q`

Expected: FAIL because the new events and request shaping do not exist.

**Step 3: Write minimal implementation**

In `backend/engine/expert/agent.py`:

- add `clarify()` helper
- add clarification-context builder
- add lightweight `_self_critique()` step
- emit `reasoning_summary` and `self_critique` events

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/expert/test_agent.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/expert/test_agent.py backend/engine/expert/agent.py
git commit -m "feat(expert): stream reasoning summary and self critique"
```

### Task 3: Add failing frontend type/store tests or compile-safe changes for clarification state

**Files:**
- Modify: `frontend/types/expert.ts`
- Modify: `frontend/stores/useExpertStore.ts`
- Modify: `frontend/components/expert/ChatArea.tsx`
- Modify: `frontend/components/expert/MessageBubble.tsx`
- Modify: `frontend/components/expert/ThinkingPanel.tsx`
- Modify: `frontend/components/expert/InputBar.tsx`

**Step 1: Write the failing change**

Introduce types and state expectations for:

- clarification request item
- pending clarification state per expert
- selection submission path
- reasoning summary and self critique rendering

If there are existing frontend tests, extend them; otherwise ensure TypeScript will fail until the types are wired through.

**Step 2: Run validation to verify it fails**

Run: `npm run lint` or project TypeScript check command used in this repo

Expected: FAIL until the new types and state flow are fully wired.

**Step 3: Write minimal implementation**

Implement:

- store state machine for `clarify -> wait selection -> chat`
- clarification option card with `A/B/C/D + 跳过`
- thinking panel rendering for `reasoning_summary` and `self_critique`
- input locking while awaiting clarification or streaming

**Step 4: Run validation to verify it passes**

Run: `npm run lint` or matching frontend validation command

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/types/expert.ts frontend/stores/useExpertStore.ts frontend/components/expert/ChatArea.tsx frontend/components/expert/MessageBubble.tsx frontend/components/expert/ThinkingPanel.tsx frontend/components/expert/InputBar.tsx
git commit -m "feat(expert-ui): add clarification and critique thinking states"
```

### Task 4: Run focused regressions and update TODO

**Files:**
- Modify: `TODO.md`
- Review only: all touched expert files

**Step 1: Run backend regressions**

Run: `python3 -m pytest tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py tests/unit/expert/test_scheduler.py -q`

Expected: PASS

**Step 2: Run frontend validation**

Run: `npm run lint`

Expected: PASS

**Step 3: Update TODO**

Mark complete only if the implementation proves:

- `Clarification Phase`
- `Thinking Out Loud`
- `Self-Critique`

**Step 4: Run final verification**

Run: `python3 -m pytest tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py tests/unit/expert/test_scheduler.py -q`

Run: `npm run lint`

Expected: PASS

**Step 5: Commit**

```bash
git add TODO.md backend/engine/expert/schemas.py backend/engine/expert/agent.py backend/engine/expert/routes.py frontend/types/expert.ts frontend/stores/useExpertStore.ts frontend/components/expert/ChatArea.tsx frontend/components/expert/MessageBubble.tsx frontend/components/expert/ThinkingPanel.tsx frontend/components/expert/InputBar.tsx tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py
git commit -m "feat(expert): complete superpower deep thinking module"
```
