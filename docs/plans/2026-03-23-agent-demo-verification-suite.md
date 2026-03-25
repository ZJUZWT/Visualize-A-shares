# Agent Demo Verification Suite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 MCP 增加一个统一验证入口，一次调用就能完成 demo 闭环验证和短窗口 backtest，并返回机器可消费的统一 JSON 结果；同时提供显式 `smoke_mode` 让这条链路能稳定做工程验收。

**Architecture:** 在 `backend/mcpserver` 的 suite wrapper 中继续复用现有 `AgentVerificationHarness.verify_demo_cycle()`、`AgentBacktestEngine.run_backtest()` 和 `get_run_summary()`，在 MCP 层完成状态归并、默认窗口推导和统一输出。新增的 `smoke_mode` 只在 suite 内临时切换到 deterministic smoke data/brain，不改 backend core harness 或 backtest engine 的默认行为。`server.py` 只负责 tool 注册，不新增 backend engine 层抽象。

**Tech Stack:** Python 3.11, pytest, FastMCP, existing `AgentVerificationHarness`, existing `AgentBacktestEngine`, DuckDB-backed agent tables

---

### Task 1: Add Failing Tests For Suite Contract

**Files:**
- Create: `backend/mcpserver/agent_verification_suite.py`
- Create: `tests/unit/mcpserver/test_agent_verification_suite_tools.py`

**Step 1: Write the failing test**

Add tests covering:

- suite 默认按 `verify_demo_cycle -> run_backtest -> get_run_summary` 顺序执行
- 默认 backtest 日期来自 `seed_summary.week_start` 和 `seed_summary.as_of_date`
- 返回结果包含 `overall_status`、`demo_verification`、`backtest`、`evidence`

Example skeleton:

```python
@pytest.mark.asyncio
async def test_run_demo_agent_verification_suite_returns_pass_json(monkeypatch):
    suite = _import_backend_module("mcpserver.agent_verification_suite")

    class FakeHarness:
        async def verify_demo_cycle(self, scenario_id: str, timeout_seconds: int = 30):
            return {
                "verification_status": "pass",
                "run_id": "verify-1",
                "portfolio_id": "demo-evolution",
                "seed_summary": {
                    "scenario_id": "demo-evolution",
                    "portfolio_id": "demo-evolution",
                    "week_start": "2042-01-05",
                    "as_of_date": "2042-01-10",
                },
                "evolution_diff": {
                    "review_records_delta": 1,
                    "daily_reviews_delta": 1,
                    "weekly_reflections_delta": 1,
                    "weekly_summaries_delta": 1,
                },
            }

    class FakeEngine:
        async def run_backtest(self, **kwargs):
            assert kwargs["start_date"] == "2042-01-05"
            assert kwargs["end_date"] == "2042-01-10"
            return {"id": "bt-1", "status": "completed"}

        async def get_run_summary(self, run_id: str):
            assert run_id == "bt-1"
            return {"run_id": "bt-1", "status": "completed", "trade_count": 2, "review_count": 3}

    monkeypatch.setattr(suite, "_get_harness", lambda: FakeHarness())
    monkeypatch.setattr(suite, "_get_engine", lambda: FakeEngine())

    text = await suite.run_demo_agent_verification_suite()
    data = json.loads(text)
    assert data["overall_status"] == "pass"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_suite_tools.py -q`

Expected: FAIL because the suite module does not exist yet.

**Step 3: Write minimal implementation**

Create `backend/mcpserver/agent_verification_suite.py` with:

- lazy `_get_harness()` reusing `AgentDB`
- lazy `_get_engine()`
- helper to compute backtest window
- helper to merge status and next actions
- async `run_demo_agent_verification_suite(...)` returning JSON string

Reuse:

- `mcpserver.agent_verification._build_demo_cycle_summary`

Do not parse markdown from existing tools.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_suite_tools.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/mcpserver/agent_verification_suite.py tests/unit/mcpserver/test_agent_verification_suite_tools.py
git commit -m "feat(mcp): add demo verification suite tool"
```

---

### Task 2: Tighten Status Aggregation And Failure Evidence

**Files:**
- Modify: `backend/mcpserver/agent_verification_suite.py`
- Modify: `tests/unit/mcpserver/test_agent_verification_suite_tools.py`

**Step 1: Write the failing test**

Add tests covering:

- demo verification `warn` makes suite `warn`
- backtest weak signals (`trade_count == 0` or `review_count == 0`) make suite `warn`
- backtest exception makes suite `fail`
- demo verification `fail` short-circuits and does not call backtest

Example skeleton:

```python
@pytest.mark.asyncio
async def test_suite_fails_and_skips_backtest_when_demo_verification_fails(monkeypatch):
    ...
    assert data["overall_status"] == "fail"
    assert data["backtest"]["status"] == "skipped"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_suite_tools.py -q`

Expected: FAIL because the initial implementation will not yet cover all status edges.

**Step 3: Write minimal implementation**

In `agent_verification_suite.py`:

- add `fail` short-circuit when demo verification fails
- preserve `verification_run_id` even when backtest fails
- add `warn` heuristics for:
  - `trade_count == 0`
  - `review_count == 0`
  - no memory movement
- add `next_actions` messages tied to each warning/failure path

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_suite_tools.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/mcpserver/agent_verification_suite.py tests/unit/mcpserver/test_agent_verification_suite_tools.py
git commit -m "feat(mcp): add suite status aggregation"
```

---

### Task 3: Register The MCP Tool

**Files:**
- Modify: `backend/mcpserver/server.py`
- Modify: `tests/unit/mcpserver/test_http_transport.py`

**Step 1: Write the failing test**

Add a registration assertion:

```python
def test_agent_suite_tool_registered():
    from mcpserver.server import server
    tools = server._tool_manager._tools
    assert "run_demo_agent_verification_suite" in tools
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_http_transport.py -q`

Expected: FAIL because the tool is not registered yet.

**Step 3: Write minimal implementation**

In `backend/mcpserver/server.py`:

- import `agent_verification_suite`
- register async tool:
  - `run_demo_agent_verification_suite(...)`

Keep the docstring explicit that this is a unified demo verification + backtest suite.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/mcpserver/server.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(mcp): register demo verification suite tool"
```

---

### Task 4: Run Focused Regression Suite

**Files:**
- Review only: touched files from previous tasks

**Step 1: Run suite-specific tests**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_suite_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 2: Run broader agent regression tests**

Run: `python3 -m pytest tests/unit/test_agent_verification.py tests/unit/test_agent_backtest.py tests/unit/mcpserver/test_agent_verification_tools.py tests/unit/mcpserver/test_agent_backtest_tools.py tests/unit/mcpserver/test_agent_verification_suite_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-23-agent-demo-verification-suite-design.md docs/plans/2026-03-23-agent-demo-verification-suite.md backend/mcpserver/agent_verification_suite.py backend/mcpserver/server.py tests/unit/mcpserver/test_agent_verification_suite_tools.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(mcp): add demo verification suite"
```

---

### Task 5: Add Explicit Smoke Mode For Stable Suite Smoke Runs

**Files:**
- Modify: `backend/mcpserver/agent_verification_suite.py`
- Modify: `backend/mcpserver/server.py`
- Modify: `tests/unit/mcpserver/test_agent_verification_suite_tools.py`

**Step 1: Write the failing test**

Add tests covering:

- `smoke_mode=True` returns `mode == "smoke"`
- `smoke_mode=True` uses smoke default dates when caller does not pass backtest dates
- `smoke_mode=False` keeps existing behavior

Example skeleton:

```python
@pytest.mark.asyncio
async def test_run_demo_agent_verification_suite_smoke_mode_uses_smoke_defaults(monkeypatch):
    ...
    text = await suite.run_demo_agent_verification_suite(smoke_mode=True)
    data = json.loads(text)
    assert data["mode"] == "smoke"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_suite_tools.py -q`

Expected: FAIL because the suite does not yet expose or honor `smoke_mode`.

**Step 3: Write minimal implementation**

In `backend/mcpserver/agent_verification_suite.py`:

- add `smoke_mode: bool = False`
- add top-level `mode` field to result
- when `smoke_mode=True`, use suite-local deterministic smoke backtest env
- keep `verify_demo_cycle()` on the real path

In `backend/mcpserver/server.py`:

- expose the new parameter on the MCP tool registration

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_verification_suite_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/mcpserver/agent_verification_suite.py backend/mcpserver/server.py tests/unit/mcpserver/test_agent_verification_suite_tools.py docs/plans/2026-03-23-agent-demo-verification-suite-design.md docs/plans/2026-03-23-agent-demo-verification-suite.md
git commit -m "feat(mcp): add suite smoke mode"
```
