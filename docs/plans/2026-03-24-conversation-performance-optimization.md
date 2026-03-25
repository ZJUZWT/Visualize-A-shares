# Conversation Performance Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `expert`、`arena`、`main agent` 抽取共享对话执行运行时，统一模型分层、输入预取、依赖感知并行和渐进式 SSE，加速整体交互且不降低最终回答质量。

**Architecture:** 在后端新增共享 runtime 能力层，包含 `ModelRouter`、`ExecutionContext`、`QueryPrefetcher`、`ToolExecutionPlanner` 和 `ProgressiveEmitter`。`ExpertAgent` 作为首个完整接入者，`JudgeRAG` 和 `AgentBrain` 复用其中的低风险能力，保持既有业务编排与外部接口兼容。

**Tech Stack:** Python, FastAPI, asyncio, Pydantic, SSE, pytest

---

### Task 1: Add shared LLM tier routing

**Files:**
- Modify: `backend/llm/config.py`
- Modify: `backend/llm/providers.py`
- Create: `tests/unit/llm/test_model_router.py`

**Step 1: Write the failing test**

Add tests that prove:

- `fast` config can override model/provider/base_url independently
- missing `fast` config falls back to `quality`
- existing `LLMProviderFactory.create()` behavior remains unchanged

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/llm/test_model_router.py -v`

Expected: FAIL because no shared tier router exists yet.

**Step 3: Write minimal implementation**

- extend `LLMConfig` with optional `fast_*` env-backed fields
- add `ModelRouter` helper around `LLMProviderFactory`
- keep default config backward compatible

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/llm/test_model_router.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/llm/config.py backend/llm/providers.py tests/unit/llm/test_model_router.py
git commit -m "feat(llm): add fast and quality model routing"
```

### Task 2: Add shared execution context and query prefetcher

**Files:**
- Create: `backend/engine/runtime/context.py`
- Create: `backend/engine/runtime/prefetch.py`
- Modify: `backend/engine/expert/agent.py`
- Create: `tests/unit/expert/test_runtime_prefetch.py`

**Step 1: Write the failing test**

Add tests that prove:

- messages containing a stock code trigger prefetch
- messages containing a known stock name trigger prefetch
- prefetch failure does not break `ExpertAgent.chat()`

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/expert/test_runtime_prefetch.py -v`

Expected: FAIL because runtime context and prefetch hooks do not exist.

**Step 3: Write minimal implementation**

- add `ExecutionContext`
- add `QueryPrefetcher`
- kick off prefetch early in `ExpertAgent.chat()`
- emit optional `prefetch_ready` event when prefetch returns usable data

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/expert/test_runtime_prefetch.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/runtime/context.py backend/engine/runtime/prefetch.py backend/engine/expert/agent.py tests/unit/expert/test_runtime_prefetch.py
git commit -m "feat(runtime): add execution context and query prefetcher"
```

### Task 3: Add dependency-aware tool planner and progressive expert SSE

**Files:**
- Create: `backend/engine/runtime/planner.py`
- Create: `backend/engine/runtime/emitter.py`
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/expert/tools.py`
- Modify: `tests/unit/expert/test_agent.py`
- Create: `tests/unit/expert/test_runtime_planner.py`

**Step 1: Write the failing test**

Add tests that prove:

- `quant` can run in parallel when no `data` dependency is present
- planner falls back to conservative order when dependency is unknown
- `early_insight` is emitted before `reply_complete`
- existing `tool_result` and `reply_complete` events still exist

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/expert/test_agent.py tests/unit/expert/test_runtime_planner.py -v`

Expected: FAIL because execution planning and early insight events are not implemented.

**Step 3: Write minimal implementation**

- add dependency classification and execution planning
- allow prefetched history/profile to satisfy some quant prerequisites
- add progressive emitter helpers
- emit `tool_partial` / `early_insight` before final reply when meaningful

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/expert/test_agent.py tests/unit/expert/test_runtime_planner.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/runtime/planner.py backend/engine/runtime/emitter.py backend/engine/expert/agent.py backend/engine/expert/tools.py tests/unit/expert/test_agent.py tests/unit/expert/test_runtime_planner.py
git commit -m "feat(expert): add dependency-aware planning and progressive sse"
```

### Task 4: Integrate shared runtime into JudgeRAG

**Files:**
- Modify: `backend/engine/arena/judge.py`
- Create: `tests/unit/arena/test_judge_runtime.py`

**Step 1: Write the failing test**

Add tests that prove:

- judge round eval uses fast-tier routing
- final verdict path still uses quality-tier routing
- `judge_*` event names remain compatible

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/arena/test_judge_runtime.py -v`

Expected: FAIL because JudgeRAG does not consume shared runtime components yet.

**Step 3: Write minimal implementation**

- use shared model router in judge paths
- reuse planner/emitter where low-risk
- preserve `judge_*` event naming

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/arena/test_judge_runtime.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/arena/judge.py tests/unit/arena/test_judge_runtime.py
git commit -m "feat(arena): reuse shared runtime in judge paths"
```

### Task 5: Reuse model routing and prefetch in Main Agent

**Files:**
- Modify: `backend/engine/agent/brain.py`
- Modify: `tests/unit/test_agent_brain.py`

**Step 1: Write the failing test**

Add tests that prove:

- Main Agent can obtain fast-tier model for lightweight analysis steps
- final decision synthesis keeps using quality-tier model
- candidate analysis can consume prefetch context without changing external behavior

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_brain.py -v`

Expected: FAIL because Main Agent still directly uses a single provider path.

**Step 3: Write minimal implementation**

- switch lightweight LLM lookups to shared router
- wire prefetch context into candidate analysis where safe
- keep execution and decision contract unchanged

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_brain.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/brain.py tests/unit/test_agent_brain.py
git commit -m "feat(agent): reuse model routing and prefetch context"
```

### Task 6: Final verification and TODO alignment

**Files:**
- Modify: `TODO.md`

**Step 1: Run focused expert tests**

Run: `pytest tests/unit/expert/test_agent.py tests/unit/expert/test_runtime_prefetch.py tests/unit/expert/test_runtime_planner.py -v`

Expected: PASS

**Step 2: Run shared runtime and judge tests**

Run: `pytest tests/unit/llm/test_model_router.py tests/unit/arena/test_judge_runtime.py -v`

Expected: PASS

**Step 3: Run Main Agent verification**

Run: `pytest tests/unit/test_agent_brain.py -v`

Expected: PASS

**Step 4: Run syntax/type safety checks**

Run: `python3 -m py_compile backend/engine/expert/agent.py backend/engine/arena/judge.py backend/engine/agent/brain.py backend/engine/runtime/context.py backend/engine/runtime/prefetch.py backend/engine/runtime/planner.py backend/engine/runtime/emitter.py backend/llm/config.py backend/llm/providers.py`

Expected: PASS

**Step 5: Update TODO**

Mark complete only if these are true:

- `quant` 无需 data 时可直接并行
- 数据专家结果可提前推送阶段性 SSE
- think/reply 已分层路由快慢模型
- 输入命中股票时已触发预取

**Step 6: Commit**

```bash
git add TODO.md backend/llm/config.py backend/llm/providers.py backend/engine/runtime backend/engine/expert/agent.py backend/engine/expert/tools.py backend/engine/arena/judge.py backend/engine/agent/brain.py tests/unit/llm/test_model_router.py tests/unit/expert/test_runtime_prefetch.py tests/unit/expert/test_runtime_planner.py tests/unit/arena/test_judge_runtime.py tests/unit/test_agent_brain.py docs/plans/2026-03-24-conversation-performance-optimization-design.md docs/plans/2026-03-24-conversation-performance-optimization.md
git commit -m "feat(runtime): complete conversation performance optimization module"
```
