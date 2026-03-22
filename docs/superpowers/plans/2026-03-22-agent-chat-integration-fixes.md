# Agent Chat Integration Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the review findings from the current chat/adopt/reject batch so the feature can be merged as a working end-to-end `/agent` experience instead of three individually-green but incompatible slices.

**Architecture:** Keep the same three-way split, but enlarge each worker’s scope so each one owns a coherent vertical slice rather than a narrow partial. Backend chat owns canonical SSE and session contracts plus central router mounting; backend strategy actions owns request/read-model stability; frontend owns full session-backed `/agent` chat orchestration against those canonical contracts.

**Tech Stack:** FastAPI, DuckDB, Pydantic, pytest, Next.js App Router, TypeScript, React

---

## Mainline

- This is a remediation-and-integration batch, not a new feature batch.
- Do not start Wake / DataHunger / next-phase work until this plan lands.
- Canonical contract choices for this batch:
  - Agent chat uses expert-style SSE event names: `reply_token`, `reply_complete`, `error`
  - Chat endpoints are namespaced under `/api/v1/agent/chat/...`
  - Strategy actions always include enough metadata to rehydrate UI state deterministically
  - `/agent` must use persisted sessions, not ephemeral local-only chat history
- Worker lifecycle requirement:
  - Before starting, each worker should delete only stale worker shells that are already merged into `main`, explicitly accepted and superseded, or patch-equivalent to `main`.
  - Do not delete the current unmerged chat implementation branches from the prior batch; they remain reference inputs for this remediation batch until merge is complete.
  - Each worker then creates a fresh branch from current local `main` and a fresh worktree under `.worktrees/`.
  - Each summary must include cleanup status for both the old worker state and the new worker state.

## Worker A — Chat Contract And Session API

- Proposed branch/worktree:
  - `batch-2026-03-22-agent-chat-contract-a`
  - `.worktrees/batch-2026-03-22-agent-chat-contract-a`
- Owns:
  - `backend/engine/agent/chat.py`
  - `backend/engine/agent/chat_routes.py`
  - `backend/engine/agent/routes.py`
  - `tests/unit/test_agent_chat.py`
- Must not touch:
  - `backend/engine/agent/models.py`
  - `backend/engine/agent/strategy_actions.py`
  - `backend/engine/agent/strategy_action_routes.py`
  - `frontend/**`
- Deliver:
  - Mount the chat router into `create_agent_router()`
  - Namespace chat session APIs under `/chat/sessions`
  - Add missing session deletion support
  - Keep SSE contract aligned with expert chat naming and payload keys
  - Add route tests that cover mounted `/api/v1/agent/chat/...` endpoints, not only standalone router behavior
- Required TDD checkpoints:
  - red: mounted route tests fail on missing namespace/delete behavior
  - green: mounted route tests pass
  - regression: existing agent route tests still pass
- Done when:
  - frontend can call `/api/v1/agent/chat`, `/api/v1/agent/chat/sessions`, `/api/v1/agent/chat/sessions/{id}/messages`
  - no standalone-only contract remains

## Worker B — Strategy Action Contract And Rehydration Read Model

- Proposed branch/worktree:
  - `batch-2026-03-22-agent-action-contract-b`
  - `.worktrees/batch-2026-03-22-agent-action-contract-b`
- Owns:
  - `backend/engine/agent/models.py`
  - `backend/engine/agent/strategy_actions.py`
  - `backend/engine/agent/strategy_action_routes.py`
  - `backend/engine/agent/routes.py`
  - `backend/engine/agent/memory.py`
  - `tests/unit/test_agent_strategy_actions.py`
- Must not touch:
  - `backend/engine/agent/chat.py`
  - `backend/engine/agent/chat_routes.py`
  - `frontend/**`
- Deliver:
  - Mount strategy-action routes into `create_agent_router()`
  - Finalize canonical request bodies for adopt/reject
  - Ensure `GET /strategy-actions` supports required filters and returns a stable UI-facing read model with:
    - `session_id`
    - `message_id`
    - `strategy_key`
    - `decision/status`
    - linked ids
    - enough plan metadata if `strategy_key` must be derived server-side
  - Preserve idempotency and memory feedback behavior
- Required TDD checkpoints:
  - red: route tests fail on request-shape mismatch and missing rehydration fields
  - green: route + service tests pass with canonical payloads
  - regression: trade-plan and memory suites still pass
- Done when:
  - frontend can safely POST adopt/reject without guessing payload shape
  - reload can deterministically map action rows back onto strategy cards

## Worker C — Session-Backed `/agent` Chat UI

- Proposed branch/worktree:
  - `batch-2026-03-22-agent-session-ui-c`
  - `.worktrees/batch-2026-03-22-agent-session-ui-c`
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
  - Add active session state and session list UI
  - Load persisted messages from the selected session
  - Create or reuse a session before sending chat
  - Parse backend SSE using canonical `reply_token` / `reply_complete`
  - Send adopt/reject payloads using the backend’s finalized request models
  - Rehydrate action states from `GET /strategy-actions?session_id=...`
  - Preserve the current run/review/memory/reflection console surfaces
- Verification:
  - `cd frontend && ./node_modules/.bin/tsc --noEmit`
  - `cd frontend && npm run build`
- Done when:
  - refresh no longer loses the current conversation
  - multiple sends stay in one backend session
  - strategy cards render persisted adopt/reject state after reload

## Review / Integration

- Merge order:
  1. Worker A
  2. Worker B
  3. Worker C
- Required fresh verification:
  - `python3 -m pytest tests/unit/test_agent_chat.py tests/unit/test_agent_strategy_actions.py -v`
  - `python3 -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py -v`
  - `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py tests/unit/test_agent_read_models.py tests/unit/test_agent_review_read_models.py tests/unit/test_agent_strategy_history_read_models.py -v`
  - `cd frontend && ./node_modules/.bin/tsc --noEmit`
  - `cd frontend && npm run build`
- Review checklist:
  - no SSE naming mismatch remains
  - no request-body mismatch remains
  - `/agent` uses real persisted sessions
  - worker summaries record branch/worktree cleanup status

## Handoff Notes

- After this plan lands and is merged cleanly, the next big batch can move to Wake / WatchSignal / DataHunger.
