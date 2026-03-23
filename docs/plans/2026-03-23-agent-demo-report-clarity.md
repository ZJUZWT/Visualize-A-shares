# Agent Demo Report Clarity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the demo verification report more operator-readable by separating daily review journal growth from weekly reflection growth in `evolution_diff`.

**Architecture:** Replace the coarse `reflections_added` signal with two explicit counters sourced from separate snapshot buckets: `daily_reviews_delta` and `weekly_reflections_delta`. Keep the rest of the verification and demo scenario flow unchanged.

**Tech Stack:** Python 3, DuckDB, pytest, MCP FastMCP wrappers

---

### Task 1: Add failing tests for split reflection counters

**Files:**
- Modify: `tests/unit/test_agent_verification.py`
- Modify: `tests/unit/mcpserver/test_agent_verification_tools.py`

**Step 1: Write the failing tests**

Add assertions that:

- `evolution_diff` exposes `daily_reviews_delta`
- `evolution_diff` exposes `weekly_reflections_delta`
- demo verification returns one of each
- MCP rendering shows the new keys

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: FAIL because the diff still uses `reflections_added`

**Step 3: Write minimal implementation**

Split the snapshot buckets and update diff computation/rendering only enough to satisfy the tests.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: PASS

### Task 2: Re-run focused verification and commit

**Files:**
- Modify: `backend/engine/agent/verification.py`
- Modify: `backend/mcpserver/agent_verification.py`
- Modify: `docs/plans/2026-03-23-agent-demo-report-clarity.md`

**Step 1: Re-run focused verification**

Run: `python3 -m pytest tests/unit/test_agent_demo_scenarios.py tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`
Expected: PASS

**Step 2: Commit**

```bash
git add docs/plans/2026-03-23-agent-demo-report-clarity.md backend/engine/agent/verification.py backend/mcpserver/agent_verification.py tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py
git commit -m "refactor(agent): clarify demo verification diff output"
```
