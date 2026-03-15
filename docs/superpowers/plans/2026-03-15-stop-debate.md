# 终止辩论 + 可选总结 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许用户在辩论进行中随时终止，并可选择让 AI 对已有内容生成总结。

**Architecture:** 前端通过 AbortController 中断 SSE fetch 连接，store 新增 `"stopped"` 状态和 `currentTarget` 字段；终止后弹窗询问是否总结，总结调用后端新增的独立 `/debate/summarize` 端点。

**Tech Stack:** Next.js 15, Zustand, FastAPI, SSE, Anthropic LLM

---

## Chunk 1: 类型 + 后端 summarize 端点

### Task 1: 新增 DebateStatus "stopped" 和 PartialSummary 类型

**Files:**
- Modify: `web/types/debate.ts`

- [ ] **Step 1: 修改 DebateStatus 类型**

```ts
// web/types/debate.ts
export type DebateStatus = "idle" | "debating" | "final_round" | "judging" | "completed" | "stopped";
```

- [ ] **Step 2: 新增 PartialSummary 类型**

```ts
export interface PartialSummary {
  summary: string;
  signal: DebateSignal | null;
}
```

- [ ] **Step 3: Commit**

```bash
git add web/types/debate.ts
git commit -m "feat: add stopped status and PartialSummary type"
```

---

### Task 2: 后端新增 POST /api/v1/debate/summarize 端点

**Files:**
- Modify: `engine/api/routes/debate.py`

- [ ] **Step 1: 新增 SummarizeRequest 模型和端点**

在 `engine/api/routes/debate.py` 末尾添加：

```python
class SummarizeRequest(BaseModel):
    target: str = Field(description="股票代码")
    transcript: list[dict] = Field(description="已有辩论记录，DebateEntry 列表")


@router.post("/debate/summarize")
async def summarize_debate(req: SummarizeRequest):
    """对中途终止的辩论生成简短总结"""
    from llm.config import llm_settings
    if not llm_settings.api_key:
        raise HTTPException(status_code=503, detail="LLM 未配置")

    if not req.transcript:
        raise HTTPException(status_code=400, detail="transcript 为空，无法总结")

    try:
        from agent import get_orchestrator
        orch = get_orchestrator()
        llm = orch._llm._provider

        # 构建 transcript 文本
        lines = []
        for entry in req.transcript:
            role = "多头" if entry.get("role") == "bull_expert" else "空头"
            lines.append(f"[{role} 第{entry.get('round', '?')}轮] {entry.get('argument', '')}")
        transcript_text = "\n\n".join(lines)

        prompt = f"""以下是关于股票 {req.target} 的多空辩论记录（辩论被用户中途终止）：

{transcript_text}

请基于已有内容，给出：
1. 一段简短总结（100字以内），概括双方核心分歧
2. 当前倾向：bullish（看多）/ bearish（看空）/ neutral（中性）

以 JSON 格式返回：{{"summary": "...", "signal": "bullish|bearish|neutral"}}"""

        response = await llm.chat([{"role": "user", "content": prompt}])
        import json as _json
        # 提取 JSON
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = _json.loads(text.strip())
        return {
            "summary": result.get("summary", ""),
            "signal": result.get("signal") if result.get("signal") in ("bullish", "bearish", "neutral") else None,
        }
    except Exception as e:
        logger.error(f"生成总结失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成总结失败: {str(e)}")
```

- [ ] **Step 2: 手动测试端点（后端需已启动）**

```bash
curl -X POST http://localhost:8000/api/v1/debate/summarize \
  -H "Content-Type: application/json" \
  -d '{"target":"600519","transcript":[{"role":"bull_expert","round":1,"argument":"贵州茅台品牌护城河深厚"},{"role":"bear_expert","round":1,"argument":"估值过高，PE超50倍"}]}'
```

Expected: `{"summary": "...", "signal": "bearish|bullish|neutral"}`

- [ ] **Step 3: Commit**

```bash
git add engine/api/routes/debate.py
git commit -m "feat: add POST /debate/summarize endpoint"
```

---

## Chunk 2: 前端 Store 改动

### Task 3: useDebateStore 新增 stopDebate + AbortController + currentTarget

**Files:**
- Modify: `web/stores/useDebateStore.ts`

- [ ] **Step 1: 更新 DebateStore interface**

在 `interface DebateStore` 中新增：

```ts
currentTarget: string | null;
_abortController: AbortController | null;
stopDebate: () => void;
```

- [ ] **Step 2: 更新初始状态**

在 `create<DebateStore>` 的初始值中新增：

```ts
currentTarget: null,
_abortController: null,
```

- [ ] **Step 3: 更新 reset()**

```ts
reset: () => set({
  status: "idle",
  transcript: [],
  observerState: {},
  roleState: {},
  currentRound: 0,
  judgeVerdict: null,
  isReplayMode: false,
  error: null,
  _observerSpokenThisRound: {},
  currentTarget: null,
  _abortController: null,
}),
```

- [ ] **Step 4: 新增 stopDebate()**

```ts
stopDebate: () => {
  get()._abortController?.abort();
  set({ status: "stopped" });
},
```

- [ ] **Step 5: 更新 startDebate()**

完整替换 `startDebate` 方法（保留原有 SSE 读取逻辑，只改开头和 catch）：

```ts
startDebate: async (code, maxRounds) => {
  get().reset();
  const controller = new AbortController();
  set({ status: "debating", currentTarget: code, _abortController: controller });

  try {
    const res = await fetch(`${API_BASE}/api/v1/debate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, max_rounds: maxRounds }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      set({ error: err.detail ?? "请求失败", status: "idle" });
      return;
    }

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";

      for (const chunk of chunks) {
        const lines = chunk.split("\n");
        let eventType = "";
        let dataStr = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) eventType = line.slice(7).trim();
          if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
        }
        if (!eventType || !dataStr) continue;

        try {
          const data = JSON.parse(dataStr);
          _handleSSEEvent(eventType, data, set, get);
        } catch {
          // 忽略解析失败的事件
        }
      }
    }
  } catch (e: unknown) {
    // AbortError 是用户主动终止，不是错误
    if (e instanceof DOMException && e.name === "AbortError") return;
    const msg = e instanceof Error ? e.message : "连接失败";
    set({ error: msg, status: "idle" });
  }
},
```

- [ ] **Step 6: 更新 _handleSSEEvent 入口**

在 `_handleSSEEvent` 函数的 `switch` 语句之前加守卫：

```ts
function _handleSSEEvent(...) {
  const state = get();
  if (state.status === "stopped") return; // abort 传播窗口内忽略所有事件
  switch (eventType) {
    // ...
  }
}
```

- [ ] **Step 7: Commit**

```bash
git add web/stores/useDebateStore.ts
git commit -m "feat: add stopDebate, AbortController, currentTarget to debate store"
```

---

## Chunk 3: 前端 UI 改动

### Task 4: InputBar 新增终止按钮

**Files:**
- Modify: `web/components/debate/InputBar.tsx`

- [ ] **Step 1: 新增 onStop prop**

```ts
interface InputBarProps {
  status: DebateStatus;
  isReplayMode: boolean;
  onStart: (code: string, maxRounds: number) => void;
  onHistoryOpen: () => void;
  onStop: () => void;
}
```

- [ ] **Step 2: 将辩论中的按钮替换为终止按钮**

```tsx
const [stopping, setStopping] = useState(false);
const busy = status === "debating" || status === "final_round" || status === "judging";

// 开始/终止按钮
{busy ? (
  <button
    onClick={() => { setStopping(true); onStop(); }}
    disabled={stopping}
    className="h-10 px-5 rounded-lg text-sm font-medium bg-red-500 text-white
               hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
               flex items-center gap-2 transition-opacity shrink-0"
  >
    {stopping ? <><Loader2 size={14} className="animate-spin" />终止中...</> : "终止辩论"}
  </button>
) : (
  <button
    onClick={() => { setStopping(false); code && onStart(code, maxRounds); }}
    disabled={!code}
    className="h-10 px-5 rounded-lg text-sm font-medium bg-[var(--accent)] text-white
               hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
               flex items-center gap-2 transition-opacity shrink-0"
  >
    开始辩论
  </button>
)}
```

注意：`Loader2` 需要从 `lucide-react` 引入，`useState` 需要从 `react` 引入（已有）。

- [ ] **Step 3: Commit**

```bash
git add web/components/debate/InputBar.tsx
git commit -m "feat: add stop button to InputBar"
```

---

### Task 5: 新建 SummaryCard 组件

**Files:**
- Create: `web/components/debate/SummaryCard.tsx`

- [ ] **Step 1: 创建 SummaryCard**

```tsx
"use client";

import type { PartialSummary } from "@/types/debate";

const SIGNAL_COLOR = { bullish: "#EF4444", bearish: "#10B981", neutral: "#9CA3AF" };
const SIGNAL_LABEL = { bullish: "看多", bearish: "看空", neutral: "中性" };

export default function SummaryCard({ summary }: { summary: PartialSummary }) {
  const color = summary.signal ? SIGNAL_COLOR[summary.signal] : "#9CA3AF";
  const label = summary.signal ? SIGNAL_LABEL[summary.signal] : "中性";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden mt-4">
      <div className="h-1.5" style={{ backgroundColor: color }} />
      <div className="px-5 py-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold" style={{ color }}>{label}</span>
          <span className="text-xs text-[var(--text-tertiary)] px-2 py-0.5 rounded-full bg-[var(--bg-primary)]">
            中途终止总结
          </span>
        </div>
        <p className="text-sm text-[var(--text-primary)] leading-relaxed">{summary.summary}</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/debate/SummaryCard.tsx
git commit -m "feat: add SummaryCard component"
```

---

### Task 6: 新建 StopConfirmModal 组件

**Files:**
- Create: `web/components/debate/StopConfirmModal.tsx`

- [ ] **Step 1: 创建 StopConfirmModal**

总结成功后调用 `onSummaryReady` 把结果传给父组件（DebatePage），由 DebatePage 存入 store 并在 TranscriptFeed 末尾显示。

```tsx
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { TranscriptItem } from "@/stores/useDebateStore";
import type { PartialSummary } from "@/types/debate";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

interface StopConfirmModalProps {
  transcript: TranscriptItem[];
  target: string;
  onReset: () => void;
  onSummaryReady: (summary: PartialSummary) => void;
}

export default function StopConfirmModal({ transcript, target, onReset, onSummaryReady }: StopConfirmModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSummarize = async () => {
    setLoading(true);
    setError(null);
    try {
      const entries = transcript
        .filter(i => i.type === "entry")
        .map(i => (i as Extract<TranscriptItem, { type: "entry" }>).data);

      const res = await fetch(`${API_BASE}/api/v1/debate/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, transcript: entries }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "请求失败");
      }
      const data: PartialSummary = await res.json();
      onSummaryReady(data);  // 传给父组件，由父组件存入 store
      onReset();             // 关闭弹窗，重置状态
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "生成总结失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
         onClick={onReset}>
      <div className="bg-[var(--bg-secondary)] rounded-2xl border border-[var(--border)]
                      shadow-xl w-full max-w-sm mx-4 p-6 space-y-4"
           onClick={e => e.stopPropagation()}>
        <div className="text-base font-semibold text-[var(--text-primary)]">辩论已终止</div>
        <p className="text-sm text-[var(--text-secondary)]">
          是否需要 AI 对已有辩论内容生成总结？
        </p>

        {error && (
          <p className="text-sm text-red-500">{error}</p>
        )}

        <div className="flex gap-3">
          <button
            onClick={handleSummarize}
            disabled={loading}
            className="flex-1 h-10 rounded-xl text-sm font-medium bg-[var(--accent)] text-white
                       hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <><Loader2 size={14} className="animate-spin" />生成中...</> : "生成总结"}
          </button>
          <button
            onClick={onReset}
            className="flex-1 h-10 rounded-xl text-sm font-medium border border-[var(--border)]
                       text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] transition-colors"
          >
            直接退出
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/debate/StopConfirmModal.tsx
git commit -m "feat: add StopConfirmModal component"
```

---

### Task 7: DebatePage 挂载 StopConfirmModal，传 onStop 给 InputBar，存储 summary

**Files:**
- Modify: `web/components/debate/DebatePage.tsx`

- [ ] **Step 1: 引入新组件，新增 summary state**

```tsx
import StopConfirmModal from "./StopConfirmModal";
import SummaryCard from "./SummaryCard";
import type { PartialSummary } from "@/types/debate";

// 在组件内新增
const [partialSummary, setPartialSummary] = useState<PartialSummary | null>(null);
```

- [ ] **Step 2: 从 store 取 stopDebate 和 currentTarget**

```tsx
const {
  status, transcript, observerState, roleState,
  judgeVerdict, isReplayMode, error,
  startDebate, loadReplay, reset, stopDebate, currentTarget,
} = useDebateStore();
```

- [ ] **Step 3: reset 时清除 partialSummary**

```tsx
const handleReset = () => {
  setPartialSummary(null);
  reset();
};
```

- [ ] **Step 4: 传 onStop 给 InputBar**

```tsx
<InputBar
  status={status}
  isReplayMode={isReplayMode}
  onStart={startDebate}
  onHistoryOpen={() => setShowHistory(true)}
  onStop={stopDebate}
/>
```

- [ ] **Step 5: 在 BullBearArena 下方渲染 SummaryCard（如有）**

`BullBearArena` 的 `TranscriptFeed` 已经在末尾渲染 `verdict`，`partialSummary` 需要在 TranscriptFeed 外单独渲染，放在 BullBearArena 和 InputBar 之间：

```tsx
{partialSummary && (
  <div className="px-4">
    <SummaryCard summary={partialSummary} />
  </div>
)}
```

- [ ] **Step 6: 挂载 StopConfirmModal**

```tsx
{status === "stopped" && currentTarget && (
  <StopConfirmModal
    transcript={transcript}
    target={currentTarget}
    onReset={handleReset}
    onSummaryReady={(s) => { setPartialSummary(s); }}
  />
)}
```

- [ ] **Step 7: Commit**

```bash
git add web/components/debate/DebatePage.tsx
git commit -m "feat: wire up StopConfirmModal, SummaryCard and stopDebate in DebatePage"
```

---

## Chunk 4: 收尾

### Task 8: 端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd engine && .venv/bin/python main.py
```

- [ ] **Step 2: 启动前端**

```bash
cd web && npm run dev
```

- [ ] **Step 3: 验证终止流程**

1. 访问 http://localhost:3000/debate
2. 输入股票代码，开始辩论
3. 辩论进行中点击"终止辩论"按钮
4. 确认弹窗出现
5. 点击"生成总结"，确认总结卡片显示
6. 再次测试，点击"直接退出"，确认页面重置

- [ ] **Step 4: 最终 commit + push**

```bash
git add -A
git commit -m "feat: 终止辩论 + 可选总结功能完成"
git push origin feat/stop-debate
```
