# Agent Wake DataHunger Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Main Agent 增加最小自主观察闭环，落地 `watch_signals`、`info_digests` 和 `DataHunger`，让 brain run 在决策前先做信息消化而不是直接消费原始数据。

**Architecture:** 在现有 `backend/engine/agent` 基础上做增量扩展，不改前端。先补 DuckDB schema 和 Pydantic 模型，再实现 `DataHungerService` 的产业上下文查询、信号扫描和 digest 生成，最后把 digest 注入 `AgentBrain` 并暴露最小读写 API。

**Tech Stack:** Python 3.11, FastAPI, DuckDB, Pydantic v2, pytest, existing `IndustryEngine` / `InfoEngine` / `DataFetcher`

---

### Task 1: Add WatchSignal And Digest Schema

**Files:**
- Modify: `backend/engine/agent/db.py`
- Modify: `backend/engine/agent/models.py`
- Modify: `backend/engine/agent/service.py`
- Modify: `tests/unit/test_agent_phase1a.py`
- Create: `tests/unit/test_agent_data_hunger.py`

**Step 1: Write the failing schema tests**

Add table assertions to `tests/unit/test_agent_phase1a.py` and create a new `tests/unit/test_agent_data_hunger.py` with a minimal model import test:

```python
def test_agent_db_contains_watch_signal_and_digest_tables():
    table_names = {row["table_name"] for row in db.execute_read(...)}
    assert "watch_signals" in table_names
    assert "info_digests" in table_names


def test_brain_run_supports_digest_link_fields():
    run = BrainRun(
        ...,
        info_digest_ids=["digest-1"],
        triggered_signal_ids=["signal-1"],
    )
    assert run.info_digest_ids == ["digest-1"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_phase1a.py tests/unit/test_agent_data_hunger.py -q`

Expected: FAIL because the tables and fields do not exist yet.

**Step 3: Write minimal schema and model implementation**

In `backend/engine/agent/db.py`:

- Add `agent.watch_signals`
- Add `agent.info_digests`
- Add `brain_runs.info_digest_ids`
- Add `brain_runs.triggered_signal_ids`

Use idempotent DDL only:

```sql
ALTER TABLE agent.brain_runs ADD COLUMN IF NOT EXISTS info_digest_ids JSON;
ALTER TABLE agent.brain_runs ADD COLUMN IF NOT EXISTS triggered_signal_ids JSON;
```

In `backend/engine/agent/models.py`:

- Add `WatchSignal`
- Add `WatchSignalInput`
- Add `InfoDigest`
- Extend `BrainRun`

In `backend/engine/agent/service.py`:

- Extend `BRAIN_RUN_JSON_FIELDS` with the new JSON fields

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_phase1a.py tests/unit/test_agent_data_hunger.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/models.py backend/engine/agent/service.py tests/unit/test_agent_phase1a.py tests/unit/test_agent_data_hunger.py
git commit -m "feat(agent): add wake signal and digest schema"
```

---

### Task 2: Add WatchSignal CRUD And Minimal Routes

**Files:**
- Modify: `backend/engine/agent/service.py`
- Modify: `backend/engine/agent/routes.py`
- Modify: `backend/engine/agent/models.py`
- Modify: `tests/unit/test_agent_data_hunger.py`

**Step 1: Write the failing CRUD and route tests**

Add tests for:

- creating a watch signal
- listing watch signals by `portfolio_id`
- updating a watch signal status
- mounted routes under `/api/v1/agent/watch-signals`

```python
def test_create_and_list_watch_signals():
    created = run(svc.create_watch_signal("p1", WatchSignalInput(...)))
    rows = run(svc.list_watch_signals("p1"))
    assert rows[0]["id"] == created["id"]


def test_update_watch_signal_status():
    updated = run(svc.update_watch_signal(signal_id, {"status": "triggered"}))
    assert updated["status"] == "triggered"


def test_watch_signal_routes(client):
    resp = client.post("/api/v1/agent/watch-signals", json={...})
    assert resp.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py -q`

Expected: FAIL on missing service methods and routes.

**Step 3: Write minimal implementation**

In `backend/engine/agent/service.py` add:

- `create_watch_signal(portfolio_id, payload, source_run_id=None)`
- `list_watch_signals(portfolio_id, status=None)`
- `update_watch_signal(signal_id, updates)`

Keep the first version simple:

- `keywords` and `trigger_evidence` stored as JSON
- `updated_at` refreshed on every patch
- reject invalid statuses with `ValueError`

In `backend/engine/agent/routes.py` add:

- `POST /watch-signals`
- `GET /watch-signals`
- `PATCH /watch-signals/{signal_id}`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/service.py backend/engine/agent/routes.py backend/engine/agent/models.py tests/unit/test_agent_data_hunger.py
git commit -m "feat(agent): add watch signal CRUD routes"
```

---

### Task 3: Implement DataHungerService

**Files:**
- Create: `backend/engine/agent/data_hunger.py`
- Modify: `backend/engine/agent/service.py`
- Modify: `tests/unit/test_agent_data_hunger.py`

**Step 1: Write the failing service tests**

Add tests for:

- `query_industry_context(stock_code)` returning a normalized context object
- `execute_and_digest()` surviving partial source failures
- `scan_watch_signals()` matching keywords and returning signal hits

```python
async def test_query_industry_context_returns_normalized_payload(...):
    result = await hunger.query_industry_context("600519")
    assert result["industry"] == "饮料制造"
    assert "cycle_position" in result


async def test_execute_and_digest_marks_missing_sources(...):
    digest = await hunger.execute_and_digest("p1", "run-1", "600519", triggers=[])
    assert digest["impact_assessment"] in {"none", "noted", "minor_adjust", "reassess"}
    assert digest["missing_sources"] == ["announcements"]


async def test_scan_watch_signals_matches_keywords(...):
    hits = await hunger.scan_watch_signals("p1")
    assert hits[0]["signal_id"] == "signal-1"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py -q`

Expected: FAIL because `data_hunger.py` does not exist.

**Step 3: Write minimal implementation**

Create `backend/engine/agent/data_hunger.py` with:

```python
class DataHungerService:
    async def query_industry_context(self, stock_code: str) -> dict | None: ...
    async def scan_watch_signals(self, portfolio_id: str) -> list[dict]: ...
    async def execute_and_digest(
        self,
        portfolio_id: str,
        run_id: str,
        stock_code: str,
        triggers: list[dict] | None = None,
    ) -> dict: ...
```

Implementation rules:

- `query_industry_context()` composes `IndustryEngine.analyze()` and `get_capital_structure()`
- `scan_watch_signals()` only supports `check_engine="info"` for this batch
- `execute_and_digest()` gathers:
  - `news`
  - `announcements`
  - `industry_context`
  - `capital_structure`
  - `daily_history`
  - `technical_indicators`
- If no LLM is configured, fall back to a rule-based digest

Also add helper methods in `backend/engine/agent/service.py`:

- `create_info_digest(...)`
- `list_info_digests(portfolio_id, run_id=None, stock_code=None, limit=50)`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/data_hunger.py backend/engine/agent/service.py tests/unit/test_agent_data_hunger.py
git commit -m "feat(agent): add data hunger digest service"
```

---

### Task 4: Inject Digests Into AgentBrain

**Files:**
- Modify: `backend/engine/agent/brain.py`
- Modify: `backend/engine/agent/service.py`
- Modify: `tests/unit/test_agent_brain.py`
- Modify: `tests/unit/test_agent_data_hunger.py`

**Step 1: Write the failing brain tests**

Add tests for:

- `execute()` scanning watch signals before making decisions
- `execute()` recording `info_digest_ids`
- `execute()` recording `triggered_signal_ids`
- `_make_decisions()` consuming digest summaries instead of only raw analysis strings

```python
async def test_execute_records_digest_and_signal_links(...):
    await brain.execute("run-1")
    run_record = await svc.get_brain_run("run-1")
    assert run_record["info_digest_ids"] == ["digest-1"]
    assert run_record["triggered_signal_ids"] == ["signal-1"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_data_hunger.py -q`

Expected: FAIL because brain does not know about digests yet.

**Step 3: Write minimal implementation**

In `backend/engine/agent/brain.py`:

- instantiate `DataHungerService`
- scan watch signals near the start of `execute()`
- pass signal hits into candidate/digest flow
- for each candidate, call `execute_and_digest(...)`
- persist returned digest ids onto the run
- include digest summaries in the decision prompt:

```python
digest_desc += f"- impact: {digest['impact_assessment']}\n"
digest_desc += f"- summary: {digest['summary']}\n"
digest_desc += f"- evidence: {digest['key_evidence']}\n"
```

Do not delete the existing quant/history analysis path yet. The first version should layer digest data on top of it.

In `backend/engine/agent/service.py`:

- make sure `get_brain_run()` and `list_brain_runs()` decode the new JSON fields

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_data_hunger.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/brain.py backend/engine/agent/service.py tests/unit/test_agent_brain.py tests/unit/test_agent_data_hunger.py
git commit -m "feat(agent): inject data hunger into brain runs"
```

---

### Task 5: Expose Digest Read API And Run Regressions

**Files:**
- Modify: `backend/engine/agent/routes.py`
- Modify: `backend/engine/agent/service.py`
- Modify: `tests/unit/test_agent_data_hunger.py`

**Step 1: Write the failing route tests**

Add tests for:

- `GET /api/v1/agent/info-digests?portfolio_id=...`
- optional `run_id` filter
- JSON-safe fields in route payloads

```python
def test_get_info_digests_route(client):
    resp = client.get("/api/v1/agent/info-digests?portfolio_id=p1&run_id=run-1")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "digest-1"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py -q`

Expected: FAIL on missing route.

**Step 3: Write minimal implementation**

In `backend/engine/agent/routes.py` add:

- `GET /info-digests`

In `backend/engine/agent/service.py` keep the first read model simple:

- order by `created_at DESC`
- support `portfolio_id`, `run_id`, `stock_code`, `limit`

**Step 4: Run focused and regression tests**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/routes.py backend/engine/agent/service.py tests/unit/test_agent_data_hunger.py
git commit -m "feat(agent): expose digest read models"
```

---

### Task 6: Final Verification

**Files:**
- Verify only

**Step 1: Run the full backend verification for this batch**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py tests/unit/test_agent_read_models.py tests/unit/test_agent_review_read_models.py tests/unit/test_agent_strategy_history_read_models.py -q`

Expected: PASS

**Step 2: Inspect git status**

Run: `git status --short`

Expected: only intended tracked changes for this batch, or clean if everything was committed already.

**Step 3: Summarize integration risks**

Capture before merge:

- digest prompt may need model-based fallback tuning
- `check_engine="info"` is the only supported trigger type in this batch
- no frontend surface yet for watch signals or digests

**Step 4: Commit any final follow-up if needed**

```bash
git add <files>
git commit -m "fix(agent): finalize wake datahunger regressions"
```

Only do this if verification forced a last fix. Otherwise skip.
