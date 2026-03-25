# Prompt Persona Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构 `expert` 对话链路中的投资顾问与短线专家人格，使两者在同一问题下能稳定给出不同分析框架与意见。

**Architecture:** 在 `backend/engine/expert/personas.py` 中新增结构化 persona profile 与 prompt builder，统一生成 `think` 和 `reply` prompt；在 `backend/engine/expert/agent.py` 中改为调用 builder，而不再维护分散的手写 prompt 分支。通过 `tests/unit/expert/test_personas.py` 锁定身份、禁忌、冲突立场和 few-shot 差异。

**Tech Stack:** Python 3.11, pytest

---

### Task 1: Add failing persona contract tests

**Files:**
- Modify: `tests/unit/expert/test_personas.py`
- Modify: `backend/engine/expert/personas.py`

**Step 1: Write the failing test**

Add tests covering:

- structured persona profiles exist for `rag` and `short_term`
- investment-advisor think/reply prompts include:
  - safety margin
  - position management
  - anti-chasing / no intraday calls
- short-term prompts include:
  - timing
  - volume-price / tape reading
  - stop-loss discipline
  - anti-valuation / anti-three-year-narrative
- both personas explicitly allow conflict with the other role
- each persona has at least 3 few-shot examples

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/expert/test_personas.py -q`

Expected: FAIL because the structured persona profile and builders do not exist yet.

**Step 3: Write minimal implementation**

In `backend/engine/expert/personas.py`:

- add structured persona profiles
- add prompt builder helpers
- keep compatibility exports where useful

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/expert/test_personas.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/expert/test_personas.py backend/engine/expert/personas.py
git commit -m "feat(expert): add structured persona prompt profiles"
```

### Task 2: Route expert think prompts through persona builders

**Files:**
- Modify: `backend/engine/expert/agent.py`
- Test: `tests/unit/expert/test_personas.py`

**Step 1: Write the failing test**

Add coverage proving the exported builder-generated think prompts differ by persona and still include:

- graph context placeholder / content
- memory context placeholder / content
- expert dispatch rules

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/expert/test_personas.py -k "think" -q`

Expected: FAIL because `agent.py` still depends on legacy prompt branches.

**Step 3: Write minimal implementation**

In `backend/engine/expert/agent.py`:

- replace direct `THINK_SYSTEM_PROMPT` / `SHORT_TERM_THINK_PROMPT` branching
- call `build_think_prompt(...)`
- keep existing tool-dispatch and context-guard flow unchanged

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/expert/test_personas.py -k "think" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/expert/agent.py tests/unit/expert/test_personas.py
git commit -m "refactor(expert): route think prompts through persona builders"
```

### Task 3: Route expert reply prompts through persona builders

**Files:**
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/expert/personas.py`
- Test: `tests/unit/expert/test_personas.py`

**Step 1: Write the failing test**

Add tests covering:

- reply builder for `rag` is稳重、重风险收益比、避免短线催促
- reply builder for `short_term` is果断、重节奏和价位、避免长期估值叙事
- same persona builders expose distinct few-shot tone and output priorities

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/expert/test_personas.py -k "reply or few_shot" -q`

Expected: FAIL because reply prompts are still partly inline and not generated from shared profiles.

**Step 3: Write minimal implementation**

In `backend/engine/expert/personas.py`:

- add `build_reply_system(...)`

In `backend/engine/expert/agent.py`:

- replace inline investment-advisor reply system and short-term branch
- keep existing context assembly and history wiring intact

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/expert/test_personas.py -k "reply or few_shot" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/expert/personas.py backend/engine/expert/agent.py tests/unit/expert/test_personas.py
git commit -m "feat(expert): unify reply personas with few-shot builders"
```

### Task 4: Run focused expert regressions and align TODO

**Files:**
- Modify: `TODO.md`
- Review only: touched expert persona files

**Step 1: Run persona and expert regressions**

Run: `python3 -m pytest tests/unit/expert/test_personas.py tests/unit/expert/test_scheduler.py tests/integration/test_personas.py -q`

Expected: PASS

**Step 2: Update TODO module status**

In `TODO.md`, mark the Prompt Persona Optimization items complete only if the code/tests prove:

- 投资顾问人格深化
- 短线专家人格深化
- 人格冲突设计
- Few-shot 人格校准

**Step 3: Run final verification**

Run: `python3 -m pytest tests/unit/expert/test_personas.py tests/unit/expert/test_scheduler.py tests/integration/test_personas.py -q`

Expected: PASS

**Step 4: Commit**

```bash
git add TODO.md tests/unit/expert/test_personas.py tests/integration/test_personas.py backend/engine/expert/personas.py backend/engine/expert/agent.py
git commit -m "feat(expert): complete prompt persona optimization module"
```
