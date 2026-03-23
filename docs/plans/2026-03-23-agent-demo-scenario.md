# Agent Demo Scenario Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic demo scenario seed plus a one-shot MCP verification tool so the Main Agent evolution loop can be validated end-to-end without relying on live data or real LLM behavior.

**Architecture:** Introduce a dedicated demo scenario seeder that owns cleanup, baseline seeding, and a deterministic demo brain factory; then let the existing verification harness orchestrate `prepare -> run demo brain -> daily review -> weekly review -> diff`, and expose that through two MCP tools.

**Tech Stack:** Python 3, asyncio, DuckDB, FastAPI service layer, pytest, MCP FastMCP wrappers

---

### Task 1: Add failing tests for deterministic demo seeding

**Files:**
- Create: `tests/unit/test_agent_demo_scenarios.py`
- Create: `backend/engine/agent/demo_scenarios.py`

**Step 1: Write the failing tests**

Cover:

- `prepare_scenario("demo-evolution")` creates baseline portfolio/state/watchlist/memories/review records
- running `prepare_scenario()` twice stays idempotent

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_demo_scenarios.py -q`
Expected: FAIL because the module does not exist yet

**Step 3: Write minimal implementation**

Implement only the scenario cleanup + baseline seed needed by the tests.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_demo_scenarios.py -q`
Expected: PASS

### Task 2: Add failing harness test for one-shot demo verification

**Files:**
- Modify: `tests/unit/test_agent_verification.py`
- Modify: `backend/engine/agent/verification.py`

**Step 1: Write the failing test**

Add a test for:

- `verify_demo_cycle("demo-evolution")` returns `pass`
- `seed_summary` exists
- `evolution_diff` shows deterministic evolution evidence

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -q`
Expected: FAIL because demo orchestration does not exist yet

**Step 3: Write minimal implementation**

Add harness entrypoints and inject the demo brain factory.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -q`
Expected: PASS

### Task 3: Add failing MCP wrapper tests for demo tools

**Files:**
- Modify: `tests/unit/mcpserver/test_agent_verification_tools.py`
- Modify: `tests/unit/mcpserver/test_http_transport.py`
- Modify: `backend/mcpserver/agent_verification.py`
- Modify: `backend/mcpserver/server.py`

**Step 1: Write the failing tests**

Cover:

- `prepare_demo_agent_portfolio()` renders seed summary
- `verify_demo_agent_cycle()` renders scenario information plus verification report
- MCP server registers both new tools

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`
Expected: FAIL because wrappers and tool registrations do not exist yet

**Step 3: Write minimal implementation**

Register the new tools and extend rendering just enough to satisfy the tests.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`
Expected: PASS

### Task 4: Harden cleanup boundaries and output contract

**Files:**
- Modify: `backend/engine/agent/demo_scenarios.py`
- Modify: `backend/engine/agent/verification.py`
- Modify: `backend/mcpserver/agent_verification.py`

**Step 1: Limit cleanup to demo-owned rows**

Implementation requirements:

- delete only scenario-tagged or scenario-dated records
- do not truncate shared tables

**Step 2: Keep operator output explicit**

Implementation requirements:

- include `scenario_id`
- include `portfolio_id`
- include `as_of_date`
- include seeded artifact counts

### Task 5: Final verification and commit

**Files:**
- Modify: `docs/plans/2026-03-23-agent-demo-scenario-design.md`
- Modify: `docs/plans/2026-03-23-agent-demo-scenario.md`
- Modify: `backend/engine/agent/demo_scenarios.py`
- Modify: `backend/engine/agent/verification.py`
- Modify: `backend/mcpserver/agent_verification.py`
- Modify: `backend/mcpserver/server.py`
- Modify: `tests/unit/test_agent_demo_scenarios.py`
- Modify: `tests/unit/test_agent_verification.py`
- Modify: `tests/unit/mcpserver/test_agent_verification_tools.py`
- Modify: `tests/unit/mcpserver/test_http_transport.py`

**Step 1: Re-run focused verification**

Run: `python3 -m pytest tests/unit/test_agent_demo_scenarios.py tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`
Expected: PASS

**Step 2: Re-run related backend verification**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -q`
Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-23-agent-demo-scenario-design.md docs/plans/2026-03-23-agent-demo-scenario.md backend/engine/agent/demo_scenarios.py backend/engine/agent/verification.py backend/mcpserver/agent_verification.py backend/mcpserver/server.py tests/unit/test_agent_demo_scenarios.py tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(agent): add demo scenario verification tools"
```
