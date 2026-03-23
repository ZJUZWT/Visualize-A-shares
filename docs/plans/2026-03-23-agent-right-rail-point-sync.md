# Agent Right Rail Point Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users click a date point on the `/agent` equity chart to switch the historical replay date and show the selected point highlight.

**Architecture:** Keep the existing right-rail timeline/replay flow, add a pure chart-point helper in the timeline view-model for coordinates and selection state, then render clickable SVG circles in `ExecutionLedgerPanel` that reuse the existing `onReplayDateChange`.

**Tech Stack:** Next.js 15, React 19, TypeScript, native SVG, Node `node:test`

---

### Task 1: Add failing chart-point helper tests

**Files:**
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.test.ts`
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.ts`

**Step 1: Write the failing tests**

```ts
test("buildEquityChartPoints marks the selected date", () => {
  const points = buildEquityChartPoints(series, 320, 120, "2026-03-19");
  assert.equal(points[1].isSelected, true);
});

test("buildEquityChartPoints returns empty array for empty series", () => {
  assert.deepEqual(buildEquityChartPoints([], 320, 120, "2026-03-19"), []);
});
```

**Step 2: Run test to verify it fails**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts`
Expected: FAIL with missing helper

**Step 3: Write minimal implementation**

```ts
export function buildEquityChartPoints(...) { ... }
```

**Step 4: Run test to verify it passes**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/lib/rightRailTimelineViewModel.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts
git commit -m "test(agent): cover timeline point sync model"
```

### Task 2: Implement clickable points in the SVG chart

**Files:**
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.ts`

**Step 1: Add the minimal failing expectation in the helper test**

```ts
test("buildEquityChartPoints keeps date and equity on the point model", () => {
  const points = buildEquityChartPoints(series, 320, 120, "2026-03-19");
  assert.equal(points[0].date, "2026-03-18");
  assert.equal(points[0].equity, 1000000);
});
```

**Step 2: Run test to verify it fails if the model is incomplete**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts`
Expected: FAIL if fields are missing

**Step 3: Write minimal implementation**

Implementation requirements:

- compute point array for `mark_to_market`
- compute point array for `realized_only`
- render visible points for both series
- render a larger transparent click target
- selected date gets larger circle / stroke
- click calls `onReplayDateChange(point.date)`

**Step 4: Run test to verify helper stays green**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/lib/rightRailTimelineViewModel.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts
git commit -m "feat(agent): sync replay date from chart points"
```

### Task 3: Run focused verification and sync docs

**Files:**
- Modify: `docs/plans/2026-03-23-agent-right-rail-point-sync-design.md`
- Modify: `docs/plans/2026-03-23-agent-right-rail-point-sync.md`
- Test: `frontend/app/agent/lib/rightRailTimelineViewModel.test.ts`
- Test: `frontend/app/agent/lib/wakeViewModel.test.ts`

**Step 1: Run focused verification**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

**Step 2: Update docs only if implementation diverged**

```md
- adjust point-hit behavior
- adjust highlight behavior
```

**Step 3: Re-run focused verification**

Run: `node --test app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

**Step 4: Commit**

```bash
git add docs/plans/2026-03-23-agent-right-rail-point-sync-design.md docs/plans/2026-03-23-agent-right-rail-point-sync.md frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/lib/rightRailTimelineViewModel.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts
git commit -m "feat(agent): add point sync to timeline replay"
```
