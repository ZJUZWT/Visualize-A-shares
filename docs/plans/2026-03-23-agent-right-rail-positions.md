# Agent Right Rail Position Cards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the `/agent` right rail position area by extending the ledger overview read model with latest strategy metadata and rendering grouped position cards by holding type.

**Architecture:** Enrich `get_ledger_overview()` so `open_positions` includes strategy summary, portfolio weight, and a lightweight status signal; then add a small frontend view-model that groups positions and extracts holding-type-specific card fields for `ExecutionLedgerPanel`.

**Tech Stack:** FastAPI, Python, DuckDB, Next.js 15, React 19, TypeScript, Node `node:test`, pytest

---

### Task 1: Add failing backend tests for enriched ledger overview

**Files:**
- Modify: `tests/unit/test_agent_read_models.py`
- Modify: `backend/engine/agent/service.py`

**Step 1: Write the failing tests**

Add assertions for:

- `open_positions[*].position_pct`
- `open_positions[*].latest_strategy`
- `open_positions[*].status_signal`
- `open_positions[*].status_reason`

Use existing `create_strategy()` setup so the read model is verified against real stored strategy rows.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_read_models.py -q`
Expected: FAIL because enriched fields do not exist yet

**Step 3: Write minimal implementation**

Implement the smallest backend helpers needed to satisfy the test.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_read_models.py -q`
Expected: PASS

### Task 2: Implement backend ledger overview enrichment

**Files:**
- Modify: `backend/engine/agent/service.py`

**Step 1: Load latest strategy per open position**

Implementation requirements:

- latest version only
- normalized `details`
- no N+1 API calls from the frontend

**Step 2: Compute position weight and status signal**

Implementation requirements:

- `position_pct` based on total open position market value
- `status_signal` in `healthy | warning | danger`
- `status_reason` explaining the signal

**Step 3: Keep route contract stable**

- do not remove existing fields
- only enrich `open_positions`

### Task 3: Add failing frontend tests for grouped right-rail positions

**Files:**
- Create: `frontend/app/agent/lib/rightRailPositionViewModel.ts`
- Create: `frontend/app/agent/lib/rightRailPositionViewModel.test.ts`

**Step 1: Write the failing tests**

Cover:

- grouping by `holding_type`
- long/mid/short field extraction from `latest_strategy.details`
- signal label mapping
- no-strategy fallback

**Step 2: Run test to verify it fails**

Run: `node --test app/agent/lib/rightRailPositionViewModel.test.ts`
Expected: FAIL with missing helper

**Step 3: Write minimal implementation**

Implement grouping + card extraction helpers only.

**Step 4: Run test to verify it passes**

Run: `node --test app/agent/lib/rightRailPositionViewModel.test.ts`
Expected: PASS

### Task 4: Render grouped richer position cards in ExecutionLedgerPanel

**Files:**
- Modify: `frontend/app/agent/types.ts`
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Modify: `frontend/app/agent/lib/rightRailPositionViewModel.ts`

**Step 1: Extend frontend ledger position shape**

- latest strategy summary
- status signal + reason
- position_pct

**Step 2: Replace current flat position list**

Implementation requirements:

- group by `holding_type`
- render type header tags
- show general metrics
- show type-specific strategy details
- show signal light and reason

**Step 3: Keep other right-rail sections unchanged**

- account overview
- equity timeline
- replay
- trades / plans area

### Task 5: Final verification and commit

**Files:**
- Modify: `docs/plans/2026-03-23-agent-right-rail-positions-design.md`
- Modify: `docs/plans/2026-03-23-agent-right-rail-positions.md`

**Step 1: Re-run focused verification**

Run: `python3 -m pytest tests/unit/test_agent_read_models.py tests/unit/test_agent_timeline_read_models.py -q`
Expected: PASS

Run: `node --test app/agent/lib/rightRailPositionViewModel.test.ts app/agent/lib/rightRailTimelineViewModel.test.ts app/agent/lib/strategyBrainViewModel.test.ts app/agent/lib/strategyActionViewModel.test.ts app/agent/lib/wakeViewModel.test.ts`
Expected: PASS

Run: `./frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json`
Expected: PASS

**Step 2: Commit**

```bash
git add docs/plans/2026-03-23-agent-right-rail-positions-design.md docs/plans/2026-03-23-agent-right-rail-positions.md backend/engine/agent/service.py tests/unit/test_agent_read_models.py frontend/app/agent/types.ts frontend/app/agent/lib/rightRailPositionViewModel.ts frontend/app/agent/lib/rightRailPositionViewModel.test.ts frontend/app/agent/components/ExecutionLedgerPanel.tsx
git commit -m "feat(agent): enrich right rail position cards"
```
