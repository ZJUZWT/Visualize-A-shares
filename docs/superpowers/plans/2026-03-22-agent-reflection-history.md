# Agent Reflection And Strategy History Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the next Main Agent loop after review/memory infrastructure by persisting reflection artifacts, exposing strategy-history read models, and surfacing them on `/agent` without starting chat/adopt flows yet.

**Architecture:** Keep this batch on a strict write-path / read-path / UI split. Reflection persistence owns new journal tables and trade review writeback; read models expose normalized `/strategy/history` and `/reflections` APIs; frontend consumes only those contracts and keeps presentation components isolated from fetch/state orchestration.

**Tech Stack:** FastAPI, DuckDB, Pydantic, pytest, Next.js App Router, TypeScript

---

## Mainline

- Goal:
  - Make the agent visibly learn over time instead of only showing raw review rows and current state.
- Architecture boundary:
  - No `/api/v1/agent/chat`, no strategy adopt/reject flow, no SSE, no Industry/DataHunger work in this batch.
  - Reflection write path must remain deterministic and non-LLM for now.
  - Strategy history should be derived from existing persisted artifacts (`brain_runs.state_after`, `execution_summary`, `agent_state`) rather than inventing another snapshot table.
- Serial dependencies:
  - Merge Worker A before Worker B if Worker B’s routes depend on newly persisted reflection tables at runtime.
  - Worker C can start against the documented response shapes immediately.
- Non-goals:
  - Real-time market valuation
  - Manual reflection editing
  - Cost-control / token-budget plumbing

## Worker A — Reflection Write Path

- Owns:
  - `backend/engine/agent/db.py`
  - `backend/engine/agent/models.py`
  - `backend/engine/agent/review.py`
  - `tests/unit/test_agent_reflection_write_path.py`
- Must not touch:
  - `backend/engine/agent/service.py`
  - `backend/engine/agent/routes.py`
  - `frontend/**`
- Deliver:
  - Add `agent.daily_reviews` and `agent.weekly_reflections` tables.
  - Extend review write path so daily review also backfills `agent.trades.review_result/review_note/review_date/pnl_at_review` where applicable.
  - Persist one daily reflection row per review day and one weekly reflection row per week with deterministic summary fields from existing records.
  - Keep write behavior idempotent by date/week.
- Test ownership:
  - New dedicated file `tests/unit/test_agent_reflection_write_path.py`
  - Do not keep extending `test_agent_review_memory.py`
- Done when:
  - Running daily review twice does not duplicate `daily_reviews` or trade backfill.
  - Running weekly review twice does not duplicate `weekly_reflections`.
  - Existing review-memory tests still pass.
- Suggested TDD flow:
  1. Write failing table-creation and writeback tests in `tests/unit/test_agent_reflection_write_path.py`.
  2. Run only those tests and confirm red.
  3. Implement minimal schema and review-engine changes.
  4. Re-run focused tests until green.
  5. Run regression on review-related suites.
  6. Commit with a scoped message such as `feat(agent): persist reflection journals`.

## Worker B — Strategy History And Reflection Read Models

- Owns:
  - `backend/engine/agent/service.py`
  - `backend/engine/agent/routes.py`
  - `tests/unit/test_agent_strategy_history_read_models.py`
- Must not touch:
  - `backend/engine/agent/db.py`
  - `backend/engine/agent/models.py`
  - `backend/engine/agent/review.py`
  - `frontend/**`
- Deliver:
  - Add `GET /api/v1/agent/strategy/history?portfolio_id=...&limit=...`
  - Add `GET /api/v1/agent/reflections?limit=...`
  - `strategy/history` should return a stable timeline derived from completed brain runs and their `state_after` / `execution_summary`.
  - `reflections` should return a normalized mixed feed of daily and weekly reflection records ordered newest first.
- Important parallel rule:
  - Do not edit `db.py`. If your tests need reflection tables before Worker A merges, create those tables explicitly inside the test fixture/setup SQL.
- Test ownership:
  - New dedicated file `tests/unit/test_agent_strategy_history_read_models.py`
- Done when:
  - Service layer returns normalized, JSON-safe records.
  - Route tests cover happy path and missing-portfolio behavior for `strategy/history`.
  - Existing read-model suites still pass.
- Suggested TDD flow:
  1. Write failing service and route tests for `strategy/history` and `reflections`.
  2. Run targeted pytest command and confirm red.
  3. Implement service methods and routes only.
  4. Re-run focused tests until green.
  5. Run regression on agent read-model suites.
  6. Commit with a scoped message such as `feat(agent): add reflection and history read models`.

## Worker C — Agent Reflection / Evolution UI

- Owns:
  - `frontend/app/agent/page.tsx`
  - `frontend/app/agent/types.ts`
  - `frontend/app/agent/components/ReflectionFeedPanel.tsx`
  - `frontend/app/agent/components/StrategyHistoryPanel.tsx`
- Must not touch:
  - `backend/**`
  - Existing shared app shell components outside `frontend/app/agent/**`
- Deliver:
  - Add a new `/agent` tab for reflection/evolution surface.
  - Consume `GET /api/v1/agent/reflections` and `GET /api/v1/agent/strategy/history`.
  - Show reflection feed on the main column and strategy history timeline on the side column.
  - Keep fetch/state logic inside `page.tsx`; keep new panels presentational.
- Contract assumptions:
  - `reflections` returns a list with `kind`, `date`, `summary`, and structured metrics/details.
  - `strategy/history` returns a list with `run_id`, `occurred_at`, `market_view`, `position_level`, `sector_preferences`, `risk_alerts`, and execution counters.
  - Normalize nulls and tolerate missing optional fields.
- Done when:
  - `page.tsx` remains the orchestration layer only.
  - New tab renders empty/loading/error states cleanly.
  - `./node_modules/.bin/tsc --noEmit` and `npm run build` pass.
- Suggested TDD flow:
  1. Add types and panel props first.
  2. Wire fetch + normalization in `page.tsx`.
  3. Implement panels with empty/error/loading states.
  4. Run `tsc --noEmit`.
  5. Run `npm run build`.
  6. Commit with a scoped message such as `feat(agent-ui): add reflection and history console`.

## Review / Integration

- Reviewer:
  - Main session reviewer only. Workers do not self-approve architecture.
- Integration owner:
  - Main session
- Required regression tests:
  - `python3 -m pytest tests/unit/test_agent_review_memory.py tests/unit/test_agent_reflection_write_path.py -v`
  - `python3 -m pytest tests/unit/test_agent_read_models.py tests/unit/test_agent_review_read_models.py tests/unit/test_agent_strategy_history_read_models.py -v`
  - `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py tests/unit/test_trade_plans.py tests/unit/test_agent_phase1a.py -v`
  - `cd frontend && ./node_modules/.bin/tsc --noEmit`
  - `npm run build`
- Merge order:
  1. Worker A
  2. Worker B
  3. Worker C
- Review checklist:
  - Reflection writes are idempotent.
  - No new route reads raw pandas / timestamp objects.
  - Frontend does not call nonexistent endpoints or mis-format percentage fields.
  - No worker touched forbidden files.

## Handoff Notes

- This batch is the recommended next step because it builds directly on the newly merged review/memory infrastructure and reduces rework before chat/adopt flows.
- After this batch lands, the next high-value batch should be either:
  - `Phase 1B chat/adopt/reject`
  - or `Phase 1C watch-signals + DataHunger`
