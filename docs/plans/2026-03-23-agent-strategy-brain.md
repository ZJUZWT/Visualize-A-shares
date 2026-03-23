# Agent Strategy Brain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the fragmented `/agent` middle-column tabs with one integrated Strategy Brain panel built from existing read models.

**Architecture:** Add a dedicated Strategy Brain view-model layer that maps `state`, `runs`, `memory rules`, `reflections`, and `strategy history` into one stable UI contract, then render a single `StrategyBrainPanel` from that contract inside `page.tsx`.

**Tech Stack:** Next.js 15, React 19, TypeScript, Node `node:test`

---

### Task 1: Add failing tests for Strategy Brain view-model

**Files:**
- Create: `frontend/app/agent/lib/strategyBrainViewModel.test.ts`
- Create: `frontend/app/agent/lib/strategyBrainViewModel.ts`

**Step 1: Write the failing tests**

```ts
test("buildStrategyBrainViewModel maps state and active run into snapshot cards", () => {
  const vm = buildStrategyBrainViewModel({ ... });
  assert.equal(vm.snapshot.marketViewLabel, "bullish");
});
```

**Step 2: Run test to verify it fails**

Run: `node --test app/agent/lib/strategyBrainViewModel.test.ts`
Expected: FAIL with missing module or helper

**Step 3: Write minimal implementation**

```ts
export function buildStrategyBrainViewModel(input) {
  return { snapshot: ..., beliefs: [], timeline: [], evolution: ... };
}
```

**Step 4: Run test to verify it passes**

Run: `node --test app/agent/lib/strategyBrainViewModel.test.ts`
Expected: PASS

### Task 2: Expand tests to cover beliefs, timeline, and evolution

**Files:**
- Modify: `frontend/app/agent/lib/strategyBrainViewModel.test.ts`
- Modify: `frontend/app/agent/lib/strategyBrainViewModel.ts`

**Step 1: Write failing tests**

Add cases covering:

- memory rules -> belief cards
- runs -> decision timeline nodes
- reflections + strategy history -> evolution summary
- empty arrays -> safe defaults

**Step 2: Run test to verify it fails**

Run: `node --test app/agent/lib/strategyBrainViewModel.test.ts`
Expected: FAIL because mappings are incomplete

**Step 3: Write minimal implementation**

Implement only the fields needed by the tests.

**Step 4: Run test to verify it passes**

Run: `node --test app/agent/lib/strategyBrainViewModel.test.ts`
Expected: PASS

### Task 3: Implement integrated Strategy Brain panel

**Files:**
- Create: `frontend/app/agent/components/StrategyBrainPanel.tsx`
- Modify: `frontend/app/agent/types.ts`
- Modify: `frontend/app/agent/lib/strategyBrainViewModel.ts`

**Step 1: Add panel sections**

Implementation requirements:

- Brain Snapshot
- Belief Ledger
- Decision Timeline
- Reflection & Evolution

**Step 2: Render concise, high-signal cards**

Implementation requirements:

- show current market view / position level / sector preference / risk alerts
- show confidence bars for beliefs
- show run nodes with decisions and before/after state deltas
- show reflection cards plus strategy evolution nodes

**Step 3: Keep empty/error states explicit**

- no silent blanks
- no raw JSON dumps as the primary presentation

### Task 4: Wire Strategy Brain into `/agent` page

**Files:**
- Modify: `frontend/app/agent/page.tsx`

**Step 1: Replace middle-column tab-first rendering**

Implementation requirements:

- mount `StrategyBrainPanel` as the default middle-column view
- feed it existing loaded data: `agentState`, `runs`, `memoryRules`, `reflectionFeed`, `strategyHistory`
- keep existing data fetching behavior working

**Step 2: Remove now-redundant tab UI from the middle column**

- if a tab state becomes dead, delete it
- if an effect only existed for dead tabs, simplify it

**Step 3: Run focused frontend tests**

Run: `node --test app/agent/lib/strategyBrainViewModel.test.ts app/agent/lib/strategyActionViewModel.test.ts app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

### Task 5: Final verification and commit

**Files:**
- Modify: `docs/plans/2026-03-23-agent-strategy-brain-design.md`
- Modify: `docs/plans/2026-03-23-agent-strategy-brain.md`

**Step 1: Re-run focused verification**

Run: `node --test app/agent/lib/strategyBrainViewModel.test.ts app/agent/lib/strategyActionViewModel.test.ts app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

**Step 2: Commit**

```bash
git add docs/plans/2026-03-23-agent-strategy-brain-design.md docs/plans/2026-03-23-agent-strategy-brain.md frontend/app/agent/components/StrategyBrainPanel.tsx frontend/app/agent/lib/strategyBrainViewModel.ts frontend/app/agent/lib/strategyBrainViewModel.test.ts frontend/app/agent/page.tsx frontend/app/agent/types.ts
git commit -m "feat(agent): add integrated strategy brain panel"
```
