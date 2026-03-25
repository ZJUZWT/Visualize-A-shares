# Main Agent Core Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 一次性收敛 `Main Agent Core`，补齐信息免疫语义、decision trace 审计和 replay learning，使 `/agent` 与 backend/MCP contract 形成完整闭环。

**Architecture:** 在现有 `backend/engine/agent` 和 `frontend/app/agent` 能力上做收尾式增强，不新建 `decision_logs` 表，而是扩展 `brain_runs.thinking_process`；不重写 replay/backtest，而是在现有 replay read model 之上新增 replay learning。所有新增能力优先复用现有 `DataHungerService`、`AgentBrain`、`AgentService`、`/agent` 页面。

**Tech Stack:** Python 3.11, pytest, FastAPI, FastMCP, Next.js 15, React 19, TypeScript, node:test, DuckDB

---

### Task 1: Add failing tests for DataHunger information-immunity contract

**Files:**
- Modify: `tests/unit/test_agent_data_hunger.py`
- Modify: `backend/engine/agent/data_hunger.py`

**Step 1: Write the failing test**

Add tests covering:

- `execute_and_digest()` returns structured immunity fields:
  - `evidence_tier`
  - `suggested_action`
  - `missing_tier1_evidence`
  - `immunity_checks`
- trigger-only evidence does not automatically mean strategy change
- missing Tier 1 sources downgrades digest confidence/action

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py -k "immunity or digest" -q`

Expected: FAIL because the digest contract does not expose these fields yet.

**Step 3: Write minimal implementation**

In `backend/engine/agent/data_hunger.py`:

- extend `structured_summary`
- add deterministic immunity evaluation helpers
- persist the extra fields through `create_info_digest()`
- keep current write path and table shape

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py -k "immunity or digest" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_agent_data_hunger.py backend/engine/agent/data_hunger.py
git commit -m "feat(agent): add information immunity digest contract"
```

### Task 2: Add failing tests for AgentBrain decision trace and strengthened system prompt

**Files:**
- Modify: `tests/unit/test_agent_brain.py`
- Modify: `tests/unit/test_agent_decision_quality.py`
- Modify: `backend/engine/agent/brain.py`
- Modify: `backend/engine/agent/decision_quality.py`

**Step 1: Write the failing test**

Add tests covering:

- `build_system_prompt()` includes the core creed from root TODO
- `thinking_process` persists stable `decision_trace`
- `decision_trace.info_digests` maps consumed digest ids and decision roles
- gate summary remains visible in `thinking_process`

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_decision_quality.py tests/unit/test_agent_brain.py -k "decision_trace or system_prompt" -q`

Expected: FAIL because the stronger prompt text and `decision_trace` structure do not exist yet.

**Step 3: Write minimal implementation**

In `backend/engine/agent/decision_quality.py`:

- strengthen `build_system_prompt()` with the core anti-noise / Tier 1 creed

In `backend/engine/agent/brain.py`:

- derive a stable `decision_trace` from current digests and triggered signals
- persist it under `thinking_process`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_decision_quality.py tests/unit/test_agent_brain.py -k "decision_trace or system_prompt" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_agent_decision_quality.py tests/unit/test_agent_brain.py backend/engine/agent/brain.py backend/engine/agent/decision_quality.py
git commit -m "feat(agent): persist decision trace with digest evidence"
```

### Task 3: Add failing tests for replay learning backend read model and route

**Files:**
- Modify: `tests/unit/test_agent_timeline_read_models.py`
- Modify: `backend/engine/agent/service.py`
- Modify: `backend/engine/agent/routes.py`

**Step 1: Write the failing test**

Add tests covering:

- `AgentService.get_replay_learning(portfolio_id, date)` returns:
  - `what_ai_knew`
  - `what_happened`
  - `counterfactual`
  - `lesson_summary`
- route `GET /api/v1/agent/timeline/replay-learning` returns structured JSON
- invalid portfolio/date map to existing HTTP semantics

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "replay_learning" -q`

Expected: FAIL because replay learning does not exist yet.

**Step 3: Write minimal implementation**

In `backend/engine/agent/service.py`:

- add `get_replay_learning()` on top of `get_replay_snapshot()`
- build deterministic counterfactual guidance from replay, reviews, next-day move, and decision trace

In `backend/engine/agent/routes.py`:

- add `GET /timeline/replay-learning`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_timeline_read_models.py -k "replay_learning" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_agent_timeline_read_models.py backend/engine/agent/service.py backend/engine/agent/routes.py
git commit -m "feat(agent): add replay learning read model"
```

### Task 4: Add failing frontend tests for replay learning and decision trace consumption

**Files:**
- Modify: `frontend/app/agent/lib/rightRailTimelineViewModel.ts`
- Create: `frontend/app/agent/lib/replayLearningViewModel.ts`
- Create: `frontend/app/agent/lib/replayLearningViewModel.test.ts`
- Modify: `frontend/app/agent/types.ts`
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
- Modify: `frontend/app/agent/page.tsx`

**Step 1: Write the failing test**

Add tests covering:

- replay learning payload normalization
- counterfactual recommendation text / tone mapping
- `ExecutionLedgerPanel` can render replay learning summary alongside replay

**Step 2: Run test to verify it fails**

Run: `node --test frontend/app/agent/lib/rightRailTimelineViewModel.test.ts frontend/app/agent/lib/replayLearningViewModel.test.ts`

Expected: FAIL because replay learning types and view-model do not exist yet.

**Step 3: Write minimal implementation**

In frontend:

- add replay learning types and normalize helpers
- fetch replay learning with existing replay date flow
- render a compact replay learning card in the right rail / battle-backtest surfaces

Do not redesign the entire page layout.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/rightRailTimelineViewModel.test.ts frontend/app/agent/lib/replayLearningViewModel.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/lib/rightRailTimelineViewModel.ts frontend/app/agent/lib/replayLearningViewModel.ts frontend/app/agent/lib/replayLearningViewModel.test.ts frontend/app/agent/types.ts frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/page.tsx
git commit -m "feat(agent): surface replay learning on agent console"
```

### Task 5: Run focused Main Agent Core verification

**Files:**
- Review only: files touched in Tasks 1-4

**Step 1: Run backend regressions**

Run: `python3 -m pytest tests/unit/test_agent_data_hunger.py tests/unit/test_agent_decision_quality.py tests/unit/test_agent_brain.py tests/unit/test_agent_timeline_read_models.py tests/unit/test_agent_backtest.py tests/unit/test_agent_verification.py tests/unit/test_agent_verification_suite_routes.py tests/unit/mcpserver/test_agent_backtest_tools.py tests/unit/mcpserver/test_agent_verification_suite_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 2: Run frontend agent tests**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts frontend/app/agent/lib/backtestArtifacts.test.ts frontend/app/agent/lib/petWorkspaceLayout.test.ts frontend/app/agent/lib/wakeViewModel.test.ts frontend/app/agent/lib/strategyActionViewModel.test.ts frontend/app/agent/lib/strategyBrainViewModel.test.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts frontend/app/agent/lib/rightRailPositionViewModel.test.ts frontend/app/agent/lib/replayLearningViewModel.test.ts frontend/app/agent/reflectionFeed.test.ts`

Expected: PASS

**Step 3: Run frontend build**

Run: `npm run build`

Expected: PASS

**Step 4: Commit**

```bash
git add docs/plans/2026-03-23-main-agent-core-closure-design.md docs/plans/2026-03-23-main-agent-core-closure.md
git commit -m "docs(agent): add main agent core closure plan"
```
