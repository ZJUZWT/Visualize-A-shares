# Agent Right Rail Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the remaining `/agent` right-rail timeline/replay interaction polish in one batch.

**Architecture:** Keep the current SVG chart, extend the view-model with a small chart-point summary helper, and add lightweight hover + selection feedback directly inside `ExecutionLedgerPanel`.

**Tech Stack:** Next.js 15, React 19, TypeScript, native SVG, Node `node:test`

---

### Task 1: Add failing helper tests

**Files:**
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.test.ts`
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.ts`

**Step 1: Write the failing tests**

```ts
test("summarizeSelectedEquityPoint returns selected label and values", () => {
  const summary = summarizeSelectedEquityPoint(markPoints, realizedPoints, "2026-03-19");
  assert.equal(summary.date, "2026-03-19");
});
```

**Step 2: Run test to verify it fails**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts`
Expected: FAIL with missing helper

**Step 3: Write minimal implementation**

```ts
export function summarizeSelectedEquityPoint(...) { ... }
```

**Step 4: Run test to verify it passes**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts`
Expected: PASS

### Task 2: Implement batched right-rail polish

**Files:**
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.ts`

**Step 1: Use the helper output in the chart area**

Implementation requirements:

- show `当前回放日期` 文案
- show hover/selected info row with:
  - date
  - mark_to_market equity
  - realized_only equity
- stronger selected-point styling
- slightly smaller transparent hit radius than the previous version

**Step 2: Keep click-to-sync behavior intact**

- clicking either series point still calls `onReplayDateChange(point.date)`
- date input changes still update the selected point

**Step 3: Run tests**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

### Task 3: Final verification and commit

**Files:**
- Modify: `docs/plans/2026-03-23-agent-right-rail-polish-design.md`
- Modify: `docs/plans/2026-03-23-agent-right-rail-polish.md`

**Step 1: Re-run focused verification**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

**Step 2: Commit**

```bash
git add docs/plans/2026-03-23-agent-right-rail-polish-design.md docs/plans/2026-03-23-agent-right-rail-polish.md frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/lib/rightRailTimelineViewModel.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts
git commit -m "feat(agent): polish right rail timeline interactions"
```
