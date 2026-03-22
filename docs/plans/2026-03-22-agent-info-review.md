# Agent Info Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Main Agent 在日复盘 / 周反思里开始审计 `info_digests` 的有效性与误导性，形成最小“信息复盘”闭环。

**Architecture:** 不新增表，直接扩展现有 `daily_reviews` 和 `weekly_reflections`。`ReviewEngine` 负责生成结构化 info-review 数据，`AgentService.list_reflections()` 负责把它映射到 reflection feed 的 `details.info_review`。

**Tech Stack:** Python 3.11, DuckDB, pytest, existing `ReviewEngine`, `AgentService`, `DataHunger` / `BrainRun` persistence

---

### Task 1: Extend Reflection Journal Schema For Info Review

**Files:**
- Modify: `backend/engine/agent/db.py`
- Modify: `backend/engine/agent/models.py`
- Modify: `tests/unit/test_agent_review_memory.py`

**Step 1: Write the failing test**

Add schema/model assertions for:

- `daily_reviews.info_review_summary`
- `daily_reviews.info_review_details`
- `weekly_reflections.info_review_summary`
- `weekly_reflections.info_review_details`

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "schema or reflection" -q`

Expected: FAIL because the columns and model fields do not exist yet.

**Step 3: Write minimal implementation**

Add idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` statements and extend `DailyReview` / `WeeklyReflection` models.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "schema or reflection" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/models.py tests/unit/test_agent_review_memory.py
git commit -m "feat(agent): extend reflection journals for info review"
```

---

### Task 2: Add Daily Info Review Generation

**Files:**
- Modify: `backend/engine/agent/review.py`
- Modify: `tests/unit/test_agent_review_memory.py`

**Step 1: Write the failing test**

Add a daily review test that:

- creates a completed brain run with `info_digest_ids`
- creates matching rows in `agent.info_digests`
- runs `daily_review()`
- asserts `daily_reviews.info_review_summary` and `info_review_details` are filled

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "daily and info_review" -q`

Expected: FAIL because `daily_review()` does not build info-review data yet.

**Step 3: Write minimal implementation**

In `review.py`:

- collect related digests for the review day
- classify each digest as `useful` / `misleading` / `inconclusive` / `noted`
- compute `top_missing_sources`
- persist `info_review_summary` and `info_review_details` in `_ensure_daily_review_journal()`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "daily and info_review" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/review.py tests/unit/test_agent_review_memory.py
git commit -m "feat(agent): add daily info review summaries"
```

---

### Task 3: Aggregate Weekly Info Review

**Files:**
- Modify: `backend/engine/agent/review.py`
- Modify: `tests/unit/test_agent_review_memory.py`

**Step 1: Write the failing test**

Add a weekly review test asserting:

- weekly reflection stores aggregated info-review counters
- weekly info-review summary text is present
- top missing sources are aggregated from daily entries

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "weekly and info_review" -q`

Expected: FAIL because weekly aggregation does not consider info-review data yet.

**Step 3: Write minimal implementation**

Update `weekly_review()` and `_ensure_weekly_reflection()` to:

- aggregate daily info-review details for the week
- persist weekly `info_review_summary` / `info_review_details`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "weekly and info_review" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/review.py tests/unit/test_agent_review_memory.py
git commit -m "feat(agent): aggregate weekly info review"
```

---

### Task 4: Surface Info Review In Reflection Read Models

**Files:**
- Modify: `backend/engine/agent/service.py`
- Modify: `tests/unit/test_agent_review_memory.py`

**Step 1: Write the failing test**

Add a read-model test asserting `/reflections`-style items contain:

- `details.info_review`
- `summary` including the extra info-review text when present

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "reflections and info_review" -q`

Expected: FAIL because the read model does not expose these fields.

**Step 3: Write minimal implementation**

Update `_build_daily_reflection_item()` and `_build_weekly_reflection_item()` to include `info_review` in `details`.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -k "reflections and info_review" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_review_memory.py
git commit -m "feat(agent): expose info review in reflections"
```

---

### Task 5: Run Review/Agent Regression

**Files:**
- Review only: touched files from prior tasks

**Step 1: Run focused suite**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py -q`

Expected: PASS

**Step 2: Run broader regression**

Run: `python3 -m pytest tests/unit/test_agent_review_memory.py tests/unit/test_agent_brain.py tests/unit/test_agent_data_hunger.py tests/unit/test_agent_phase1a.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/models.py backend/engine/agent/review.py backend/engine/agent/service.py tests/unit/test_agent_review_memory.py docs/plans/2026-03-22-agent-info-review-design.md docs/plans/2026-03-22-agent-info-review.md
git commit -m "feat(agent): add info review reflections"
```
