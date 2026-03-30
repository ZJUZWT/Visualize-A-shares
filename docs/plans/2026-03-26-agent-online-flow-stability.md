# Agent Online Flow Stability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不做大改的前提下，让 Main Agent 的前端链路和 MCP 在线链路都能稳定跑通，并在服务不可用时明确失败。

**Architecture:** 保持现有 `/agent` 页面和 agent 业务逻辑不变，只把 agent MCP 收敛到 HTTP 在线入口，并修正前端训练相关状态污染。后端如需补能力，只增加极薄 route 转发现有逻辑。

**Tech Stack:** Next.js 15, React 19, TypeScript, Node `node:test`, FastAPI, pytest

---

### Task 1: Add failing tests for pet training state separation

**Files:**
- Modify: `frontend/app/agent/lib/petConsoleViewModel.test.ts`
- Modify: `frontend/app/agent/lib/petConsoleViewModel.ts`

**Step 1: Write the failing test**

Add tests covering:

- existing `suiteResult` must not force pet mood to `training` when a brain run is currently `running`
- training summary can still show latest suite result while pet mood follows current run state

**Step 2: Run test to verify it fails**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: FAIL because current implementation prioritizes `suiteResult`

**Step 3: Write minimal implementation**

Update `resolvePetMood(...)` so current run state takes priority over historical suite result.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: PASS

### Task 2: Add failing tests for HTTP-backed agent MCP wrappers

**Files:**
- Create: `tests/unit/mcpserver/test_agent_http_bridge.py`
- Modify: `backend/mcpserver/agent_verification.py`
- Modify: `backend/mcpserver/agent_verification_suite.py`

**Step 1: Write the failing test**

Add tests covering:

- `inspect_agent_snapshot` uses HTTP when service is online
- `prepare_demo_agent_portfolio` uses HTTP when service is online
- `verify_demo_agent_cycle` uses HTTP when service is online
- `run_demo_agent_verification_suite` uses HTTP when service is online
- service offline returns explicit unavailable error instead of touching `AgentDB`

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_http_bridge.py -q`

Expected: FAIL because wrappers currently call local DB/harness directly

**Step 3: Write minimal implementation**

Introduce a small HTTP helper for agent MCP wrappers and route calls through `http://localhost:8000`.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/mcpserver/test_agent_http_bridge.py -q`

Expected: PASS

### Task 3: Add thin backend routes for snapshot and demo verification if missing

**Files:**
- Modify: `backend/engine/agent/routes.py`
- Create or Modify: `tests/unit/test_agent_online_routes.py`

**Step 1: Write the failing test**

Add tests covering:

- snapshot route returns structured data
- demo verification route returns structured data
- route maps `ValueError` consistently

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_online_routes.py -q`

Expected: FAIL if route does not yet exist

**Step 3: Write minimal implementation**

Add thin HTTP routes that call existing verification harness/module without adding new business logic.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_online_routes.py -q`

Expected: PASS

### Task 4: Prevent stale training state from leaking across portfolio changes

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/lib/petConsoleViewModel.test.ts`

**Step 1: Write the failing test**

Add a test or narrow reproduction covering:

- switching portfolio clears stale suite result driven training display

**Step 2: Run test to verify it fails**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: FAIL or missing coverage

**Step 3: Write minimal implementation**

Reset `suiteResult` and `suiteError` when `portfolioId` changes, while preserving current runtime fetch behavior.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: PASS

### Task 5: Verify online flow stability

**Files:**
- Review only: touched files from previous tasks

**Step 1: Run frontend tests**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: PASS

**Step 2: Run backend and MCP tests**

Run: `python3 -m pytest tests/unit/test_agent_verification_suite_routes.py tests/unit/mcpserver/test_agent_verification_suite_tools.py tests/unit/mcpserver/test_agent_http_bridge.py tests/unit/test_agent_online_routes.py -q`

Expected: PASS

**Step 3: Run live online checks**

Run:

```bash
curl -sS http://localhost:8000/api/v1/health
```

Then verify through MCP:

- `inspect_agent_snapshot`
- `prepare_demo_agent_portfolio`
- `verify_demo_agent_cycle`
- `run_demo_agent_verification_suite`

Expected: online path returns structured result; service offline fails explicitly
