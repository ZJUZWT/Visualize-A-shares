# Agent Decision Quality Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 提升 Main Agent 的单次决策质量，让 wake/data-hunger/memory 真正进入“先质疑、后执行”的闭环，而不是只把更多上下文堆给 LLM。

**Architecture:** 在 `backend/engine/agent` 下新增一层纯函数化的 decision quality 模块，负责 prompt builder、响应解析和执行前门禁。`brain.py` 退回为 orchestration 层，只做上下文收集、LLM 调用、审计落库和 execution 调用。

**Tech Stack:** Python 3.11, pytest, existing `AgentBrain`, `AgentService`, `DataHungerService`, existing LLM provider API

---

### Task 1: Add Decision Quality Helpers With Failing Unit Tests

**Files:**
- Create: `backend/engine/agent/decision_quality.py`
- Create: `tests/unit/test_agent_decision_quality.py`

**Step 1: Write the failing test**

Add tests for:

- `build_system_prompt()` includes information-immunity rules
- `build_decision_context()` includes digest and signal context
- `parse_decision_payload()` handles fenced JSON and malformed payloads
- `gate_decisions()` drops incomplete or low-confidence actions

```python
def test_build_system_prompt_includes_information_immunity_principles():
    prompt = build_system_prompt()
    assert "默认态度是怀疑" in prompt
    assert "不要因为单条消息改变策略" in prompt


def test_gate_decisions_rejects_actions_when_self_critique_says_wait():
    payload = {
        "self_critique": ["证据不足，等待确认"],
        "decisions": [{"stock_code": "600519", "action": "buy", "price": 1, "quantity": 100, "take_profit": 2, "stop_loss": 0.5, "confidence": 0.9}],
    }
    result = gate_decisions(payload)
    assert result.accepted == []
    assert result.rejected[0]["reason"] == "self_critique_requires_wait"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_decision_quality.py -q`

Expected: FAIL because the module does not exist yet.

**Step 3: Write minimal implementation**

Implement pure helpers:

- `build_system_prompt() -> str`
- `build_decision_context(...) -> str`
- `parse_decision_payload(raw: str) -> dict`
- `gate_decisions(payload: dict, min_confidence: float = 0.65) -> GateResult`

Keep the gate rules minimal and explicit.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_decision_quality.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/decision_quality.py tests/unit/test_agent_decision_quality.py
git commit -m "feat(agent): add decision quality helpers"
```

---

### Task 2: Refactor `AgentBrain` To Use Prompt Builder And Structured Payload

**Files:**
- Modify: `backend/engine/agent/brain.py`
- Modify: `tests/unit/test_agent_brain.py`
- Test: `tests/unit/test_agent_decision_quality.py`

**Step 1: Write the failing test**

Add brain tests for:

- `thinking_process` stores `system_prompt`, `decision_context`, `self_critique`, `follow_up_questions`
- malformed payload degrades to empty decisions

```python
async def test_brain_persists_structured_thinking_process(...):
    await brain.execute(run_id)
    run = await service.get_brain_run(run_id)
    assert "system_prompt" in run["thinking_process"]
    assert "gate_result" in run["thinking_process"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "thinking or critique or gate" -q`

Expected: FAIL because `brain.py` still persists only raw `prompt`.

**Step 3: Write minimal implementation**

In `brain.py`:

- replace inline giant prompt with `build_system_prompt()` and `build_decision_context()`
- send `[system, user]` messages to LLM
- parse payload via `parse_decision_payload()`
- persist full structured thinking process

Do not change execution yet beyond feeding it gated decisions.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -k "thinking or critique or gate" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/brain.py tests/unit/test_agent_brain.py
git commit -m "refactor(agent): structure decision prompting"
```

---

### Task 3: Add Execution Gate Before Plan/Trade Creation

**Files:**
- Modify: `backend/engine/agent/brain.py`
- Modify: `tests/unit/test_agent_brain.py`
- Modify: `tests/unit/test_agent_execution.py`

**Step 1: Write the failing test**

Add tests for:

- low-confidence decisions are not executed
- decisions missing stop loss / take profit are not executed
- critique requiring wait produces zero plan/trade IDs

```python
async def test_brain_does_not_execute_rejected_decisions(...):
    await brain.execute(run_id)
    run = await service.get_brain_run(run_id)
    assert run["plan_ids"] == []
    assert run["trade_ids"] == []
    assert run["execution_summary"]["decision_count"] == 0
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py -k "rejected or confidence or stop_loss" -q`

Expected: FAIL because all parsed decisions still flow to execution.

**Step 3: Write minimal implementation**

Feed only `gate_result.accepted` into `_execute_decisions()`.

Persist in `thinking_process`:

- accepted count
- rejected count
- rejection reasons

Keep `execution_summary.decision_count` aligned to accepted decisions, not raw model output.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py -k "rejected or confidence or stop_loss" -q`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/agent/brain.py tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py
git commit -m "feat(agent): gate low quality decisions before execution"
```

---

### Task 4: Run Regression Suite For Agent Decision Path

**Files:**
- Review only: touched files from previous tasks

**Step 1: Run focused new tests**

Run: `python3 -m pytest tests/unit/test_agent_decision_quality.py tests/unit/test_agent_brain.py -q`

Expected: PASS

**Step 2: Run agent regression suite**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_data_hunger.py tests/unit/test_agent_execution.py tests/unit/test_agent_review_memory.py tests/unit/test_agent_phase1a.py tests/unit/test_trade_plans.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add backend/engine/agent/decision_quality.py backend/engine/agent/brain.py tests/unit/test_agent_decision_quality.py tests/unit/test_agent_brain.py tests/unit/test_agent_execution.py docs/plans/2026-03-22-agent-decision-quality-design.md docs/plans/2026-03-22-agent-decision-quality.md
git commit -m "feat(agent): improve decision quality loop"
```
