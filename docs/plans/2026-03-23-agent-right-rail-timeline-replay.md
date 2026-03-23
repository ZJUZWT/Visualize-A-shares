# Agent Right Rail Timeline And Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the `/agent` right rail to show the new account equity timeline and daily replay data using the existing backend APIs.

**Architecture:** Keep the current `/agent` page structure, but add two new frontend read models for timeline and replay, fetch them alongside the existing ledger overview, and expand `ExecutionLedgerPanel` into a three-part UI: account snapshot, lightweight SVG equity chart, and date-driven replay card.

**Tech Stack:** Next.js App Router, React client components, TypeScript, existing `/agent` page state, native SVG, Jest/Vitest-style frontend tests already used in the repo

---

### Task 1: Add failing type/normalize tests for timeline and replay data

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Create or Modify: `frontend/app/agent/rightRailTimeline.test.ts`
- Modify: `frontend/app/agent/types.ts`

**Step 1: Write the failing tests**

```ts
it("normalizes equity timeline payload with stable defaults", () => {
  const result = normalizeEquityTimeline("live", {});
  expect(result.mark_to_market).toEqual([]);
  expect(result.realized_only).toEqual([]);
});

it("normalizes replay payload with stable nested defaults", () => {
  const result = normalizeReplaySnapshot("live", {});
  expect(result.positions).toEqual([]);
  expect(result.what_ai_knew.trade_theses).toEqual([]);
});
```

**Step 2: Run test to verify it fails**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts`
Expected: FAIL with missing types or missing normalize helpers

**Step 3: Write minimal implementation**

```ts
export interface AgentEquityTimeline { ... }
export interface AgentReplaySnapshot { ... }
function normalizeEquityTimeline(...) { ... }
function normalizeReplaySnapshot(...) { ... }
```

**Step 4: Run test to verify it passes**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/types.ts frontend/app/agent/page.tsx frontend/app/agent/rightRailTimeline.test.ts
git commit -m "test(agent): cover timeline and replay normalization"
```

### Task 2: Add failing panel rendering tests for chart/replay states

**Files:**
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Create or Modify: `frontend/app/agent/executionLedgerPanel.test.tsx`

**Step 1: Write the failing tests**

```tsx
it("renders both equity curves and replay summary when data exists", () => {
  render(<ExecutionLedgerPanel ... />);
  expect(screen.getByText("Equity Timeline")).toBeInTheDocument();
  expect(screen.getByText("Historical Replay")).toBeInTheDocument();
  expect(screen.getByDisplayValue("2026-03-20")).toBeInTheDocument();
});

it("renders replay error without hiding account overview", () => {
  render(<ExecutionLedgerPanel replayError="boom" ... />);
  expect(screen.getByText("总资产")).toBeInTheDocument();
  expect(screen.getByText("boom")).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `npm test -- frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: FAIL because the panel props and UI do not yet exist

**Step 3: Write minimal implementation**

```tsx
interface ExecutionLedgerPanelProps {
  overview: LedgerOverview | null;
  timeline: AgentEquityTimeline | null;
  replay: AgentReplaySnapshot | null;
  ...
}
```

Add placeholder sections for:

- `Equity Timeline`
- `Historical Replay`

**Step 4: Run test to verify it still fails on content**

Run: `npm test -- frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: FAIL on missing details, proving the test is real

**Step 5: Commit**

```bash
git add frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/executionLedgerPanel.test.tsx
git commit -m "test(agent): add right rail timeline panel coverage"
```

### Task 3: Implement page state and fetching for timeline/replay

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/types.ts`
- Test: `frontend/app/agent/rightRailTimeline.test.ts`

**Step 1: Write failing page-level tests for default replay date logic**

```ts
it("chooses the last timeline day as default replay date", () => {
  const value = pickDefaultReplayDate(timeline, "2026-03-23");
  expect(value).toBe("2026-03-20");
});
```

**Step 2: Run targeted tests to verify they fail**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts`
Expected: FAIL because helper/state logic is missing

**Step 3: Write minimal implementation**

```ts
function pickDefaultReplayDate(...) { ... }
const [equityTimeline, setEquityTimeline] = useState(...)
const [replayDate, setReplayDate] = useState(...)
const [replaySnapshot, setReplaySnapshot] = useState(...)
```

Implementation requirements:

- fetch timeline after `portfolioId` is ready
- derive default replay date from timeline tail
- fetch replay only after replay date exists
- changing date triggers replay refetch only
- timeline and replay errors are isolated

**Step 4: Run tests to verify they pass**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/app/agent/types.ts frontend/app/agent/rightRailTimeline.test.ts
git commit -m "feat(agent): fetch right rail timeline and replay data"
```

### Task 4: Implement the lightweight SVG chart and replay UI

**Files:**
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Test: `frontend/app/agent/executionLedgerPanel.test.tsx`

**Step 1: Write the remaining failing tests**

```tsx
it("shows empty timeline state when no points exist", () => {
  render(<ExecutionLedgerPanel timeline={emptyTimeline} ... />);
  expect(screen.getByText("暂无收益曲线数据")).toBeInTheDocument();
});

it("shows replay action summaries and next day outcome", () => {
  render(<ExecutionLedgerPanel replay={fixtureReplay} ... />);
  expect(screen.getByText("AI Context")).toBeInTheDocument();
  expect(screen.getByText("2.68%")).toBeInTheDocument();
});
```

**Step 2: Run tests to verify they fail**

Run: `npm test -- frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: FAIL on missing chart/replay details

**Step 3: Write minimal implementation**

```tsx
function buildPolylinePoints(...) { ... }
function formatCompactCurrency(...) { ... }
```

Implementation requirements:

- render a native SVG with two polylines
- render latest curve values and delta summary
- render date input with `min` and `max`
- render replay account, positions, trades, plans, AI context, outcome
- keep current account overview and ledger lists below or alongside the new sections

**Step 4: Run tests to verify they pass**

Run: `npm test -- frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/executionLedgerPanel.test.tsx
git commit -m "feat(agent): add right rail equity chart and replay panel"
```

### Task 5: Wire the panel props and verify the integrated page build

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Test: `frontend/app/agent/rightRailTimeline.test.ts`
- Test: `frontend/app/agent/executionLedgerPanel.test.tsx`

**Step 1: Add the final failing integration assertion**

```tsx
it("passes timeline and replay props into the execution panel on runs tab", () => {
  // render page shell or prop adapter and assert contract
});
```

**Step 2: Run tests to verify the integration gap**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: FAIL if props are not fully wired

**Step 3: Write minimal implementation**

Ensure `page.tsx` passes:

- `timeline`
- `timelineLoading`
- `timelineError`
- `replay`
- `replayLoading`
- `replayError`
- `replayDate`
- `timelineBounds`
- `onReplayDateChange`

**Step 4: Run tests to verify they pass**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/rightRailTimeline.test.ts frontend/app/agent/executionLedgerPanel.test.tsx
git commit -m "feat(agent): wire right rail timeline view into agent page"
```

### Task 6: Run focused verification and sync docs

**Files:**
- Modify: `docs/plans/2026-03-23-agent-right-rail-timeline-replay-design.md`
- Modify: `docs/plans/2026-03-23-agent-right-rail-timeline-replay.md`
- Test: `frontend/app/agent/rightRailTimeline.test.ts`
- Test: `frontend/app/agent/executionLedgerPanel.test.tsx`

**Step 1: Run focused verification**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: PASS

**Step 2: Run one broader agent frontend regression command**

Run: `npm test -- frontend/app/agent`
Expected: PASS or a small known set of unrelated failures that must be reported explicitly

**Step 3: Update docs only if implementation diverged**

```md
- adjust displayed fields
- adjust error-state wording
```

**Step 4: Re-run the focused verification**

Run: `npm test -- frontend/app/agent/rightRailTimeline.test.ts frontend/app/agent/executionLedgerPanel.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-03-23-agent-right-rail-timeline-replay-design.md docs/plans/2026-03-23-agent-right-rail-timeline-replay.md frontend/app/agent/page.tsx frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/rightRailTimeline.test.ts frontend/app/agent/executionLedgerPanel.test.tsx
git commit -m "feat(agent): complete right rail timeline and replay ui"
```
