# Agent History Replay And Equity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build backend-only daily equity timeline and historical replay APIs for Main Agent, with both `mark_to_market` and `realized_only` curves.

**Architecture:** Extend `AgentService` with a read-only timeline reconstruction layer that rebuilds daily cash, positions, and realized PnL from `agent.trades`, then joins historical close prices from `DataEngine`. Expose the read models through two new FastAPI routes and verify the contract entirely with isolated unit tests using stubbed price history.

**Tech Stack:** FastAPI, Pydantic, DuckDB, pytest, existing `AgentService` / `AgentDB`, `engine.data.get_data_engine`

---

### Task 1: Add failing service tests for equity timeline

**Files:**
- Create: `tests/unit/test_agent_timeline_read_models.py`
- Reference: `backend/engine/agent/service.py`

**Step 1: Write the failing test**

```python
def test_get_equity_timeline_returns_mark_to_market_and_realized_only():
    timeline = run(svc.get_equity_timeline("live"))
    assert set(timeline.keys()) == {
        "portfolio_id", "start_date", "end_date",
        "mark_to_market", "realized_only",
    }
    assert timeline["mark_to_market"][-1]["equity"] > timeline["realized_only"][-1]["equity"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py::TestAgentTimelineService::test_get_equity_timeline_returns_mark_to_market_and_realized_only -v`
Expected: FAIL with `AttributeError` or missing route/service method

**Step 3: Write minimal implementation**

```python
async def get_equity_timeline(self, portfolio_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
    return {
        "portfolio_id": portfolio_id,
        "start_date": start_date,
        "end_date": end_date,
        "mark_to_market": [],
        "realized_only": [],
    }
```

**Step 4: Run test to verify it still fails for behavior**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py::TestAgentTimelineService::test_get_equity_timeline_returns_mark_to_market_and_realized_only -v`
Expected: FAIL on shape/value assertions, proving the test is exercising real behavior

**Step 5: Commit**

```bash
git add tests/unit/test_agent_timeline_read_models.py backend/engine/agent/service.py
git commit -m "test(agent): add equity timeline read model coverage"
```

### Task 2: Implement daily state reconstruction and price-backed equity curves

**Files:**
- Modify: `backend/engine/agent/service.py`
- Reference: `backend/engine/agent/models.py`
- Test: `tests/unit/test_agent_timeline_read_models.py`

**Step 1: Write the failing tests for reconstruction edge cases**

```python
def test_get_equity_timeline_falls_back_to_previous_close_when_day_missing():
    timeline = run(svc.get_equity_timeline("live"))
    assert timeline["mark_to_market"][1]["position_value"] == 10200.0

def test_get_equity_timeline_returns_flat_curve_for_portfolio_without_trades():
    timeline = run(empty_svc.get_equity_timeline("training"))
    assert timeline["mark_to_market"] == timeline["realized_only"]
```

**Step 2: Run targeted tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "equity_timeline" -v`
Expected: FAIL on incorrect calculations and missing fallback logic

**Step 3: Write minimal implementation**

```python
def _parse_iso_date(value: str | None) -> date | None: ...
async def _load_price_history(...): ...
def _lookup_close_on_or_before(...): ...
def _rebuild_daily_ledger(...): ...
async def get_equity_timeline(...): ...
```

Implementation requirements:

- sort trades by `created_at ASC`
- rebuild `cash_balance`, open qty, cost basis, realized pnl day by day
- build a daily date range from portfolio start to range end
- compute `mark_to_market` using close price fallback
- compute `realized_only` using realized pnl only
- keep returned floats rounded consistently

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "equity_timeline" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_timeline_read_models.py
git commit -m "feat(agent): add equity timeline read model"
```

### Task 3: Add failing service tests for historical replay snapshot

**Files:**
- Modify: `tests/unit/test_agent_timeline_read_models.py`
- Modify: `backend/engine/agent/service.py`

**Step 1: Write the failing test**

```python
def test_get_replay_snapshot_aggregates_account_positions_and_ai_context():
    replay = run(svc.get_replay_snapshot("live", "2026-03-20"))
    assert replay["date"] == "2026-03-20"
    assert replay["account"]["total_asset_mark_to_market"] > 0
    assert replay["trades"][0]["stock_code"] == "600519"
    assert "brain_runs" in replay
    assert "what_ai_knew" in replay
    assert "what_happened" in replay
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py::TestAgentTimelineService::test_get_replay_snapshot_aggregates_account_positions_and_ai_context -v`
Expected: FAIL with missing method or incomplete payload

**Step 3: Write minimal implementation**

```python
async def get_replay_snapshot(self, portfolio_id: str, replay_date: str) -> dict:
    return {
        "portfolio_id": portfolio_id,
        "date": replay_date,
        "account": {},
        "positions": [],
        "brain_runs": [],
        "plans": [],
        "trades": [],
        "reviews": [],
        "reflections": [],
        "what_ai_knew": {},
        "what_happened": {},
    }
```

**Step 4: Run test to verify it still fails on data assertions**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py::TestAgentTimelineService::test_get_replay_snapshot_aggregates_account_positions_and_ai_context -v`
Expected: FAIL on missing aggregated content

**Step 5: Commit**

```bash
git add tests/unit/test_agent_timeline_read_models.py backend/engine/agent/service.py
git commit -m "test(agent): add replay snapshot coverage"
```

### Task 4: Implement replay aggregation and next-day outcome summary

**Files:**
- Modify: `backend/engine/agent/service.py`
- Test: `tests/unit/test_agent_timeline_read_models.py`

**Step 1: Write the failing edge-case tests**

```python
def test_get_replay_snapshot_includes_next_day_move_pct_when_price_exists():
    replay = run(svc.get_replay_snapshot("live", "2026-03-20"))
    assert replay["what_happened"]["next_day_move_pct"] == pytest.approx(0.03)

def test_get_replay_snapshot_rejects_date_before_portfolio_start():
    with pytest.raises(ValueError, match="早于组合起始"):
        run(svc.get_replay_snapshot("live", "2026-03-01"))
```

**Step 2: Run replay tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "replay_snapshot" -v`
Expected: FAIL on missing next-day summary and range validation

**Step 3: Write minimal implementation**

```python
async def _list_replay_runs(...): ...
async def _list_replay_plans(...): ...
async def _list_replay_reviews(...): ...
async def _list_replay_reflections(...): ...
def _build_what_ai_knew(...): ...
def _build_what_happened(...): ...
async def get_replay_snapshot(...): ...
```

Implementation requirements:

- reuse the daily ledger reconstruction from Task 2
- filter rows by replay day boundaries
- include normalized brain runs and trade/plan read models
- compute unrealized/realized pnl in `account`
- include `next_day_move_pct` from the next available close after replay date

**Step 4: Run replay tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "replay_snapshot" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_timeline_read_models.py
git commit -m "feat(agent): add historical replay read model"
```

### Task 5: Add API routes and route contract tests

**Files:**
- Modify: `backend/engine/agent/routes.py`
- Modify: `tests/unit/test_agent_timeline_read_models.py`
- Optional: `backend/engine/agent/models.py`

**Step 1: Write the failing route tests**

```python
def test_get_equity_timeline_route():
    resp = client.get("/api/v1/agent/timeline/equity?portfolio_id=live")
    assert resp.status_code == 200
    assert "mark_to_market" in resp.json()

def test_get_replay_snapshot_route_404_for_missing_portfolio():
    resp = client.get("/api/v1/agent/timeline/replay?portfolio_id=missing&date=2026-03-20")
    assert resp.status_code == 404
```

**Step 2: Run route tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "route" -v`
Expected: FAIL with 404 route-not-found or wrong status mapping

**Step 3: Write minimal implementation**

```python
@router.get("/timeline/equity")
async def get_equity_timeline(...): ...

@router.get("/timeline/replay")
async def get_replay_snapshot(...): ...
```

Implementation requirements:

- map invalid dates to `400`
- map missing portfolio to `404`
- preserve existing router style

**Step 4: Run route tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "route" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/routes.py tests/unit/test_agent_timeline_read_models.py backend/engine/agent/models.py
git commit -m "feat(agent): add timeline and replay api routes"
```

### Task 6: Run regression verification and integrate docs

**Files:**
- Modify: `docs/plans/2026-03-23-agent-history-replay-equity-design.md`
- Modify: `docs/plans/2026-03-23-agent-history-replay-equity.md`
- Test: `tests/unit/test_agent_read_models.py`
- Test: `tests/unit/test_agent_strategy_history_read_models.py`
- Test: `tests/unit/test_agent_review_read_models.py`
- Test: `tests/unit/test_agent_timeline_read_models.py`

**Step 1: Run the focused regression suite**

Run: `python3 -m pytest tests/unit/test_agent_read_models.py tests/unit/test_agent_strategy_history_read_models.py tests/unit/test_agent_review_read_models.py tests/unit/test_agent_timeline_read_models.py -q`
Expected: PASS

**Step 2: Review for overreach**

Check:

- no write-path behavior changed
- no new tables added
- no network dependency in tests

**Step 3: Update docs only if implementation diverged**

```markdown
- adjust route response examples
- document any fallback rule change
```

**Step 4: Run full targeted verification again**

Run: `python3 -m pytest tests/unit/test_agent_read_models.py tests/unit/test_agent_strategy_history_read_models.py tests/unit/test_agent_review_read_models.py tests/unit/test_agent_timeline_read_models.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-03-23-agent-history-replay-equity-design.md docs/plans/2026-03-23-agent-history-replay-equity.md backend/engine/agent/routes.py backend/engine/agent/service.py tests/unit/test_agent_timeline_read_models.py
git commit -m "feat(agent): add replay and equity backend read models"
```
