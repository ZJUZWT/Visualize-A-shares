# Agent Verification MCP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Main Agent 增加一个验证型 MCP harness，能直接驱动 backend 跑一次真实 agent cycle，并返回 `pass / warn / fail` 结论与关键证据。

**Architecture:** 在 `backend/engine/agent` 下新增一个验证 orchestration 模块，直接调用 `AgentService`、`AgentBrain`、`ReviewEngine` 完成单次验证，再在 `backend/mcpserver` 下新增轻量 wrapper 把结构化结果格式化成 AI 友好的 Markdown。第一批只交付 `verify_agent_cycle` 和 `inspect_agent_snapshot`，不引入 memo 边界验证。

**Tech Stack:** Python 3.11, pytest, FastMCP, existing `AgentBrain`, `AgentService`, `ReviewEngine`, DuckDB-backed agent tables

---

### Task 1: Add Failing Tests For Verification Harness Core

**Files:**
- Create: `backend/engine/agent/verification.py`
- Create: `tests/unit/test_agent_verification.py`

**Step 1: Write the failing test**

Add tests covering:

- `verify_cycle()` returns `pass` when a run completes and invariants hold
- `verify_cycle()` returns `warn` when run completes but has zero candidates / zero trades
- `verify_cycle()` returns `fail` when `brain_run.status == "failed"`
- `inspect_snapshot()` aggregates `state`, latest `brain_run`, `ledger_overview`, `review_stats`, and `memories`

Example skeleton:

```python
def test_verify_cycle_passes_when_brain_run_and_review_complete(tmp_path):
    verifier = AgentVerificationHarness(...)
    result = run(verifier.verify_cycle("live"))
    assert result["verification_status"] == "pass"
    assert result["failed_stage"] is None
    assert any(check["name"] == "brain_run_completed" for check in result["checks"])


def test_verify_cycle_warns_when_completed_without_trades(tmp_path):
    verifier = AgentVerificationHarness(...)
    result = run(verifier.verify_cycle("live", require_trade=False))
    assert result["verification_status"] == "warn"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -q`

Expected: FAIL because the module does not exist yet.

**Step 3: Write minimal implementation**

Create `AgentVerificationHarness` with async methods:

- `verify_cycle(...)`
- `inspect_snapshot(...)`

Inside `verify_cycle(...)`:

- create `brain_run`
- execute `AgentBrain` under `asyncio.wait_for`
- optionally call `ReviewEngine.daily_review()`
- collect checks and evidence
- classify `pass / warn / fail`

Keep output as plain dict; do not format Markdown here.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/verification.py tests/unit/test_agent_verification.py
git commit -m "feat(agent): add verification harness"
```

---

### Task 2: Tighten Failure Stages And Invariant Checks

**Files:**
- Modify: `backend/engine/agent/verification.py`
- Modify: `tests/unit/test_agent_verification.py`

**Step 1: Write the failing test**

Add explicit tests for:

- timeout returns `fail` with `failed_stage == "brain_execute"`
- missing `state_after` returns `fail`
- mismatched `trade_ids` vs DB returns `fail`
- review error returns `fail` when `include_review=True`

Example skeleton:

```python
def test_verify_cycle_fails_when_state_after_missing(tmp_path):
    result = run(verifier.verify_cycle("live"))
    assert result["verification_status"] == "fail"
    assert result["failed_stage"] == "invariant_check"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -k "timeout or invariant or review" -q`

Expected: FAIL because the first implementation will not yet classify these cases strictly enough.

**Step 3: Write minimal implementation**

In `verification.py`:

- split the flow into explicit stages:
  - `brain_run_create`
  - `brain_execute`
  - `review_daily`
  - `invariant_check`
- add invariant helpers for:
  - `state_before_present`
  - `state_after_present`
  - `execution_summary_present`
  - `plan_ids_consistent`
  - `trade_ids_consistent`
- preserve partial evidence on failure

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_verification.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/verification.py tests/unit/test_agent_verification.py
git commit -m "feat(agent): add verification invariants"
```

---

### Task 3: Add MCP Wrapper And Tool Registration

**Files:**
- Create: `backend/mcpserver/agent_verification.py`
- Modify: `backend/mcpserver/server.py`
- Create: `tests/unit/mcpserver/test_agent_verification_tools.py`
- Modify: `tests/unit/mcpserver/test_http_transport.py`

**Step 1: Write the failing test**

Add tests for:

- `verify_agent_cycle` wrapper returns Markdown containing status, run id, and failed stage
- `inspect_agent_snapshot` wrapper returns Markdown with state / ledger / review sections
- MCP server registers the new tools

Example skeleton:

```python
@pytest.mark.asyncio
async def test_verify_agent_cycle_tool_formats_result(monkeypatch):
    monkeypatch.setattr(..., "verify_cycle", fake_verify_cycle)
    text = await verify_agent_cycle("live")
    assert "verification_status" in text.lower() or "PASS" in text


def test_mcp_tools_registered():
    from mcpserver.server import server
    tools = server._tool_manager._tools
    assert "verify_agent_cycle" in tools
    assert "inspect_agent_snapshot" in tools
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: FAIL because the wrapper module and server registrations do not exist yet.

**Step 3: Write minimal implementation**

In `backend/mcpserver/agent_verification.py`:

- instantiate harness lazily
- provide async wrapper functions:
  - `verify_agent_cycle(...)`
  - `inspect_agent_snapshot(...)`
- format dict results to Markdown with:
  - summary
  - checks table
  - evidence summary
  - next actions

In `backend/mcpserver/server.py`:

- import the new wrapper module
- register two new `@server.tool()` functions

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/mcpserver/agent_verification.py backend/mcpserver/server.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(mcp): expose agent verification tools"
```

---

### Task 4: Run Focused Regression Suite

**Files:**
- Review only: touched files from previous tasks

**Step 1: Run new focused tests**

Run: `python3 -m pytest tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py -q`

Expected: PASS

**Step 2: Run agent and MCP regression suite**

Run: `python3 -m pytest tests/unit/test_agent_phase1a.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_review_read_models.py tests/unit/mcpserver/test_http_transport.py tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add backend/engine/agent/verification.py backend/mcpserver/agent_verification.py backend/mcpserver/server.py tests/unit/test_agent_verification.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_http_transport.py docs/plans/2026-03-23-agent-verification-mcp-design.md docs/plans/2026-03-23-agent-verification-mcp.md
git commit -m "feat(agent): add verification mcp harness"
```

