# Agent Chat Action Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the `/agent` left-chat strategy card flow so adopt/reject mutates the virtual portfolio while save still writes only to memo inbox.

**Architecture:** Keep the existing backend execution routes, split frontend state into execution actions and memo actions, and update the chat strategy card so the three user actions share one UI but persist into two different data flows.

**Tech Stack:** Next.js 15, React 19, TypeScript, FastAPI, pytest, Node `node:test`

---

### Task 1: Add failing frontend tests for split action semantics

**Files:**
- Create: `frontend/app/agent/lib/strategyActionViewModel.test.ts`
- Create: `frontend/app/agent/lib/strategyActionViewModel.ts`

**Step 1: Write the failing tests**

```ts
test("mergeStrategyCardState keeps execution and memo badges independent", () => {
  const result = mergeStrategyCardState(executionState, memoState);
  assert.equal(result.executionLabel, "已采纳");
  assert.equal(result.memoLabel, "已收藏");
});
```

**Step 2: Run test to verify it fails**

Run: `node --test app/agent/lib/strategyActionViewModel.test.ts`
Expected: FAIL with missing module or helper

**Step 3: Write minimal implementation**

```ts
export function mergeStrategyCardState(...) {
  return { ... };
}
```

**Step 4: Run test to verify it passes**

Run: `node --test app/agent/lib/strategyActionViewModel.test.ts`
Expected: PASS

### Task 2: Add failing frontend tests for request routing

**Files:**
- Modify: `frontend/app/agent/lib/strategyActionViewModel.test.ts`
- Modify: `frontend/app/agent/lib/strategyActionViewModel.ts`

**Step 1: Write the failing tests**

Add cases covering:

- adopt request payload goes to `/api/v1/agent/adopt-strategy`
- reject request payload goes to `/api/v1/agent/reject-strategy`
- save request payload still maps to `/api/v1/agent/strategy-memos`

**Step 2: Run test to verify it fails**

Run: `node --test app/agent/lib/strategyActionViewModel.test.ts`
Expected: FAIL because route helper does not exist

**Step 3: Write minimal implementation**

```ts
export function buildStrategyActionRequest(...) {
  return { endpoint, method, body };
}
```

**Step 4: Run test to verify it passes**

Run: `node --test app/agent/lib/strategyActionViewModel.test.ts`
Expected: PASS

### Task 3: Implement split action state in `/agent`

**Files:**
- Modify: `frontend/app/agent/types.ts`
- Modify: `frontend/app/agent/components/AgentStrategyActionCard.tsx`
- Modify: `frontend/app/agent/components/AgentChatMessage.tsx`
- Modify: `frontend/app/agent/components/AgentChatPanel.tsx`
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/lib/strategyActionViewModel.ts`

**Step 1: Add execution and memo state types**

Implementation requirements:

- separate execution decision from memo decision
- keep the existing lookup key contract
- support combined card status display

**Step 2: Update chat card UI**

Implementation requirements:

- show `采纳` / `忽略` / `收藏到备忘录`
- show execution badge independently from memo badge
- lock only the relevant buttons after each action
- keep ignore reason prompt

**Step 3: Update page data loading and handlers**

Implementation requirements:

- fetch strategy actions per session
- keep fetching memo actions per session
- on send / session switch, refresh both sets
- route adopt/reject/save to the correct endpoints
- keep memo inbox behavior unchanged

**Step 4: Run focused frontend tests**

Run: `node --test app/agent/lib/strategyActionViewModel.test.ts app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

### Task 4: Run backend regression tests for execution contract

**Files:**
- Modify: `tests/unit/test_agent_strategy_actions.py` (only if coverage gap is found)

**Step 1: Run existing backend tests first**

Run: `python3 -m pytest tests/unit/test_agent_strategy_actions.py -q`
Expected: PASS

**Step 2: Add a failing backend regression test only if needed**

Only add a new test if the frontend changes expose a missing contract or unstable shape.

**Step 3: Re-run backend tests**

Run: `python3 -m pytest tests/unit/test_agent_strategy_actions.py -q`
Expected: PASS

### Task 5: Final verification and commit

**Files:**
- Modify: `docs/plans/2026-03-23-agent-chat-action-split-design.md`
- Modify: `docs/plans/2026-03-23-agent-chat-action-split.md`

**Step 1: Re-run focused verification**

Run: `node --test app/agent/lib/strategyActionViewModel.test.ts app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

Run: `python3 -m pytest tests/unit/test_agent_strategy_actions.py tests/unit/test_agent_strategy_memos.py -q`
Expected: PASS

**Step 2: Commit**

```bash
git add docs/plans/2026-03-23-agent-chat-action-split-design.md docs/plans/2026-03-23-agent-chat-action-split.md frontend/app/agent/types.ts frontend/app/agent/components/AgentStrategyActionCard.tsx frontend/app/agent/components/AgentChatMessage.tsx frontend/app/agent/components/AgentChatPanel.tsx frontend/app/agent/page.tsx frontend/app/agent/lib/strategyActionViewModel.ts frontend/app/agent/lib/strategyActionViewModel.test.ts
git commit -m "feat(agent): split chat execution and memo actions"
```
