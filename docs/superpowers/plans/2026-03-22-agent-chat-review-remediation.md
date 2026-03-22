# Agent Chat Review Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the two blocking review findings from `2026-03-22-agent-chat-integration-fixes` so the agent chat feature can be reintegrated without repeating the same contract failures.

**Architecture:** This is a narrow remediation batch, not a fresh feature batch. The remaining work splits cleanly into two write sets: backend strategy-action contract/idempotency correction, and frontend `/agent` payload alignment against that canonical contract. Previous unmerged chat/action/ui branches remain read-only reference inputs; new worker branches must still be cut from current local `main`.

**Tech Stack:** FastAPI, DuckDB, Pydantic, pytest, Next.js App Router, TypeScript, React

---

## Mainline

- This batch fixes only the blockers found in review:
  - frontend adopt/reject payload still uses old `trade_plan` shape
  - backend strategy-action uniqueness/idempotency still collapses different strategy cards for the same stock within one message
- Do not reopen the chat router slice here. Worker A from the previous batch is treated as a reference input, not an active write target.
- Parallelism is pinned to `2` for this batch because only two disjoint write sets remain. Future batches should still default to `parallelism=auto` unless the task graph clearly says otherwise.
- Reference inputs that may be read but not reused as bases:
  - `batch-2026-03-22-agent-chat-contract-a`
  - `batch-2026-03-22-agent-action-contract-b`
  - `batch-2026-03-22-agent-session-ui-c`
- Worker lifecycle requirement:
  - Before starting, each worker should delete only stale worker shells already merged into `main`, explicitly accepted and superseded, or patch-equivalent to `main`.
  - Do not delete the current unmerged reference branches/worktrees listed above.
  - Each worker then creates a fresh branch from current local `main@1b42801` and a fresh worktree under `.worktrees/`.
  - Each summary must include cleanup status for both old worker state and new worker state.

## Worker A — Strategy Action Remediation

- Proposed branch/worktree:
  - `batch-2026-03-22-agent-action-remediation-a`
  - `.worktrees/batch-2026-03-22-agent-action-remediation-a`
- Read-only reference inputs:
  - `batch-2026-03-22-agent-action-contract-b`
  - `batch-2026-03-22-agent-chat-integration-fixes/outputs/worker-b-summary.md`
- Owns:
  - `backend/engine/agent/models.py`
  - `backend/engine/agent/strategy_actions.py`
  - `backend/engine/agent/strategy_action_routes.py`
  - `tests/unit/test_agent_strategy_actions.py`
- Must not touch:
  - `backend/engine/agent/chat.py`
  - `backend/engine/agent/chat_routes.py`
  - `backend/engine/agent/routes.py`
  - `frontend/**`
- Deliver:
  - Keep canonical request bodies centered on `strategy_key + plan`
  - Tighten uniqueness/idempotency so the canonical identity is `session_id + message_id + strategy_key`
  - Remove the stock-code fallback that incorrectly treats different cards for the same stock as duplicates
  - Add regression coverage for same-session same-message same-stock but different-strategy-key actions
  - Preserve legacy row rehydration where `strategy_key` must be derived from stored snapshot/plan data for reads
- Required TDD checkpoints:
  - red: add a failing test that submits two distinct strategies for the same stock within one message and prove they are currently collapsed
  - green: service and route behavior keep both actions distinct
  - regression: existing strategy-action and memory/trade-plan suites still pass
- Suggested verification:
  - `python3 -m pytest tests/unit/test_agent_strategy_actions.py -q`
  - `python3 -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py -q`
- Done when:
  - a second strategy card with a different `strategy_key` no longer reuses the first action row
  - the API contract still accepts only the canonical `plan` body

## Worker B — `/agent` UI Contract Remediation

- Proposed branch/worktree:
  - `batch-2026-03-22-agent-ui-remediation-b`
  - `.worktrees/batch-2026-03-22-agent-ui-remediation-b`
- Read-only reference inputs:
  - `batch-2026-03-22-agent-session-ui-c`
  - `batch-2026-03-22-agent-chat-contract-a`
  - `batch-2026-03-22-agent-action-contract-b`
  - `batch-2026-03-22-agent-chat-integration-fixes/outputs/worker-c-summary.md`
- Owns:
  - `frontend/app/agent/page.tsx`
  - `frontend/app/agent/types.ts`
  - `frontend/app/agent/components/AgentChatPanel.tsx`
  - `frontend/app/agent/components/AgentChatComposer.tsx`
  - `frontend/app/agent/components/AgentChatMessage.tsx`
  - `frontend/app/agent/components/AgentStrategyActionCard.tsx`
- Must not touch:
  - `backend/**`
  - shared expert components
  - `frontend/lib/parseTradePlan.ts`
- Deliver:
  - Port the prior session-backed `/agent` UI slice onto a fresh branch from `main`
  - Align adopt/reject writes to the backend canonical request body:
    - `portfolio_id`
    - `session_id`
    - `message_id`
    - `strategy_key`
    - `plan`
    - `reason?`
    - `source_run_id?` only if already available
  - Remove old `trade_plan` / `stock_code` write assumptions from the request body
  - Keep action lookup keyed by `message_id + strategy_key`
  - Keep session-backed chat flow and canonical SSE parsing from the previous UI branch
- Verification:
  - If the worktree lacks `frontend/node_modules`, do not install dependencies. Run the workspace-root binaries against the worktree:
    - `/Users/swannzhang/Workspace/AIProjects/A_Claude/frontend/node_modules/.bin/tsc --noEmit`
    - `/Users/swannzhang/Workspace/AIProjects/A_Claude/frontend/node_modules/.bin/next build`
  - Run both commands from inside the worker worktree `frontend/` directory
- Done when:
  - the UI no longer posts `trade_plan`
  - the UI request body matches Worker A's canonical Pydantic models
  - session-backed chat and action rehydration behavior from the previous UI slice remains intact

## Review / Integration

- Merge order:
  1. Worker A
  2. Worker B
- Required fresh verification:
  - `python3 -m pytest tests/unit/test_agent_strategy_actions.py -v`
  - `python3 -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py -v`
  - `cd frontend && /Users/swannzhang/Workspace/AIProjects/A_Claude/frontend/node_modules/.bin/tsc --noEmit`
  - `cd frontend && /Users/swannzhang/Workspace/AIProjects/A_Claude/frontend/node_modules/.bin/next build`
- Review checklist:
  - no 422 request-body mismatch remains for adopt/reject
  - same-message same-stock different-strategy-key actions remain distinct
  - worker summaries record cleanup status for both old and new worker shells

## Handoff Notes

- After this remediation batch passes review, return to the prior integration line and merge the corrected slices instead of reviving the old broken worker branches.
