# Agent Demo Structured Summary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a machine-friendly MCP tool that returns a compact JSON summary for demo agent cycle readiness.

**Architecture:** Reuse `verify_demo_cycle()` as the single source of truth, then derive a compact summary object in the MCP wrapper layer and expose it through a dedicated tool registration.

**Tech Stack:** Python 3, JSON, pytest, MCP FastMCP wrappers

---

### Task 1: Add failing tests for structured summary output

**Files:**
- Modify: `tests/unit/mcpserver/test_agent_verification_tools.py`
- Modify: `backend/mcpserver/agent_verification.py`

**Step 1: Write the failing tests**

Add assertions that:

- `get_demo_agent_cycle_summary()` returns JSON
- `ready` is `true` for the seeded pass case
- `proof` and `review_effect` contain the expected fields

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: FAIL because the tool does not exist yet

**Step 3: Write minimal implementation**

Implement summary extraction and JSON rendering only enough to satisfy the test.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: PASS

### Task 2: Add failing transport test for tool registration

**Files:**
- Modify: `tests/unit/mcpserver/test_http_transport.py`
- Modify: `backend/mcpserver/server.py`

**Step 1: Write the failing test**

Assert MCP server registers:

- `get_demo_agent_cycle_summary`

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_http_transport.py -q`
Expected: FAIL because the tool is not registered yet

**Step 3: Write minimal implementation**

Register the new tool in `server.py`.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_http_transport.py -q`
Expected: PASS

### Task 3: Re-run focused verification and inspect real output

**Files:**
- Modify: `backend/mcpserver/agent_verification.py`
- Modify: `backend/mcpserver/server.py`
- Modify: `docs/plans/2026-03-23-agent-demo-structured-summary-design.md`
- Modify: `docs/plans/2026-03-23-agent-demo-structured-summary.md`

**Step 1: Re-run focused verification**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`
Expected: PASS

**Step 2: Inspect real output on isolated temp DB**

Run the local temp-DB script against `get_demo_agent_cycle_summary("demo-evolution")`
Expected: compact JSON with `ready=true`

**Step 3: Commit**

```bash
git add docs/plans/2026-03-23-agent-demo-structured-summary-design.md docs/plans/2026-03-23-agent-demo-structured-summary.md backend/mcpserver/agent_verification.py backend/mcpserver/server.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(agent): add demo cycle summary tool"
```
