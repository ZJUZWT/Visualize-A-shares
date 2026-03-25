# Agent Platform Full-Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完整补齐 Main Agent 的估值、深度分析与 `/agent` 前端交互链路，让组合台账使用真实价格口径，`full_analysis` 成为可复用的平台工具，并让分析结果可在 chat、strategy/memo context 与右侧摘要中统一呈现。

**Architecture:** 先在后端补两个共享能力层：`valuation resolver` 与 `full analysis aggregator`。随后为 Main Agent 增加 `analysis_records` 持久化与显式分析 API，再让 MCP tool 与 `/agent` 前端都接到同一份结构化结果上，避免重复实现和口径漂移。

**Tech Stack:** Python, FastAPI, asyncio, DuckDB, Pydantic, pytest, TypeScript, React, Next.js, Playwright

---

### Task 1: Add shared position valuation resolver

**Files:**
- Create: `backend/engine/agent/valuation.py`
- Modify: `backend/engine/agent/service.py`
- Create: `tests/unit/test_agent_valuation.py`

**Step 1: Write the failing test**

Add tests that prove:

- resolver prefers `realtime` or `snapshot` price over `entry_price`
- resolver falls back to recent `close_history` when snapshot is missing
- resolver falls back to `cost_fallback` when all quotes are unavailable
- returned payload always includes `latest_price`, `valuation_source`, `valuation_as_of`, `degraded`

```python
def test_resolve_position_valuation_prefers_snapshot_price():
    resolver = PositionValuationResolver(engine=FakeDataEngine(snapshot_price=112.0))
    result = run(resolver.value_position({
        "stock_code": "600519",
        "entry_price": 100.0,
        "current_qty": 100,
        "cost_basis": 10000.0,
    }))
    assert result["latest_price"] == 112.0
    assert result["market_value"] == 11200.0
    assert result["valuation_source"] == "snapshot"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_valuation.py -v`

Expected: FAIL because `PositionValuationResolver` does not exist yet.

**Step 3: Write minimal implementation**

Implement a shared resolver with a stable response shape:

```python
class PositionValuationResolver:
    async def value_position(self, position: dict) -> dict:
        return {
            "latest_price": 0.0,
            "market_value": 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "valuation_source": "cost_fallback",
            "valuation_as_of": None,
            "degraded": True,
            "fallback_reason": "no_quote",
        }
```

Resolver priority:

- realtime quote
- snapshot quote
- latest close from daily history
- cost fallback

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_valuation.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/valuation.py backend/engine/agent/service.py tests/unit/test_agent_valuation.py
git commit -m "feat(agent): add shared position valuation resolver"
```

### Task 2: Wire valuation metadata into portfolio, ledger, replay read models

**Files:**
- Modify: `backend/engine/agent/service.py`
- Modify: `tests/unit/test_agent_read_models.py`
- Modify: `tests/unit/test_agent_timeline_read_models.py`

**Step 1: Write the failing test**

Extend read-model tests so they prove:

- `get_portfolio()` total asset uses latest price instead of `entry_price * qty`
- `get_ledger_overview()` positions expose `latest_price`, `valuation_source`, `valuation_as_of`
- `asset_summary` exposes portfolio-level pricing context
- `get_replay_snapshot()` exposes `price_source` or `pricing_context` for replay account and positions

```python
assert overview["open_positions"][0]["latest_price"] == 112.0
assert overview["open_positions"][0]["valuation_source"] == "close_history"
assert overview["asset_summary"]["valuation_source"] == "close_history"
assert replay["pricing_context"]["source"] == "close_history"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_read_models.py tests/unit/test_agent_timeline_read_models.py -v`

Expected: FAIL because the read models still only expose cost-based values.

**Step 3: Write minimal implementation**

Update read models to reuse the resolver instead of recomputing with `entry_price`:

```python
position_model = _build_position_read_model(position, valuation_snapshot)

return {
    "cash_balance": cash,
    "total_asset": total_asset,
    "pricing_context": {
        "source": portfolio_source,
        "degraded": portfolio_degraded,
        "as_of": portfolio_as_of,
    },
}
```

Do not rewrite the historical ledger rebuild for timeline. Only enrich visible outputs with explicit source metadata.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_read_models.py tests/unit/test_agent_timeline_read_models.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_read_models.py tests/unit/test_agent_timeline_read_models.py
git commit -m "feat(agent): expose mark-to-market valuation across read models"
```

### Task 3: Add a shared structured full-analysis aggregator

**Files:**
- Create: `backend/engine/runtime/full_analysis.py`
- Create: `tests/unit/test_full_analysis_runtime.py`

**Step 1: Write the failing test**

Add tests that prove:

- aggregator returns stable `summary_blocks` and `sections`
- one failing section still yields a `partial` result
- section payloads carry independent `status`, `source`, and `error`

```python
def test_build_full_analysis_allows_partial_success():
    result = run(build_full_analysis(FakeDeps(news_error=RuntimeError("boom")), "600519"))
    assert result["status"] == "partial"
    assert result["sections"]["market"]["status"] == "ok"
    assert result["sections"]["info"]["status"] == "error"
    assert len(result["summary_blocks"]) >= 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_full_analysis_runtime.py -v`

Expected: FAIL because the shared aggregator does not exist.

**Step 3: Write minimal implementation**

Create a shared runtime module with a stable return contract:

```python
async def build_full_analysis(deps, code: str) -> dict:
    return {
        "stock_code": code,
        "stock_name": None,
        "status": "partial",
        "summary_blocks": [],
        "sections": {
            "market": {"status": "ok", "source": "snapshot", "payload": {}},
            "quant": {"status": "ok", "source": "quant", "payload": {}},
            "info": {"status": "error", "source": "info", "error": "boom"},
            "industry": {"status": "degraded", "source": "industry", "payload": {}},
        },
    }
```

Blocks to support:

- `market`
- `quant`
- `info`
- `industry`

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_full_analysis_runtime.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/runtime/full_analysis.py tests/unit/test_full_analysis_runtime.py
git commit -m "feat(runtime): add shared full analysis aggregator"
```

### Task 4: Persist deep-analysis results and expose explicit agent analysis APIs

**Files:**
- Modify: `backend/engine/agent/db.py`
- Modify: `backend/engine/agent/models.py`
- Create: `backend/engine/agent/analysis.py`
- Modify: `backend/engine/agent/routes.py`
- Modify: `backend/engine/agent/chat.py`
- Create: `tests/unit/test_agent_analysis.py`
- Modify: `tests/unit/test_agent_chat.py`

**Step 1: Write the failing test**

Add tests that prove:

- `POST /api/v1/agent/analysis/deep` creates a persisted analysis record
- `GET /api/v1/agent/analysis/latest` returns the newest record for the portfolio
- analysis completion can be inserted into session history as an assistant message
- chat runtime context includes the latest analysis summary in addition to current holdings

```python
def test_run_deep_analysis_persists_analysis_record(self):
    resp = self.client.post("/api/v1/agent/analysis/deep", json={
        "portfolio_id": "live",
        "stock_code": "600519",
        "trigger_source": "watchlist",
    })
    assert resp.status_code == 200
    latest = self.client.get("/api/v1/agent/analysis/latest", params={"portfolio_id": "live"})
    assert latest.json()["stock_code"] == "600519"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_analysis.py tests/unit/test_agent_chat.py -v`

Expected: FAIL because there is no analysis schema, no persistence table, and no explicit route.

**Step 3: Write minimal implementation**

Add a new persisted read model:

```python
class AgentAnalysisRecord(BaseModel):
    id: str
    portfolio_id: str
    stock_code: str
    stock_name: str | None = None
    trigger_source: str
    source_session_id: str | None = None
    source_message_id: str | None = None
    summary_blocks: list[dict]
    structured_payload: dict
    status: str
    created_at: str
    updated_at: str
```

Add explicit routes:

```python
@router.post("/analysis/deep")
async def run_deep_analysis(req: DeepAnalysisRequest): ...

@router.get("/analysis/latest")
async def get_latest_analysis(portfolio_id: str): ...
```

Inject the latest summary into `AgentChatService._build_runtime_context_message()` so future chat replies can see the newest deep-analysis result.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_analysis.py tests/unit/test_agent_chat.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/models.py backend/engine/agent/analysis.py backend/engine/agent/routes.py backend/engine/agent/chat.py tests/unit/test_agent_analysis.py tests/unit/test_agent_chat.py
git commit -m "feat(agent): persist deep analysis records and expose analysis api"
```

### Task 5: Turn `full_analysis` into a real MCP tool

**Files:**
- Modify: `backend/mcpserver/tools.py`
- Modify: `backend/mcpserver/server.py`
- Create: `tests/unit/mcpserver/test_full_analysis_tool.py`
- Modify: `tests/unit/mcpserver/test_http_transport.py`

**Step 1: Write the failing test**

Add tests that prove:

- `full_analysis(code)` is registered on the MCP server
- tool output includes `summary_blocks`, `sections`, and top-level `status`
- partial success is serialized instead of raising

```python
def test_full_analysis_tool_registered():
    module = _load_server_module()
    assert "full_analysis" in module.server._tool_manager._tools
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/mcpserver/test_full_analysis_tool.py tests/unit/mcpserver/test_http_transport.py -v`

Expected: FAIL because `full_analysis` is still only a TODO comment.

**Step 3: Write minimal implementation**

Wrap the shared runtime aggregator instead of duplicating logic:

```python
def full_analysis(da: DataAccess, code: str) -> str:
    result = _run_async(build_full_analysis(_build_mcp_analysis_deps(da), code))
    return json.dumps(result, ensure_ascii=False, indent=2)
```

Register it in `server.py` with a stable tool description.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/mcpserver/test_full_analysis_tool.py tests/unit/mcpserver/test_http_transport.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/mcpserver/tools.py backend/mcpserver/server.py tests/unit/mcpserver/test_full_analysis_tool.py tests/unit/mcpserver/test_http_transport.py
git commit -m "feat(mcp): add full_analysis tool"
```

### Task 6: Add frontend analysis/valuation view models and types

**Files:**
- Modify: `frontend/app/agent/types.ts`
- Create: `frontend/app/agent/lib/analysisViewModel.ts`
- Create: `frontend/app/agent/lib/analysisViewModel.test.ts`
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.ts`
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.test.ts`

**Step 1: Write the failing test**

Add tests that prove:

- analysis record normalization is defensive and preserves `summary_blocks`
- latest analysis summary can be derived from raw API payload
- replay / ledger normalization accepts new `valuation_source` and `latest_price` fields

```ts
test("normalizeAnalysisRecord keeps summary blocks and status", () => {
  const record = normalizeAnalysisRecord({
    stock_code: "600519",
    status: "partial",
    summary_blocks: [{ id: "market", title: "行情与估值", summary: "..." }],
  });
  assert.equal(record?.status, "partial");
  assert.equal(record?.summary_blocks.length, 1);
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit`

Expected: FAIL because the new analysis normalization helpers and fields do not exist yet.

**Step 3: Write minimal implementation**

Extend frontend types with stable shapes:

```ts
export interface AgentAnalysisSummaryBlock {
  id: string;
  title: string;
  tone: string | null;
  summary: string | null;
}

export interface AgentAnalysisRecord {
  id: string;
  stock_code: string;
  stock_name: string | null;
  status: string | null;
  summary_blocks: AgentAnalysisSummaryBlock[];
}
```

Keep normalization defensive for partial payloads and old records.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/types.ts frontend/app/agent/lib/analysisViewModel.ts frontend/app/agent/lib/analysisViewModel.test.ts frontend/app/agent/lib/rightRailTimelineViewModel.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts
git commit -m "feat(agent-ui): add analysis and valuation view models"
```

### Task 7: Add explicit deep-analysis UX to `/agent`

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/components/AgentChatPanel.tsx`
- Modify: `frontend/app/agent/components/AgentChatMessage.tsx`
- Create: `frontend/app/agent/components/AgentAnalysisCard.tsx`
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Modify: `frontend/tests/smoke/support/smokeHarness.ts`
- Modify: `frontend/tests/smoke/routes.spec.ts`

**Step 1: Write the failing test**

Add tests or smoke assertions that prove:

- watchlist item exposes a `深度分析` action
- triggering it renders an analysis card in the chat stream
- latest analysis summary appears in the right-side workspace
- ledger cards show valuation source instead of a generic unavailable message

```ts
await page.goto("/agent");
await page.getByRole("button", { name: "深度分析 600519" }).click();
await page.getByText("行情与估值").waitFor();
await page.getByText("source: snapshot").waitFor();
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:smoke`

Expected: FAIL because the explicit analysis action and card rendering do not exist yet.

**Step 3: Write minimal implementation**

Wire a dedicated analysis flow in the page:

```ts
async function handleRunDeepAnalysis(input: {
  stock_code: string;
  stock_name?: string | null;
  trigger_source: "watchlist" | "position" | "manual";
}) {
  // call /api/v1/agent/analysis/deep
  // stream status
  // append assistant analysis card entry
  // refresh latest analysis + session messages
}
```

UI changes:

- add `深度分析` buttons to watchlist/position entry points
- render `AgentAnalysisCard` when a chat entry carries analysis payload
- surface latest analysis summary in the right rail or ledger area
- replace generic unavailable text with exact source/degraded wording where data now exists

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit && npm run test:smoke`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/app/agent/components/AgentChatPanel.tsx frontend/app/agent/components/AgentChatMessage.tsx frontend/app/agent/components/AgentAnalysisCard.tsx frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/tests/smoke/support/smokeHarness.ts frontend/tests/smoke/routes.spec.ts
git commit -m "feat(agent-ui): add explicit deep analysis workflow"
```

### Task 8: Final verification and doc alignment

**Files:**
- Modify: `docs/plans/2026-03-24-agent-platform-full-stack-design.md`
- Modify: `docs/plans/2026-03-24-agent-platform-full-stack.md`

**Step 1: Run backend verification**

Run: `pytest tests/unit/test_agent_valuation.py tests/unit/test_agent_read_models.py tests/unit/test_agent_timeline_read_models.py tests/unit/test_full_analysis_runtime.py tests/unit/test_agent_analysis.py tests/unit/test_agent_chat.py tests/unit/mcpserver/test_full_analysis_tool.py tests/unit/mcpserver/test_http_transport.py -v`

Expected: PASS

**Step 2: Run frontend verification**

Run: `cd frontend && npm run test:unit && npm run build`

Expected: PASS

**Step 3: Run smoke verification**

Run: `cd frontend && npm run test:smoke`

Expected: PASS

**Step 4: Sanity-check Python syntax**

Run: `python3 -m py_compile backend/engine/agent/valuation.py backend/engine/agent/analysis.py backend/engine/runtime/full_analysis.py backend/engine/agent/service.py backend/engine/agent/routes.py backend/engine/agent/chat.py backend/mcpserver/tools.py backend/mcpserver/server.py`

Expected: PASS

**Step 5: Update docs if implementation diverged**

Only update the design/plan docs if any concrete file path, field name, or route differs from the actual implementation. Do not leave stale names in the saved docs.

**Step 6: Commit**

```bash
git add docs/plans/2026-03-24-agent-platform-full-stack-design.md docs/plans/2026-03-24-agent-platform-full-stack.md backend/engine/agent/valuation.py backend/engine/agent/analysis.py backend/engine/runtime/full_analysis.py backend/engine/agent/service.py backend/engine/agent/routes.py backend/engine/agent/chat.py backend/engine/agent/db.py backend/engine/agent/models.py backend/mcpserver/tools.py backend/mcpserver/server.py tests/unit/test_agent_valuation.py tests/unit/test_agent_read_models.py tests/unit/test_agent_timeline_read_models.py tests/unit/test_full_analysis_runtime.py tests/unit/test_agent_analysis.py tests/unit/test_agent_chat.py tests/unit/mcpserver/test_full_analysis_tool.py tests/unit/mcpserver/test_http_transport.py frontend/app/agent/types.ts frontend/app/agent/lib/analysisViewModel.ts frontend/app/agent/lib/analysisViewModel.test.ts frontend/app/agent/lib/rightRailTimelineViewModel.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts frontend/app/agent/page.tsx frontend/app/agent/components/AgentChatPanel.tsx frontend/app/agent/components/AgentChatMessage.tsx frontend/app/agent/components/AgentAnalysisCard.tsx frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/tests/smoke/support/smokeHarness.ts frontend/tests/smoke/routes.spec.ts
git commit -m "feat(agent): complete valuation and deep analysis platform module"
```
