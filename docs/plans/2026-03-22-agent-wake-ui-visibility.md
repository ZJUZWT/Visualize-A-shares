# Agent Wake UI Visibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 `/agent` 中新增 wake 可视化与最小交互，让 `watch_signals` 和 `info_digests` 从后端能力变成前端可见、可维护的控制台能力。

**Architecture:** 保持现有 `/agent` 双栏结构，只新增 `wake` tab。把 wake 的数据归一化、摘要统计、digest 过滤和表单 payload 组装抽到独立 view-model 模块，用纯 `node:test` 做 TDD；页面只负责状态、请求和组件拼装。

**Tech Stack:** Next.js 15, React 19, TypeScript 5.7, Node 24 `node:test`, existing `/api/v1/agent/*` endpoints

---

### Task 1: Add Wake View-Model With Failing Tests

**Files:**
- Create: `frontend/app/agent/lib/wakeViewModel.ts`
- Create: `frontend/app/agent/lib/wakeViewModel.test.ts`
- Modify: `frontend/app/agent/types.ts`

**Step 1: Write the failing test**

Add tests for:

- `normalizeWatchSignals()` parses keywords and trigger evidence safely
- `normalizeInfoDigests()` extracts summary/evidence/risk fields from `structured_summary`
- `filterInfoDigestsForRun()` prefers current run digests and falls back cleanly
- `buildWatchSignalPayload()` trims strings and splits comma keywords

**Step 2: Run test to verify it fails**

Run: `node --test frontend/app/agent/lib/wakeViewModel.test.ts`

Expected: FAIL because the module does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- `WatchSignal`
- `InfoDigest`
- `WakeSummary`
- `normalizeWatchSignals(raw)`
- `normalizeInfoDigests(raw)`
- `summarizeWatchSignals(signals)`
- `filterInfoDigestsForRun(digests, runId, mode)`
- `buildWatchSignalPayload(form)`

Keep it JSON-safe and defensive about mixed backend shapes.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/wakeViewModel.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/types.ts frontend/app/agent/lib/wakeViewModel.ts frontend/app/agent/lib/wakeViewModel.test.ts
git commit -m "test(agent): add wake view-model coverage"
```

---

### Task 2: Add Wake Panels

**Files:**
- Create: `frontend/app/agent/components/WatchSignalsPanel.tsx`
- Create: `frontend/app/agent/components/InfoDigestsPanel.tsx`
- Modify: `frontend/app/agent/types.ts`

**Step 1: Write the failing test**

Use the existing typecheck/build as the failure harness by first wiring imports in the page after the components are referenced but absent.

Run: `./node_modules/.bin/tsc --noEmit`

Expected: FAIL with missing component/type errors.

**Step 3: Write minimal implementation**

Create:

- `WatchSignalsPanel.tsx`
  - summary cards
  - create form
  - watch signal cards
  - status action buttons
- `InfoDigestsPanel.tsx`
  - run/recent toggle
  - digest cards
  - key evidence, risk flags, missing sources

Keep styling aligned with the current `/agent` visual language.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/tsc --noEmit`

Expected: PASS for component/type wiring.

**Step 5: Commit**

```bash
git add frontend/app/agent/components/WatchSignalsPanel.tsx frontend/app/agent/components/InfoDigestsPanel.tsx frontend/app/agent/types.ts
git commit -m "feat(agent): add wake panels"
```

---

### Task 3: Wire Wake Data Flow Into `/agent`

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/types.ts`
- Modify: `frontend/app/agent/lib/wakeViewModel.ts`

**Step 1: Write the failing test**

Extend `wakeViewModel.test.ts` with one more failing case that matches the chosen page behavior:

- selected run with no digests should fall back to recent

Then run:

Run: `node --test frontend/app/agent/lib/wakeViewModel.test.ts`

Expected: FAIL until the filter logic matches the page usage.

**Step 3: Write minimal implementation**

In `page.tsx`:

- add `wake` to `AgentConsoleTab`
- add wake loading/error/form state
- fetch `watch-signals` and `info-digests`
- refresh wake data when entering the tab and after run completion
- wire create / patch handlers
- render `WatchSignalsPanel` in the left content column
- render `InfoDigestsPanel` in the right content column

Do not refactor unrelated tabs.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/wakeViewModel.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/app/agent/types.ts frontend/app/agent/lib/wakeViewModel.ts frontend/app/agent/lib/wakeViewModel.test.ts
git commit -m "feat(agent): surface wake signals and digests"
```

---

### Task 4: Verify End-To-End Frontend Slice

**Files:**
- Modify: `frontend/node_modules` visibility in the worktree if needed
- Review: `frontend/tsconfig.tsbuildinfo` only if build refreshes it

**Step 1: Prepare local verification environment**

If the worktree lacks `frontend/node_modules`, expose the existing dependency directory from the main workspace to the worktree before verification.

**Step 2: Run targeted tests**

Run: `node --test frontend/app/agent/lib/wakeViewModel.test.ts`

Expected: PASS

**Step 3: Run typecheck**

Run: `./node_modules/.bin/tsc --noEmit`

Expected: PASS

**Step 4: Run production build**

Run: `npm run build`

Expected: PASS with `/agent` included in the build output.

**Step 5: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/app/agent/types.ts frontend/app/agent/lib/wakeViewModel.ts frontend/app/agent/lib/wakeViewModel.test.ts frontend/app/agent/components/WatchSignalsPanel.tsx frontend/app/agent/components/InfoDigestsPanel.tsx docs/plans/2026-03-22-agent-wake-ui-visibility-design.md docs/plans/2026-03-22-agent-wake-ui-visibility.md
git commit -m "feat(agent): add wake console visibility"
```
