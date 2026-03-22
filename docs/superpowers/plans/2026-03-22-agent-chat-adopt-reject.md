# Agent Chat And Adopt Reject Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `/agent` usable as a real strategy conversation surface by adding agent chat sessions, structured strategy adopt/reject actions, and a chat-first UI without regressing the existing brain / review / reflection consoles.

**Architecture:** Reuse the mature expert SSE event contract instead of inventing a second streaming protocol. Persist agent-specific chat sessions and messages in `agent.duckdb`, then treat adopt/reject as a separate domain write path that only accepts structured strategy-card payloads, records user intent, writes through existing plan / trade / strategy primitives, and feeds rejection reasons back into agent memory.

**Tech Stack:** FastAPI, DuckDB, Pydantic, pytest, Next.js App Router, TypeScript, React

---

## Mainline

- Product target:
  - `/agent` should support discussion, strategy proposal, one-click adoption, and one-click rejection with memory feedback.
- Core contract:
  - Agent replies keep using `【交易计划】...【/交易计划】` blocks so the existing parser in `frontend/lib/parseTradePlan.ts` remains the single structured-plan extraction path.
  - Chat streaming events should match the existing expert event names: `thinking_start`, `thinking_round`, `graph_recall`, `tool_call`, `tool_result`, `reply_token`, `reply_complete`, `belief_updated`, `error`.
  - Adopt/reject is only allowed from parsed structured plans, never from arbitrary free-text.
- Domain rules for this batch:
  - Chat sessions are scoped to `portfolio_id`.
  - `adopt` creates an agent-sourced trade plan, records an action row, and writes to the virtual portfolio through existing trade/strategy flows.
  - `reject` records the action row and writes a memory rule when the user supplies a reason.
  - For `buy` strategies, if an open position already exists for the same `stock_code`, the adopted trade becomes `add`; otherwise it becomes `buy`.
  - For `sell` strategies, there must be an open position for the same `stock_code`; action becomes `reduce` for partial size and `sell` for full exit.
  - Buy/add quantity is derived from `position_pct` of total assets, default `0.1` when absent, rounded down to A-share board lot `100`.
- Non-goals:
  - Wake/DataHunger/watch-signal automation
  - Full autonomous execution from chat text
  - Real-time mark-to-market pricing
  - Reworking `/expert` or shared trade-plan parser contracts
- Important integration constraint:
  - Workers create dedicated router modules, not direct edits to `backend/engine/agent/routes.py`.
  - Main session wires those routers into `create_agent_router()` during review/integration to avoid cross-worker conflicts on the central file.

## Worker A — Agent Chat Backend And Persistence

- Owns:
  - `backend/engine/agent/db.py`
  - `backend/engine/agent/chat.py`
  - `backend/engine/agent/chat_routes.py`
  - `tests/unit/test_agent_chat.py`
- Must not touch:
  - `backend/engine/agent/routes.py`
  - `backend/engine/agent/models.py`
  - `backend/engine/agent/service.py`
  - `backend/engine/agent/memory.py`
  - `frontend/**`
- Deliver:
  - Add `agent.chat_sessions`, `agent.chat_messages`, and `agent.strategy_actions` tables to `AgentDB`.
  - Implement an `AgentChatService` in `backend/engine/agent/chat.py` that:
    - validates `portfolio_id`
    - builds agent context from existing portfolio/state/watchlist data
    - reuses expert-agent style streaming instead of inventing a new event protocol
    - persists user + assistant messages, including serialized `thinking`
  - Implement a dedicated router factory in `backend/engine/agent/chat_routes.py` exposing:
    - `GET /chat/sessions?portfolio_id=...`
    - `POST /chat/sessions`
    - `DELETE /chat/sessions/{session_id}`
    - `GET /chat/sessions/{session_id}/messages`
    - `POST /chat` as `text/event-stream`
  - Keep this router self-contained so the main session can later mount it inside `create_agent_router()`.
- Test ownership:
  - `tests/unit/test_agent_chat.py`
- Required test cases:
  - session list is filtered by `portfolio_id`
  - missing portfolio returns 404/validation error
  - `POST /chat` emits at least `reply_token` then `reply_complete`
  - user and assistant messages are persisted in `agent.chat_messages`
  - stored `thinking` payload is JSON-safe
- Suggested TDD flow:
  1. Write failing tests in `tests/unit/test_agent_chat.py`.
  2. Run `python3 -m pytest tests/unit/test_agent_chat.py -v` and confirm red.
  3. Add schema changes and minimal chat service/router code.
  4. Re-run `python3 -m pytest tests/unit/test_agent_chat.py -v` until green.
  5. Run `python3 -m pytest tests/unit/test_agent_chat.py tests/unit/test_agent_phase1a.py -v`.
  6. Commit with a scoped message such as `feat(agent): add chat persistence and streaming`.
- Done when:
  - chat session CRUD works without touching central `routes.py`
  - SSE contract matches expert chat event names
  - persisted messages can be reloaded by session

## Worker B — Strategy Adopt Reject Domain Write Path

- Owns:
  - `backend/engine/agent/models.py`
  - `backend/engine/agent/memory.py`
  - `backend/engine/agent/strategy_actions.py`
  - `backend/engine/agent/strategy_action_routes.py`
  - `tests/unit/test_agent_strategy_actions.py`
- Must not touch:
  - `backend/engine/agent/db.py`
  - `backend/engine/agent/chat.py`
  - `backend/engine/agent/chat_routes.py`
  - `backend/engine/agent/routes.py`
  - `frontend/**`
- Deliver:
  - Add action request/response models for adopt/reject and action readbacks.
  - Implement `StrategyActionService` in `backend/engine/agent/strategy_actions.py` that:
    - idempotently records action state keyed by `session_id + message_id + stock_code`
    - creates an agent-sourced trade plan via existing plan primitives
    - computes executable quantity from plan payload + portfolio state
    - writes through existing trade/position strategy flows
    - updates the action row with linked `plan_id`, `trade_id`, `position_id`, and `strategy_id`
    - on rejection, records reason text and writes a memory rule via `MemoryManager`
  - Update `MemoryManager` so rejection feedback can be added with nullable `source_run_id`.
  - Implement a dedicated router factory in `backend/engine/agent/strategy_action_routes.py` exposing:
    - `POST /adopt-strategy`
    - `POST /reject-strategy`
    - `GET /strategy-actions?session_id=...`
- Parallel constraint:
  - Do not edit `db.py`.
  - If your tests need `agent.strategy_actions` before Worker A merges, create that table explicitly inside test setup SQL in `tests/unit/test_agent_strategy_actions.py`.
- Domain rules to implement:
  - `buy` + no open position -> `buy`
  - `buy` + existing open position -> `add`
  - `sell` + matching open position -> `reduce` or `sell` based on derived quantity
  - `sell` + no matching open position -> 400
  - successful adopt sets the linked trade plan status to `executing`
  - repeated adopt/reject returns the existing action record instead of duplicating writes
- Test ownership:
  - `tests/unit/test_agent_strategy_actions.py`
- Required test cases:
  - adopt buy opens a new position and writes action linkage
  - adopt buy on existing holding turns into `add`
  - reject stores reason and creates a memory rule
  - reject/adopt repeated calls are idempotent
  - reject without reason still records the action row but does not crash memory writes
- Suggested TDD flow:
  1. Write failing tests in `tests/unit/test_agent_strategy_actions.py`.
  2. Run `python3 -m pytest tests/unit/test_agent_strategy_actions.py -v` and confirm red.
  3. Implement minimal models, memory tweak, service, and router code.
  4. Re-run `python3 -m pytest tests/unit/test_agent_strategy_actions.py -v` until green.
  5. Run `python3 -m pytest tests/unit/test_agent_strategy_actions.py tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py -v`.
  6. Commit with a scoped message such as `feat(agent): add strategy adopt reject actions`.
- Done when:
  - adopt/reject can be mounted without editing the central router
  - writes are idempotent and linked to existing ledger entities
  - rejection reasons become reusable memory rules

## Worker C — `/agent` Chat-First Console UI

- Owns:
  - `frontend/app/agent/page.tsx`
  - `frontend/app/agent/types.ts`
  - `frontend/app/agent/components/AgentChatPanel.tsx`
  - `frontend/app/agent/components/AgentChatComposer.tsx`
  - `frontend/app/agent/components/AgentChatMessage.tsx`
  - `frontend/app/agent/components/AgentStrategyActionCard.tsx`
- Must not touch:
  - `backend/**`
  - `frontend/components/expert/**`
  - `frontend/components/plans/TradePlanCard.tsx`
  - `frontend/lib/parseTradePlan.ts`
- Deliver:
  - Reshape `/agent` into a chat-first surface while preserving the existing run/review/memory/reflection panels.
  - Left side should become the agent chat stack:
    - session list
    - message history
    - composer
    - structured strategy cards with adopt/reject actions
  - Middle/right columns should keep existing brain and ledger/reflection panels rather than rebuilding them.
  - Add frontend fetch/stream handling for:
    - `GET /api/v1/agent/chat/sessions?portfolio_id=...`
    - `POST /api/v1/agent/chat/sessions`
    - `GET /api/v1/agent/chat/sessions/{session_id}/messages`
    - `POST /api/v1/agent/chat`
    - `GET /api/v1/agent/strategy-actions?session_id=...`
    - `POST /api/v1/agent/adopt-strategy`
    - `POST /api/v1/agent/reject-strategy`
  - Reuse `splitByTradePlan()` and `hasTradePlan()` so agent strategy cards parse exactly like expert plan cards.
- UI constraints:
  - `page.tsx` remains the orchestration layer only.
  - New components are presentational and agent-specific.
  - Existing reflection/history/ledger fetches must keep working.
  - Empty/loading/error states must be explicit for chat session list, message stream, and action buttons.
- Contract assumptions:
  - Chat message shape includes `id`, `role`, `content`, `thinking`, `created_at`
  - Strategy action read model includes `message_id`, `stock_code`, `status`, `reason`, and linked entity ids
  - SSE event names match expert chat
- Suggested implementation flow:
  1. Extend `frontend/app/agent/types.ts` with chat session, message, action, and event types.
  2. Add new agent chat components under `frontend/app/agent/components/`.
  3. Move chat/session/request orchestration into `frontend/app/agent/page.tsx`.
  4. Hook strategy-card adopt/reject actions to the new endpoints.
  5. Run `cd frontend && ./node_modules/.bin/tsc --noEmit`.
  6. Run `cd frontend && npm run build`.
  7. Commit with a scoped message such as `feat(agent-ui): add chat adopt reject console`.
- Done when:
  - `/agent` is usable without leaving the page for strategy discussion
  - action buttons reflect adopted/rejected state after reload
  - existing non-chat agent panels still render

## Review / Integration

- Reviewer:
  - Main session only
- Integration ownership:
  - Main session mounts new router modules inside `backend/engine/agent/routes.py`
  - Main session resolves any light contract mismatches between worker A/B and the existing `/agent` page
- Required integration edits:
  - Wire `create_agent_chat_router()` into `create_agent_router()`
  - Wire `create_strategy_action_router()` into `create_agent_router()`
  - Keep central route prefixes under `/api/v1/agent`
- Merge order:
  1. Worker A
  2. Worker B
  3. Worker C
- Fresh regression commands:
  - `python3 -m pytest tests/unit/test_agent_chat.py tests/unit/test_agent_strategy_actions.py -v`
  - `python3 -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py -v`
  - `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py tests/unit/test_agent_read_models.py tests/unit/test_agent_review_read_models.py tests/unit/test_agent_strategy_history_read_models.py -v`
  - `cd frontend && ./node_modules/.bin/tsc --noEmit`
  - `cd frontend && npm run build`
- Review checklist:
  - Agent chat and expert chat use the same SSE event semantics
  - No worker silently edited `backend/engine/agent/routes.py`
  - Adopt/reject is idempotent and records linkage ids
  - Rejection memory writes remain JSON-safe and do not require `source_run_id`
  - `/agent` keeps reflection/history/review tabs intact after chat layout changes

## Handoff Notes

- This batch intentionally stops at chat-driven manual acceptance/rejection.
- After this lands, the next high-value batch should be `Wake / WatchSignal / DataHunger`.
