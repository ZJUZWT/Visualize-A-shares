# Agent Pet Console Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 `/agent` 页面升级成 Main Agent 的宠物化主控台，提供 `宠物 / 训练 / 模拟盘 / 回测` 四个主页签，并让前台能直接触发训练 suite。

**Architecture:** 保持现有 `/agent` 页面的大部分数据获取逻辑，新增一个顶层壳层和少量前端 view-model，把聊天、策略脑、账本、回放重新编排为四个主页签。后端补一条极薄的 `verification-suite` HTTP route，复用现有 suite wrapper，不新增业务逻辑。

**Tech Stack:** Next.js 15, React 19, TypeScript, Node `node:test`, FastAPI, pytest

---

### Task 1: Add Failing Tests For Frontend Pet Console View-Model

**Files:**
- Create: `frontend/app/agent/lib/petConsoleViewModel.ts`
- Create: `frontend/app/agent/lib/petConsoleViewModel.test.ts`
- Modify: `frontend/app/agent/types.ts`

**Step 1: Write the failing test**

Add tests covering:

- active run `running` maps pet mood to `thinking`
- training suite `running` / `warn` / `pass` maps to pet mood and summary badge
- open positions / pending plans maps battle readiness
- negative total pnl maps to `drawdown`

**Step 2: Run test to verify it fails**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: FAIL because the module does not exist yet.

**Step 3: Write minimal implementation**

Create `petConsoleViewModel.ts` with pure helpers:

- `buildPetConsoleViewModel(...)`
- `resolvePetMood(...)`
- `summarizeTrainingSuite(...)`

Only pure mapping logic, no fetch.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/lib/petConsoleViewModel.ts frontend/app/agent/lib/petConsoleViewModel.test.ts frontend/app/agent/types.ts
git commit -m "feat(agent): add pet console view model"
```

---

### Task 2: Add Failing Tests For Verification Suite HTTP Route

**Files:**
- Modify: `backend/engine/agent/routes.py`
- Create: `tests/unit/test_agent_verification_suite_routes.py`

**Step 1: Write the failing test**

Add tests covering:

- `POST /api/v1/agent/verification-suite/run` returns suite JSON
- `smoke_mode=true` is forwarded
- route surfaces `ValueError` as HTTP error consistently

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_verification_suite_routes.py -q`

Expected: FAIL because the route does not exist yet.

**Step 3: Write minimal implementation**

In `routes.py`:

- add request model for suite run
- add route that calls `mcpserver.agent_verification_suite.run_demo_agent_verification_suite(...)`
- parse returned JSON string before responding

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_verification_suite_routes.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/routes.py tests/unit/test_agent_verification_suite_routes.py
git commit -m "feat(agent): expose verification suite route"
```

---

### Task 3: Build Pet Page Shell And Main Tabs

**Files:**
- Create: `frontend/app/agent/components/AgentPetStage.tsx`
- Create: `frontend/app/agent/components/AgentTrainingPanel.tsx`
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/types.ts`

**Step 1: Write the failing test**

Expand `petConsoleViewModel.test.ts` with expectations for:

- `pet` tab strategy summary text
- training status card text
- battle status label

**Step 2: Run test to verify it fails**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: FAIL because the view-model contract is not rich enough yet.

**Step 3: Write minimal implementation**

In `page.tsx`:

- add top-level page tab state
- render four page tabs
- `pet` tab uses:
  - `AgentPetStage`
  - existing `AgentChatPanel`
  - existing `StrategyBrainPanel`
- preserve current chat and strategy functionality

`AgentPetStage.tsx`:

- pixel-style pet card
- mood badge
- last action
- readiness / training status chips

`AgentTrainingPanel.tsx`:

- buttons for `Run Training Suite` and `Run Smoke`
- result summary card

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/components/AgentPetStage.tsx frontend/app/agent/components/AgentTrainingPanel.tsx frontend/app/agent/page.tsx frontend/app/agent/types.ts frontend/app/agent/lib/petConsoleViewModel.ts frontend/app/agent/lib/petConsoleViewModel.test.ts
git commit -m "feat(agent): add pet console shell"
```

---

### Task 4: Wire Training, Battle, And Backtest Tabs

**Files:**
- Modify: `frontend/app/agent/page.tsx`
- Modify: `frontend/app/agent/components/ExecutionLedgerPanel.tsx` (only if needed)

**Step 1: Write the failing test**

Add a small failing case to `petConsoleViewModel.test.ts` for training tab summary and battle status.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: FAIL because tab-specific summaries are not complete yet.

**Step 3: Write minimal implementation**

In `page.tsx`:

- `training` tab renders suite controls + review/memory/reflection panels
- `battle` tab renders execution ledger + quick status summary
- `backtest` tab renders backtest controls + summary + replay area

Reuse existing components before creating anything new.

**Step 4: Run test to verify it passes**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/app/agent/components/ExecutionLedgerPanel.tsx frontend/app/agent/lib/petConsoleViewModel.ts frontend/app/agent/lib/petConsoleViewModel.test.ts
git commit -m "feat(agent): wire pet console tabs"
```

---

### Task 5: Run Full Verification

**Files:**
- Review only: touched files from previous tasks

**Step 1: Run frontend node tests**

Run: `node --test frontend/app/agent/lib/petConsoleViewModel.test.ts frontend/app/agent/lib/wakeViewModel.test.ts frontend/app/agent/lib/strategyActionViewModel.test.ts frontend/app/agent/lib/strategyBrainViewModel.test.ts frontend/app/agent/lib/rightRailTimelineViewModel.test.ts frontend/app/agent/lib/rightRailPositionViewModel.test.ts frontend/app/agent/reflectionFeed.test.ts`

Expected: PASS

**Step 2: Run backend route tests**

Run: `python3 -m pytest tests/unit/test_agent_verification_suite_routes.py tests/unit/test_agent_verification.py tests/unit/test_agent_backtest.py tests/unit/mcpserver/test_agent_verification_suite_tools.py tests/unit/mcpserver/test_http_transport.py -q`

Expected: PASS

**Step 3: Run frontend build**

Run: `npm run build`

Expected: PASS

**Step 4: Commit**

```bash
git add docs/plans/2026-03-23-agent-pet-console-design.md docs/plans/2026-03-23-agent-pet-console.md backend/engine/agent/routes.py tests/unit/test_agent_verification_suite_routes.py frontend/app/agent/page.tsx frontend/app/agent/types.ts frontend/app/agent/components/AgentPetStage.tsx frontend/app/agent/components/AgentTrainingPanel.tsx frontend/app/agent/lib/petConsoleViewModel.ts frontend/app/agent/lib/petConsoleViewModel.test.ts
git commit -m "feat(agent): add pet console frontstage"
```
