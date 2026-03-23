# Agent Backtest Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Main Agent 增加一个日级事件驱动的历史回测引擎，能在隔离 portfolio 中按天推进 agent 的分析、执行、复盘与记忆演化，并通过 API 与 MCP 暴露结果。

**Architecture:** 新增 `AgentBacktestEngine` 编排层与独立 `backtest_runs / backtest_days` 数据模型，复用现有 `AgentService`、`AgentBrain`、`ReviewEngine` 写路径，在一个隔离的 backtest portfolio 中逐交易日推进。所有市场数据读取都通过历史上下文适配器限制在 `as_of_date`，首版只支持 `next_open` 与 `same_close` 两种成交模式。

**Tech Stack:** Python 3.11, pytest, FastAPI, FastMCP, DuckDB, existing `AgentDB`, `AgentService`, `AgentBrain`, `ReviewEngine`

---

### Task 1: Add Failing Tests For Backtest Storage And Run Bootstrap

**Files:**
- Create: `tests/unit/test_agent_backtest.py`
- Modify: `backend/engine/agent/db.py`
- Create: `backend/engine/agent/backtest.py`

**Step 1: Write the failing test**

Add tests covering:

- `AgentDB` creates `agent.backtest_runs` and `agent.backtest_days`
- `AgentBacktestEngine.start_run(...)` creates a `backtest_run`
- source portfolio is copied into isolated `bt:{run_id}` portfolio

Example skeleton:

```python
def test_start_run_creates_isolated_backtest_portfolio():
    engine = AgentBacktestEngine(db=db, service=svc)
    run_record = run(
        engine.start_run(
            portfolio_id="live",
            start_date="2026-03-18",
            end_date="2026-03-21",
            execution_price_mode="next_open",
        )
    )
    assert run_record["source_portfolio_id"] == "live"
    assert run_record["backtest_portfolio_id"].startswith("bt:")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "isolated_backtest_portfolio or backtest_runs" -q`

Expected: FAIL because the tables and engine do not exist yet.

**Step 3: Write minimal implementation**

In `backend/engine/agent/db.py` add tables:

- `agent.backtest_runs`
- `agent.backtest_days`

In `backend/engine/agent/backtest.py` create:

- `class AgentBacktestEngine`
- `async def start_run(...) -> dict`

Minimal behavior:

- validate source portfolio exists
- create `run_id`
- create `backtest_portfolio_id = f"bt:{run_id}"`
- create isolated portfolio row with copied capital and dates
- insert `backtest_runs` row with `status="running"`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "isolated_backtest_portfolio or backtest_runs" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/backtest.py tests/unit/test_agent_backtest.py
git commit -m "feat(agent): add backtest run bootstrap"
```

---

### Task 2: Add Failing Tests For Daily Progression And Execution Price Modes

**Files:**
- Modify: `tests/unit/test_agent_backtest.py`
- Modify: `backend/engine/agent/backtest.py`
- Optional reference: `backend/engine/agent/service.py`

**Step 1: Write the failing test**

Add tests covering:

- daily progression writes one `backtest_day` per simulated trading day
- `same_close` uses same-day close as execution price
- `next_open` uses next available trading day open as execution price

Example skeleton:

```python
def test_run_backtest_writes_daily_rows_for_each_trade_day():
    result = run(engine.run_backtest(...))
    assert result["status"] == "completed"
    assert len(result["days"]) == 3


def test_next_open_execution_uses_next_day_open():
    result = run(engine.run_backtest(..., execution_price_mode="next_open"))
    assert result["days"][0]["trade_count"] >= 1
    assert result["trades"][0]["price"] == 101.0
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "trade_day or next_open or same_close" -q`

Expected: FAIL because day progression and fill pricing are not implemented.

**Step 3: Write minimal implementation**

In `backend/engine/agent/backtest.py` add:

- `async def run_backtest(...) -> dict`
- `_resolve_trading_days(...)`
- `_resolve_execution_price(...)`
- `_record_backtest_day(...)`

Implementation requirements:

- iterate trading days in ascending order
- set simulated current date before each day cycle
- create `brain_run(run_type="backtest")`
- execute `AgentBrain`
- compute fills using one of:
  - `same_close`
  - `next_open`
- write `backtest_days` rows

Do not add partial fill logic.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "trade_day or next_open or same_close" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/backtest.py tests/unit/test_agent_backtest.py
git commit -m "feat(agent): add daily backtest progression"
```

---

### Task 3: Add Failing Tests For Historical Context Freeze And Review Evolution

**Files:**
- Modify: `tests/unit/test_agent_backtest.py`
- Modify: `backend/engine/agent/backtest.py`
- Reference: `backend/engine/agent/review.py`
- Reference: `backend/engine/agent/brain.py`

**Step 1: Write the failing test**

Add tests covering:

- market data fetches never request data after `as_of_date`
- daily review runs after each backtest day
- weekly review runs on week anchor days
- memory deltas are recorded into `backtest_days`

Example skeleton:

```python
def test_backtest_freezes_market_context_at_as_of_date():
    run(engine.run_backtest(...))
    assert max(fake_data_engine.requested_end_dates) <= "2026-03-20"


def test_backtest_records_review_and_memory_deltas():
    result = run(engine.run_backtest(...))
    assert result["review_count"] >= 1
    assert result["memory_added"] >= 0
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "freeze_market_context or review_and_memory" -q`

Expected: FAIL because historical context truncation and review accounting are not implemented.

**Step 3: Write minimal implementation**

In `backend/engine/agent/backtest.py` add:

- `_with_historical_market_context(as_of_date)`
- `_collect_memory_counts(portfolio_id)`
- `_compute_memory_delta(before, after)`

Implementation requirements:

- every historical data fetch is clamped to `as_of_date`
- call `ReviewEngine.daily_review(as_of_date=trade_date)` after each day
- call `ReviewEngine.weekly_review(as_of_date=trade_date)` when the date is a weekly anchor
- write `review_created` and `memory_delta` into `backtest_days`

Keep the context adapter narrow and explicit; do not introduce a broad framework.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "freeze_market_context or review_and_memory" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/backtest.py tests/unit/test_agent_backtest.py
git commit -m "feat(agent): add historical context freeze for backtest"
```

---

### Task 4: Add Summary Read Model And Route Contract Tests

**Files:**
- Modify: `tests/unit/test_agent_backtest.py`
- Modify: `backend/engine/agent/routes.py`
- Modify: `backend/engine/agent/backtest.py`

**Step 1: Write the failing test**

Add tests covering:

- `POST /api/v1/agent/backtest/run` returns `run_id` and `status`
- `GET /api/v1/agent/backtest/run/{run_id}` returns:
  - `total_return`
  - `max_drawdown`
  - `trade_count`
  - `win_rate`
  - `review_count`
  - `memory_added`
  - `memory_updated`
  - `memory_retired`
  - `buy_and_hold_return`
- `GET /api/v1/agent/backtest/run/{run_id}/days` returns sorted day rows

Example skeleton:

```python
def test_backtest_summary_route_returns_metrics(client):
    resp = client.get(f"/api/v1/agent/backtest/run/{run_id}")
    assert resp.status_code == 200
    assert "total_return" in resp.json()
    assert "buy_and_hold_return" in resp.json()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "summary_route or days_route" -q`

Expected: FAIL because routes and summary aggregation do not exist yet.

**Step 3: Write minimal implementation**

In `backend/engine/agent/backtest.py` add:

- `async def get_run_summary(run_id: str) -> dict`
- `async def list_run_days(run_id: str) -> list[dict]`
- `_compute_max_drawdown(...)`
- `_compute_buy_and_hold_return(...)`

In `backend/engine/agent/routes.py` add:

- `POST /backtest/run`
- `GET /backtest/run/{run_id}`
- `GET /backtest/run/{run_id}/days`

Map invalid portfolio/run/date errors to proper `400` / `404`.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py -k "summary_route or days_route" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/backtest.py backend/engine/agent/routes.py tests/unit/test_agent_backtest.py
git commit -m "feat(agent): expose backtest api routes"
```

---

### Task 5: Add MCP Wrapper And Focused Verification

**Files:**
- Create: `backend/mcpserver/agent_backtest.py`
- Modify: `backend/mcpserver/server.py`
- Create: `tests/unit/mcpserver/test_agent_backtest_tools.py`
- Modify: `tests/unit/mcpserver/test_http_transport.py`

**Step 1: Write the failing test**

Add tests covering:

- `run_agent_backtest(...)` returns run status and key metrics
- `get_agent_backtest_summary(run_id)` returns compact structured JSON
- `get_agent_backtest_day(run_id, date)` returns one-day evidence
- MCP server registers all three tools

Example skeleton:

```python
@pytest.mark.asyncio
async def test_get_agent_backtest_summary_returns_structured_json(monkeypatch):
    text = await agent_backtest.get_agent_backtest_summary("run-1")
    data = json.loads(text)
    assert data["run_id"] == "run-1"
    assert "total_return" in data
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_backtest_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: FAIL because the wrapper and tool registrations do not exist yet.

**Step 3: Write minimal implementation**

In `backend/mcpserver/agent_backtest.py` add:

- `run_agent_backtest(...)`
- `get_agent_backtest_summary(run_id)`
- `get_agent_backtest_day(run_id, date)`

In `backend/mcpserver/server.py` register those tools.

Wrapper behavior:

- run tool may return operator-friendly Markdown
- summary tool should return compact JSON for agent acceptance
- day tool should return concise Markdown or JSON showing:
  - brain run id
  - trades
  - review effect
  - memory delta

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_backtest_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/mcpserver/agent_backtest.py backend/mcpserver/server.py tests/unit/mcpserver/test_agent_backtest_tools.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(mcp): expose agent backtest tools"
```

---

### Task 6: Run Focused Regression Suite And Sync Docs

**Files:**
- Review only: all touched files from Tasks 1-5

**Step 1: Run focused backtest tests**

Run: `python3 -m pytest tests/unit/test_agent_backtest.py tests/unit/mcpserver/test_agent_backtest_tools.py -q`

Expected: PASS

**Step 2: Run broader agent regression suite**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_verification.py tests/unit/test_agent_timeline_read_models.py tests/unit/test_agent_backtest.py tests/unit/mcpserver/test_agent_backtest_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-23-agent-backtest-engine-design.md docs/plans/2026-03-23-agent-backtest-engine.md backend/engine/agent/db.py backend/engine/agent/backtest.py backend/engine/agent/routes.py backend/mcpserver/agent_backtest.py backend/mcpserver/server.py tests/unit/test_agent_backtest.py tests/unit/mcpserver/test_agent_backtest_tools.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(agent): add daily backtest engine"
```
