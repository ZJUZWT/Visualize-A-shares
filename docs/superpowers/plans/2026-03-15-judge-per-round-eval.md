# 评委每轮评估系统 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入评委每轮评估机制，用三维 confidence（self/inner/judge）替代单一自评 confidence，让辩论数据有实际区分度。

**Architecture:** 每轮辩论末尾新增评委小评环节（`judge_round_eval`），评委基于本轮发言+观察员+黑板数据+历史趋势，为多空双方各打三维 confidence。专家 prompt 新增 `inner_confidence` 字段要求诚实自评。最终 score 由评委 confidence 数据驱动（70%）+ LLM 主观（30%）加权。

**Tech Stack:** Python/Pydantic (backend schemas), FastAPI SSE, Next.js/Zustand (frontend state), TypeScript types

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `engine/agent/schemas.py` | Modify | 新增 `RoundEvalSide`, `RoundEval`; `Blackboard` 加 `round_evals` 字段 |
| `engine/agent/personas.py` | Modify | 新增评委小评 prompt 模板 `JUDGE_ROUND_EVAL_PROMPT`; `extract_structure` prompt 加 `inner_confidence` |
| `engine/agent/debate.py` | Modify | 新增 `judge_round_eval()` 函数; `run_debate` 每轮末尾调用; `extract_structure` 加 `inner_confidence`; 最终 score 加权计算 |
| `web/types/debate.ts` | Modify | 新增 `RoundEvalSide`, `RoundEval` 类型; `RoleState` 加三维 confidence |
| `web/stores/useDebateStore.ts` | Modify | 处理 `judge_round_eval` SSE 事件，更新 roleState |
| `web/components/debate/RoleCard.tsx` | Modify | 展示三维 confidence（公开/内心/评委） |
| `web/components/debate/TranscriptFeed.tsx` | Modify | 新增 `RoundEvalCard` 渲染评委小评 |

---

## Chunk 1: Backend Data Models + Prompts

### Task 1: Add RoundEval schemas to schemas.py

**Files:**
- Modify: `engine/agent/schemas.py:91-116` (Blackboard class area)

- [ ] **Step 1: Add RoundEvalSide and RoundEval models**

在 `Blackboard` 类之前（`JudgeVerdict` 之前），添加：

```python
class RoundEvalSide(BaseModel):
    """评委对单方的每轮评估"""
    self_confidence: float = Field(ge=0.0, le=1.0, description="专家公开宣称的 confidence")
    inner_confidence: float = Field(ge=0.0, le=1.0, description="专家内心真实 confidence")
    judge_confidence: float = Field(ge=0.0, le=1.0, description="评委客观评估的 confidence")

class RoundEval(BaseModel):
    """评委每轮小评"""
    round: int
    bull: RoundEvalSide
    bear: RoundEvalSide
    bull_reasoning: str = ""
    bear_reasoning: str = ""
    data_utilization: dict = Field(default_factory=dict)
```

- [ ] **Step 2: Add round_evals field to Blackboard**

在 `Blackboard` 类的 `data_requests` 字段之后添加：

```python
    # 评委每轮评估
    round_evals: list[RoundEval] = Field(default_factory=list)
```

- [ ] **Step 3: Add inner_confidence to DebateEntry**

在 `DebateEntry` 类的 `confidence` 字段之后添加：

```python
    inner_confidence: float | None = None  # 专家内心真实 confidence（评委小评系统用）
```

- [ ] **Step 4: Verify schemas import correctly**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/.claude/worktrees/judge-per-round-eval && cd engine && .venv/bin/python -c "from agent.schemas import RoundEval, RoundEvalSide, Blackboard; b = Blackboard(target='test', debate_id='test_001'); print('round_evals:', b.round_evals); print('OK')"`
Expected: `round_evals: []` then `OK`

- [ ] **Step 5: Commit**

```bash
git add engine/agent/schemas.py
git commit -m "feat: add RoundEval/RoundEvalSide schemas, Blackboard.round_evals, DebateEntry.inner_confidence"
```

---

### Task 2: Add judge round eval prompt to personas.py

**Files:**
- Modify: `engine/agent/personas.py:128-245` (after DEBATE_DATA_WHITELIST, before build_debate_system_prompt)

- [ ] **Step 1: Add JUDGE_ROUND_EVAL_PROMPT template**

在 `FINAL_ROUND_ALLOW_DATA_REQUESTS = False` 之后、`_DEBATER_SYSTEM_TEMPLATE` 之前添加：

```python
JUDGE_ROUND_EVAL_PROMPT = """你是本次辩论的评委，请对本轮双方表现做客观评估。

## 评估维度
对多头和空头各给出 judge_confidence（0.0-1.0）：
- 论据质量：是否有数据支撑，逻辑是否自洽
- 反驳有效性：是否有效回应了对方的质疑
- 数据引用：是否合理利用了黑板上的数据
- 观察员信息：散户情绪和主力资金信号是否支持其观点

## 注意
- judge_confidence 反映的是"该方论据的客观说服力"，不是"该方是否正确"
- 如果一方嘴硬但论据薄弱，judge_confidence 应该低于其 self_confidence
- 如果一方让步但论据扎实，judge_confidence 可以高于其 self_confidence
- 参考观察员的信息（散户情绪、主力资金动向）作为辅助判断

## 输出格式（严格 JSON，不含 markdown 代码块）
{
  "bull": {
    "self_confidence": <多头公开宣称的 confidence>,
    "inner_confidence": <多头内心真实 confidence>,
    "judge_confidence": <你对多头的客观评估>
  },
  "bear": {
    "self_confidence": <空头公开宣称的 confidence>,
    "inner_confidence": <空头内心真实 confidence>,
    "judge_confidence": <你对空头的客观评估>
  },
  "bull_reasoning": "对多头本轮表现的简评（1-2句）",
  "bear_reasoning": "对空头本轮表现的简评（1-2句）",
  "data_utilization": {
    "bull": ["多头引用的数据源"],
    "bear": ["空头引用的数据源"]
  }
}"""
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/.claude/worktrees/judge-per-round-eval && cd engine && .venv/bin/python -c "from agent.personas import JUDGE_ROUND_EVAL_PROMPT; print(len(JUDGE_ROUND_EVAL_PROMPT), 'chars'); print('OK')"`
Expected: char count and `OK`

- [ ] **Step 3: Commit**

```bash
git add engine/agent/personas.py
git commit -m "feat: add JUDGE_ROUND_EVAL_PROMPT template"
```

---

## Chunk 2: Backend Core Logic (debate.py)

### Task 3: Add inner_confidence to extract_structure

**Files:**
- Modify: `engine/agent/debate.py:73-135` (extract_structure function)

- [ ] **Step 1: Update extract_structure prompt to include inner_confidence**

在 `extract_structure` 函数的 `extract_prompt` 中，JSON 返回格式里 `"confidence"` 之后加入 `inner_confidence`：

```python
    extract_prompt = f"""请从以下辩论发言中提取结构化信息，只返回 JSON，不要其他内容。

角色: {role}
发言内容:
<speech>
{argument}
</speech>

返回格式:
{{
  "stance": "insist" | "partial_concede" | "concede",
  "confidence": 0.0-1.0,
  "inner_confidence": 0.0-1.0,
  "challenges": ["对对方的质疑1", "质疑2"],
  "data_requests": [{{"engine": "quant|data|info", "action": "动作名", "params": {{"code": "<股票代码>"}}}}],
  "retail_sentiment_score": null,
  "speak": true
}}

重要约束：
- confidence 是你的公开立场（可以嘴硬）
- inner_confidence 是你内心的真实想法——如果对方的某个论据确实让你动摇了，这里要诚实反映
- data_requests 中的 action 必须且只能从以下列表中选择：{allowed_actions_str}
- action 必须是英文字符串，严禁使用中文或自造名称，不在列表中的一律不填
- 如果发言中没有明确的数据请求，或所需 action 不在列表中，data_requests 填空数组 []
- retail_sentiment_score 仅 retail_investor 角色填写（-1.0 到 +1.0），其他角色必须为 null
- 只返回 JSON，不要任何其他文字"""
```

- [ ] **Step 2: Extract inner_confidence from parsed result**

在 `extract_structure` 的 return dict 中，`"confidence"` 之后加入：

```python
            "inner_confidence": float(parsed.get("inner_confidence", parsed.get("confidence", 0.5))),
```

同时在 fallback return 中也加入：

```python
            "inner_confidence": None,
```

- [ ] **Step 3: Verify extract_structure still imports**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/.claude/worktrees/judge-per-round-eval && cd engine && .venv/bin/python -c "from agent.debate import extract_structure; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: add inner_confidence to extract_structure prompt"
```

---

### Task 4: Implement judge_round_eval() function

**Files:**
- Modify: `engine/agent/debate.py` (add new function after `_build_context_for_role`, before `speak_stream`)

- [ ] **Step 1: Add import for RoundEval, RoundEvalSide**

在 `debate.py` 顶部 import 行：

```python
from agent.schemas import Blackboard, DebateEntry, DataRequest, JudgeVerdict, RoundEval, RoundEvalSide
```

同时 import 新 prompt：

```python
from agent.personas import (
    build_debate_system_prompt,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_ROUND_EVAL_PROMPT,
    DEBATE_DATA_WHITELIST,
    MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND,
)
```

- [ ] **Step 2: Implement judge_round_eval function**

在 `_build_context_for_role` 函数之后、`speak_stream` 之前添加：

```python
async def judge_round_eval(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> RoundEval:
    """评委每轮小评 — 基于本轮发言+观察员+黑板数据，输出三维 confidence"""
    # 收集本轮发言
    round_entries = [e for e in blackboard.transcript if e.round == blackboard.round]
    bull_entry = next((e for e in round_entries if e.role == "bull_expert"), None)
    bear_entry = next((e for e in round_entries if e.role == "bear_expert"), None)

    # 构建评估上下文
    parts = [f"## 第 {blackboard.round} 轮辩论"]

    if bull_entry:
        parts.append(f"\n### 多头专家（公开 confidence={bull_entry.confidence:.2f}）")
        parts.append(bull_entry.argument)
    if bear_entry:
        parts.append(f"\n### 空头专家（公开 confidence={bear_entry.confidence:.2f}）")
        parts.append(bear_entry.argument)

    # 观察员发言
    for e in round_entries:
        if e.role in OBSERVERS and e.speak:
            label = "散户代表" if e.role == "retail_investor" else "主力代表"
            parts.append(f"\n### {label}")
            parts.append(e.argument)

    # 已有数据
    done_reqs = [r for r in blackboard.data_requests if r.status == "done"]
    if done_reqs:
        parts.append("\n### 黑板数据")
        for r in done_reqs:
            parts.append(f"- {r.action}: {str(r.result)[:150]}")

    # 历史评估趋势
    if blackboard.round_evals:
        parts.append("\n### 历史评估趋势")
        for ev in blackboard.round_evals:
            parts.append(
                f"- Round {ev.round}: 多头 judge={ev.bull.judge_confidence:.2f} "
                f"空头 judge={ev.bear.judge_confidence:.2f}"
            )

    eval_context = "\n".join(parts)

    messages = [
        ChatMessage(role="system", content=JUDGE_ROUND_EVAL_PROMPT),
        ChatMessage(role="user", content=eval_context),
    ]

    try:
        raw = await asyncio.wait_for(llm.chat(messages), timeout=30.0)
        data = json.loads(_extract_json(raw))

        round_eval = RoundEval(
            round=blackboard.round,
            bull=RoundEvalSide(
                self_confidence=bull_entry.confidence if bull_entry else 0.5,
                inner_confidence=bull_entry.inner_confidence if bull_entry and bull_entry.inner_confidence is not None else bull_entry.confidence if bull_entry else 0.5,
                judge_confidence=float(data.get("bull", {}).get("judge_confidence", 0.5)),
            ),
            bear=RoundEvalSide(
                self_confidence=bear_entry.confidence if bear_entry else 0.5,
                inner_confidence=bear_entry.inner_confidence if bear_entry and bear_entry.inner_confidence is not None else bear_entry.confidence if bear_entry else 0.5,
                judge_confidence=float(data.get("bear", {}).get("judge_confidence", 0.5)),
            ),
            bull_reasoning=data.get("bull_reasoning", ""),
            bear_reasoning=data.get("bear_reasoning", ""),
            data_utilization=data.get("data_utilization", {}),
        )
        return round_eval
    except Exception as e:
        logger.warning(f"评委小评失败 (Round {blackboard.round}): {e}，使用默认值")
        return RoundEval(
            round=blackboard.round,
            bull=RoundEvalSide(
                self_confidence=bull_entry.confidence if bull_entry else 0.5,
                inner_confidence=bull_entry.confidence if bull_entry else 0.5,
                judge_confidence=0.5,
            ),
            bear=RoundEvalSide(
                self_confidence=bear_entry.confidence if bear_entry else 0.5,
                inner_confidence=bear_entry.confidence if bear_entry else 0.5,
                judge_confidence=0.5,
            ),
        )
```

- [ ] **Step 3: Verify function imports**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/.claude/worktrees/judge-per-round-eval && cd engine && .venv/bin/python -c "from agent.debate import judge_round_eval; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: implement judge_round_eval() function"
```

---

### Task 5: Wire judge_round_eval into run_debate loop + final score calculation

**Files:**
- Modify: `engine/agent/debate.py:697-825` (run_debate function)

- [ ] **Step 1: Add judge_round_eval call after data requests in run_debate**

在 `run_debate` 的 `# 5. 数据请求逐个事件化` 块之后、`# 6. 轮次控制` 之前，添加评委小评：

```python
        # 5.5 评委每轮小评
        round_eval = await judge_round_eval(blackboard, llm)
        blackboard.round_evals.append(round_eval)
        yield sse("judge_round_eval", round_eval.model_dump(mode="json"))
```

- [ ] **Step 2: Update final score calculation in judge_summarize_stream**

在 `judge_summarize_stream` 的 Phase 2 成功解析 verdict 之后、存储记忆之前，添加数据驱动 score 覆盖：

```python
    # Phase 3: 数据驱动 score 覆盖
    if blackboard.round_evals:
        last_eval = blackboard.round_evals[-1]
        calculated_score = last_eval.bull.judge_confidence - last_eval.bear.judge_confidence
        if verdict.score is not None:
            verdict.score = round(calculated_score * 0.7 + verdict.score * 0.3, 3)
        else:
            verdict.score = round(calculated_score, 3)
        # 根据 score 修正 signal
        if verdict.score > 0.1:
            verdict.signal = "bullish"
        elif verdict.score < -0.1:
            verdict.signal = "bearish"
        else:
            verdict.signal = "neutral"
```

- [ ] **Step 3: Add round_evals context to judge prompt**

在 `judge_summarize_stream` 的 `judge_stream_prompt` 构建中，加入评委历史评估：

```python
    # 评委历史评估
    eval_history = ""
    if blackboard.round_evals:
        eval_lines = []
        for ev in blackboard.round_evals:
            eval_lines.append(
                f"Round {ev.round}: 多头(公开={ev.bull.self_confidence:.2f}, "
                f"内心={ev.bull.inner_confidence:.2f}, 评委={ev.bull.judge_confidence:.2f}) "
                f"空头(公开={ev.bear.self_confidence:.2f}, "
                f"内心={ev.bear.inner_confidence:.2f}, 评委={ev.bear.judge_confidence:.2f})"
            )
        eval_history = "\n\n## 各轮评委评估\n" + "\n".join(eval_lines)
```

然后修改 `judge_stream_prompt`（debate.py 约 515-518 行），将 `eval_history` 拼入：

```python
    judge_stream_prompt = (
        f"你是一位专业的股票辩论裁判。请对以下辩论做出总结评价，"
        f"直接用自然语言阐述你的裁决。\n\n{context}{memory_text}{eval_history}"
    )
```

注意：`eval_history` 变量的构建代码应放在 `judge_stream_prompt` 赋值之前（在 `context = _build_context_for_role(blackboard)` 之后）。

- [ ] **Step 4: Verify run_debate still imports**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/.claude/worktrees/judge-per-round-eval && cd engine && .venv/bin/python -c "from agent.debate import run_debate; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: wire judge_round_eval into debate loop + data-driven final score"
```

---

## Chunk 3: Frontend Types, Store, and UI

### Task 6: Add frontend TypeScript types

**Files:**
- Modify: `web/types/debate.ts`

- [ ] **Step 1: Add RoundEvalSide and RoundEval types**

在 `DataRequestItem` interface 之后添加：

```typescript
export interface RoundEvalSide {
  self_confidence: number;
  inner_confidence: number;
  judge_confidence: number;
}

export interface RoundEval {
  round: number;
  bull: RoundEvalSide;
  bear: RoundEvalSide;
  bull_reasoning: string;
  bear_reasoning: string;
  data_utilization: Record<string, string[]>;
}
```

- [ ] **Step 2: Update RoleState to include three-dimensional confidence**

修改 `RoleState` interface：

```typescript
export interface RoleState {
  stance: Stance | null;
  confidence: number;
  conceded: boolean;
  inner_confidence?: number;
  judge_confidence?: number;
}
```

- [ ] **Step 3: Update DebateEntry to include inner_confidence**

在 `DebateEntry` interface 的 `confidence` 之后添加：

```typescript
  inner_confidence: number | null;
```

- [ ] **Step 4: Commit**

```bash
git add web/types/debate.ts
git commit -m "feat: add RoundEval types and three-dimensional confidence to RoleState"
```

---

### Task 7: Handle judge_round_eval SSE event in useDebateStore

**Files:**
- Modify: `web/stores/useDebateStore.ts`

- [ ] **Step 1: Add RoundEval import**

更新 import：

```typescript
import type {
  DebateEntry, JudgeVerdict, DebateStatus,
  ObserverState, RoleState, DebateReplayRecord, RoundEval,
} from "@/types/debate";
```

- [ ] **Step 2: Add roundEvals to store state**

在 `DebateStore` interface 中 `judgeVerdict` 之后添加：

```typescript
  roundEvals: RoundEval[];
```

在 initial state 中添加：

```typescript
  roundEvals: [],
```

在 `reset()` 中添加：

```typescript
    roundEvals: [],
```

- [ ] **Step 3: Add TranscriptItem variant for round_eval**

在 `TranscriptItem` union 中添加新变体：

```typescript
  | { id: string; type: "round_eval"; data: RoundEval }
```

- [ ] **Step 4: Handle judge_round_eval event in _handleSSEEvent**

在 `_handleSSEEvent` 的 `case "judge_verdict"` 之前添加：

```typescript
    case "judge_round_eval": {
      const roundEval = data as unknown as RoundEval;
      const newRoundEvals = [...state.roundEvals, roundEval];

      // 用评委 confidence 更新 roleState
      const newRoleState = { ...state.roleState };
      if (newRoleState["bull_expert"]) {
        newRoleState["bull_expert"] = {
          ...newRoleState["bull_expert"],
          judge_confidence: roundEval.bull.judge_confidence,
          inner_confidence: roundEval.bull.inner_confidence,
        };
      }
      if (newRoleState["bear_expert"]) {
        newRoleState["bear_expert"] = {
          ...newRoleState["bear_expert"],
          judge_confidence: roundEval.bear.judge_confidence,
          inner_confidence: roundEval.bear.inner_confidence,
        };
      }

      set({
        roundEvals: newRoundEvals,
        roleState: newRoleState,
        transcript: [
          ...state.transcript,
          { id: `round_eval_${roundEval.round}`, type: "round_eval", data: roundEval },
        ],
      });
      break;
    }
```

- [ ] **Step 5: Handle roundEvals in loadReplay**

在 `loadReplay` 函数中（约 133-181 行），`set({...})` 调用之前，从 blackboard JSON 中提取 round_evals：

```typescript
      const roundEvals: RoundEval[] = blackboard.round_evals ?? [];

      // 用最后一轮评委评估更新 roleState
      const lastEval = roundEvals.length > 0 ? roundEvals[roundEvals.length - 1] : null;
      for (const entry of (blackboard.transcript ?? []) as DebateEntry[]) {
        if (DEBATERS.includes(entry.role)) {
          roleState[entry.role] = {
            stance: entry.stance,
            confidence: entry.confidence,
            conceded: entry.stance === "concede",
            ...(lastEval && entry.role === "bull_expert" ? {
              inner_confidence: lastEval.bull.inner_confidence,
              judge_confidence: lastEval.bull.judge_confidence,
            } : {}),
            ...(lastEval && entry.role === "bear_expert" ? {
              inner_confidence: lastEval.bear.inner_confidence,
              judge_confidence: lastEval.bear.judge_confidence,
            } : {}),
          };
        }
      }
```

然后在 `set({...})` 中加入 `roundEvals`：

```typescript
      set({
        transcript,
        roleState,
        roundEvals,
        judgeVerdict: verdict,
        status: "completed",
        currentRound: record.rounds_completed,
      });
```

- [ ] **Step 6: Commit**

```bash
git add web/stores/useDebateStore.ts
git commit -m "feat: handle judge_round_eval SSE event in store + replay support"
```

---

### Task 8: Update RoleCard to show three-dimensional confidence

**Files:**
- Modify: `web/components/debate/RoleCard.tsx`

- [ ] **Step 1: Replace single confidence bar with three-dimensional display**

替换 RoleCard.tsx 第 51-65 行的置信度区域（从 `{/* 置信度 */}` 到对应的闭合 `)}` ），改为三维展示：

```tsx
      {/* 三维置信度 */}
      {state && (
        <div className="w-full space-y-2.5">
          {/* 主显示：评委置信度（如果有） */}
          <div className="flex justify-between text-sm text-[var(--text-tertiary)]">
            <span>置信度</span>
            <span className="font-medium" style={{ color }}>
              {Math.round((state.judge_confidence ?? state.confidence) * 100)}%
            </span>
          </div>
          <div className="w-full h-2 rounded-full bg-[var(--bg-primary)]">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${(state.judge_confidence ?? state.confidence) * 100}%`,
                backgroundColor: color,
              }}
            />
          </div>

          {/* 三维对比（仅在有评委评估后显示） */}
          {state.judge_confidence !== undefined && (
            <div className="space-y-1.5 pt-1">
              <ConfidenceRow label="公开" value={state.confidence} color={color} />
              {state.inner_confidence !== undefined && (
                <ConfidenceRow label="内心" value={state.inner_confidence} color={color} opacity={0.6} />
              )}
              <ConfidenceRow label="评委" value={state.judge_confidence} color={color} opacity={0.85} />
            </div>
          )}
        </div>
      )}
```

- [ ] **Step 2: Add ConfidenceRow helper component**

在 RoleCard 文件底部添加：

```tsx
function ConfidenceRow({
  label, value, color, opacity = 1,
}: {
  label: string; value: number; color: string; opacity?: number;
}) {
  return (
    <div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
      <span className="w-6 shrink-0">{label}</span>
      <div className="flex-1 h-1 rounded-full bg-[var(--bg-primary)]">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${value * 100}%`, backgroundColor: color, opacity }}
        />
      </div>
      <span className="w-8 text-right" style={{ color, opacity }}>{Math.round(value * 100)}%</span>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/components/debate/RoleCard.tsx
git commit -m "feat: display three-dimensional confidence in RoleCard"
```

---

### Task 9: Add RoundEvalCard to TranscriptFeed

**Files:**
- Modify: `web/components/debate/TranscriptFeed.tsx`

- [ ] **Step 1: Add round_eval rendering in transcript map**

在 `TranscriptFeed` 的 `transcript.map` 中，`data_request` case 之后添加：

```tsx
        if (item.type === "round_eval") {
          return <RoundEvalCard key={item.id} data={item.data} />;
        }
```

- [ ] **Step 2: Implement RoundEvalCard component**

在 `TranscriptFeed.tsx` 文件底部（`VerdictCard` 之前）添加：

```tsx
function RoundEvalCard({ data }: { data: import("@/types/debate").RoundEval }) {
  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[90%] rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] text-xs overflow-hidden">
        <div className="px-4 py-2.5 flex items-center gap-2 text-[var(--text-tertiary)] border-b border-[var(--border)]">
          <span>⚖️</span>
          <span className="font-medium">评委小评 · 第 {data.round} 轮</span>
        </div>
        <div className="grid grid-cols-2 gap-3 p-4">
          {/* 多头 */}
          <div className="space-y-1.5">
            <div className="font-medium text-red-400">多头</div>
            <ConfidenceTriplet side={data.bull} color="#EF4444" />
            {data.bull_reasoning && (
              <p className="text-[var(--text-secondary)] leading-relaxed mt-1">{data.bull_reasoning}</p>
            )}
          </div>
          {/* 空头 */}
          <div className="space-y-1.5">
            <div className="font-medium text-emerald-400">空头</div>
            <ConfidenceTriplet side={data.bear} color="#10B981" />
            {data.bear_reasoning && (
              <p className="text-[var(--text-secondary)] leading-relaxed mt-1">{data.bear_reasoning}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ConfidenceTriplet({ side, color }: { side: import("@/types/debate").RoundEvalSide; color: string }) {
  const rows = [
    { label: "公开", value: side.self_confidence },
    { label: "内心", value: side.inner_confidence },
    { label: "评委", value: side.judge_confidence },
  ];
  return (
    <div className="space-y-1">
      {rows.map(({ label, value }) => (
        <div key={label} className="flex items-center gap-1.5">
          <span className="w-5 text-[var(--text-tertiary)]">{label}</span>
          <div className="flex-1 h-1 rounded-full bg-[var(--bg-secondary)]">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${value * 100}%`, backgroundColor: color }}
            />
          </div>
          <span className="w-7 text-right" style={{ color }}>{Math.round(value * 100)}%</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add web/components/debate/TranscriptFeed.tsx
git commit -m "feat: add RoundEvalCard to TranscriptFeed"
```

---

### Task 10: Smoke test — run a 1-round debate and verify

- [ ] **Step 1: Start backend**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/.claude/worktrees/judge-per-round-eval && cd engine && .venv/bin/python main.py` (background)

- [ ] **Step 2: Run a 1-round debate via API**

```bash
curl -N -X POST http://localhost:8000/api/v1/debate \
  -H "Content-Type: application/json" \
  -d '{"code": "600519", "max_rounds": 1}' 2>&1 | head -100
```

Verify:
- SSE stream contains `judge_round_eval` event after round 1 entries
- `judge_round_eval` data has `bull.judge_confidence`, `bear.judge_confidence` etc.
- `judge_verdict` event has data-driven `score` (not purely LLM)

- [ ] **Step 3: Final commit with all files**

```bash
git add -A
git commit -m "feat: judge per-round evaluation system — three-dimensional confidence"
```
