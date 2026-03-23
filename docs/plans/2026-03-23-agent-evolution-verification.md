# Agent Evolution Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade `verify_agent_cycle` into a backend-first MCP verification loop that proves both execution continuity and observable agent evolution.

**Architecture:** Reuse the existing verification harness, add reusable snapshot collection plus before/after diffing for reviews, memories, reflections, weekly summaries, and strategy history, then expose those new stages and evolution evidence through the MCP renderer.

**Tech Stack:** Python 3, asyncio, DuckDB, FastAPI service layer, pytest, MCP FastMCP wrappers

---

### Task 1: Add failing harness tests for evolution semantics

**Files:**
- Modify: `tests/unit/test_agent_verification.py`
- Modify: `backend/engine/agent/verification.py`

**Step 1: Write the failing tests**

Add tests for:

- completed cycle with no evolution evidence returns `warn`
- completed cycle with weekly review memory/reflection deltas returns `pass`
- result includes `stages` and `evolution_diff`

Use patched `AgentBrain` and `ReviewEngine` implementations so the tests drive only harness behavior.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -q`
Expected: FAIL because `stages` and `evolution_diff` do not exist yet and pass/warn semantics are not implemented

**Step 3: Write minimal implementation**

Implement only the snapshot/diff logic needed for those tests.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -q`
Expected: PASS

### Task 2: Implement reusable snapshot and evolution diff logic

**Files:**
- Modify: `backend/engine/agent/verification.py`

**Step 1: Add reusable snapshot collector**

Snapshot must include:

- `state`
- `latest_run`
- `ledger`
- `review_stats`
- `memories` with `status="all"`
- `strategy_history`
- `reflections`
- `weekly_summaries`

**Step 2: Add structured stage recording**

Stage list must cover:

- `snapshot_before`
- `brain_execute`
- `invariant_check`
- `daily_review`
- `weekly_review`
- `snapshot_after`
- `evolution_diff`

**Step 3: Add evolution diff builder**

Compute:

- count deltas for runs, reviews, weekly summaries, reflections
- memory added/updated/retired counts
- strategy history changed flag
- summary `signals`

### Task 3: Add failing MCP wrapper tests for new report sections

**Files:**
- Modify: `tests/unit/mcpserver/test_agent_verification_tools.py`
- Modify: `backend/mcpserver/agent_verification.py`

**Step 1: Write the failing tests**

Add assertions for:

- `Stages` section exists
- `Evolution Diff` section exists
- diff values render in human-readable form

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: FAIL because renderer does not output the new sections yet

**Step 3: Write minimal implementation**

Extend the MCP wrapper formatting only enough to satisfy the test.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: PASS

### Task 4: Harden result shaping and next actions

**Files:**
- Modify: `backend/engine/agent/verification.py`
- Modify: `backend/mcpserver/agent_verification.py`

**Step 1: Keep failure paths structured**

Ensure all early-return fail paths still include:

- `stages`
- `checks`
- `evidence`
- `next_actions`

**Step 2: Make warn/pass conclusions operator-friendly**

Implementation requirements:

- no evolution evidence => `warn`
- evolution evidence exists => `pass`
- keep `fail` semantics unchanged

### Task 5: Final verification and commit

**Files:**
- Modify: `docs/plans/2026-03-23-agent-evolution-verification-design.md`
- Modify: `docs/plans/2026-03-23-agent-evolution-verification.md`
- Modify: `backend/engine/agent/verification.py`
- Modify: `backend/mcpserver/agent_verification.py`
- Modify: `tests/unit/test_agent_verification.py`
- Modify: `tests/unit/mcpserver/test_agent_verification_tools.py`

**Step 1: Re-run focused verification**

Run: `python3 -m pytest tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/test_http_transport.py -q`
Expected: PASS

**Step 2: Re-run broader backend verification**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -q`
Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-23-agent-evolution-verification-design.md docs/plans/2026-03-23-agent-evolution-verification.md backend/engine/agent/verification.py backend/mcpserver/agent_verification.py tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py
git commit -m "feat(agent): verify evolution cycle via mcp"
```
