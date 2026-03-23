# Agent Demo Operator Report Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `verify_demo_agent_cycle` read like an operator-facing demo report by surfacing the outcome and evolution proof at the top.

**Architecture:** Keep the backend verification payload unchanged and only reshape the MCP text renderer. Add a `Summary` section ahead of the existing detail sections, with concise lines for scenario, final status, key evolution proof, and review effect.

**Tech Stack:** Python 3, pytest, MCP FastMCP wrappers

---

### Task 1: Add failing tests for summary-first demo report rendering

**Files:**
- Modify: `tests/unit/mcpserver/test_agent_verification_tools.py`
- Modify: `backend/mcpserver/agent_verification.py`

**Step 1: Write the failing tests**

Add assertions that `verify_demo_agent_cycle()` output includes:

- `Summary` section
- scenario line
- evolution proof line
- review effect line

Also assert the summary appears before `Stages`.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: FAIL because the renderer currently starts with generic sections only

**Step 3: Write minimal implementation**

Implement only the summary-first rendering for demo verification results.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py -q`
Expected: PASS

### Task 2: Re-run focused verification and inspect real output

**Files:**
- Modify: `backend/mcpserver/agent_verification.py`
- Modify: `docs/plans/2026-03-23-agent-demo-operator-report.md`

**Step 1: Re-run focused verification**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`
Expected: PASS

**Step 2: Re-run real demo output on an isolated temp DB**

Run the same local temp-DB script used earlier for `verify_demo_agent_cycle("demo-evolution")`
Expected: output starts with a concise operator summary and still contains the detailed sections below

**Step 3: Commit**

```bash
git add docs/plans/2026-03-23-agent-demo-operator-report.md backend/mcpserver/agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py
git commit -m "refactor(agent): polish demo verification report"
```
