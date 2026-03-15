# 辩论黑板面板 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在辩论页右侧新增黑板面板，实时展示专家搜索到的原始数据；重构辩论流程使专家在每轮发言前先完成数据搜索。

**Architecture:** 后端在 `run_debate()` 中新增 `fetch_initial_data`（公用数据）和 `request_data_for_round`（每轮专家数据请求），通过新 SSE 事件 `blackboard_update` / `initial_data_complete` 推送到前端。前端新增 `BlackboardPanel` 组件和 `blackboardItems` store 字段，布局扩展为四列。

**Tech Stack:** Python asyncio, FastAPI SSE, Next.js 15, Zustand, Tailwind CSS v4, lucide-react

---

## 文件结构

**修改：**
- `engine/agent/debate.py` — 新增 `fetch_initial_data`, `request_data_for_round`；重构 `run_debate()`；清理 `speak_stream()` 数据请求逻辑
- `engine/agent/personas.py` — 去掉 `_DEBATER_SYSTEM_TEMPLATE` 中的【数据请求】格式说明；新增 `DATA_REQUEST_SYSTEM_PROMPT` 模板
- `web/stores/useDebateStore.ts` — 新增 `BlackboardItem` 类型、`blackboardItems` state、`blackboard_update` / `initial_data_complete` 事件处理

**新增：**
- `web/components/debate/BlackboardPanel.tsx` — 黑板面板组件

**修改（轻量）：**
- `web/components/debate/BullBearArena.tsx` — 新增第四列
- `web/components/debate/DebatePage.tsx` — 传递 `blackboardItems`

---

## Chunk 1: 后端 — 新增函数与流程重构

### Task 1: `fetch_initial_data` 函数

**Files:**
- Modify: `engine/agent/debate.py`

- [ ] **Step 1: 在 `debate.py` 的 `fulfill_data_requests` 函数之后添加 `fetch_initial_data`**

```python
async def fetch_initial_data(
    blackboard: Blackboard,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """拉取公用初始数据，推送 blackboard_update 事件"""
    INITIAL_ACTIONS = [
        ("get_stock_info",    "data", "股票基本信息"),
        ("get_daily_history", "data", "日线行情"),
        ("get_news",          "info", "最新新闻"),
    ]
    success = 0
    failed = 0
    for action, engine, title in INITIAL_ACTIONS:
        req_id = f"public_{action}"
        yield sse("blackboard_update", {
            "request_id": req_id, "source": "public",
            "engine": engine, "action": action, "title": title,
            "status": "pending", "result_summary": "", "round": 0,
        })
        req = DataRequest(
            requested_by="public", engine=engine,
            action=action, params={"code": blackboard.target}, round=0,
        )
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                data_fetcher.fetch_by_request(req), timeout=15.0
            )
            summary = str(result)[:300] if result else ""
            blackboard.facts[action] = result
            success += 1
            yield sse("blackboard_update", {
                "request_id": req_id, "source": "public",
                "engine": engine, "action": action, "title": title,
                "status": "done", "result_summary": summary, "round": 0,
            })
        except Exception as e:
            logger.warning(f"公用数据拉取失败 [{action}]: {e}")
            failed += 1
            yield sse("blackboard_update", {
                "request_id": req_id, "source": "public",
                "engine": engine, "action": action, "title": title,
                "status": "failed", "result_summary": str(e)[:200], "round": 0,
            })
    yield sse("initial_data_complete", {
        "total": len(INITIAL_ACTIONS), "success": success, "failed": failed,
    })
```

- [ ] **Step 2: 确认 `time` 已在文件顶部 import（已有），`DataRequest` 已 import（已有）**

- [ ] **Step 3: 手动测试（后端启动后用 curl 触发辩论，观察 SSE 流中是否出现 `blackboard_update` 事件）**

- [ ] **Step 4: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: 新增 fetch_initial_data，推送公用黑板数据"
```

---

### Task 2: `request_data_for_round` 函数

**Files:**
- Modify: `engine/agent/debate.py`
- Modify: `engine/agent/personas.py`

- [ ] **Step 1: 在 `personas.py` 中新增数据请求专用 prompt 模板**

在文件末尾 `build_debate_system_prompt` 函数之后添加（注意：`build_data_request_prompt` 直接引用模块内的变量，不需要 import 自身）：

```python
_DATA_REQUEST_TEMPLATE = """你是{role_desc}，正在参与关于 {target} 的专家辩论（第 {round} 轮）。

## 当前辩论状态
{context}

## 你的任务
在发言之前，你需要决定本轮需要哪些数据来支撑你的论点。
只输出 JSON 数组，不要任何其他内容。如果不需要数据，输出空数组 []。

## 可用数据动作
{allowed_actions}

## 输出格式（严格 JSON 数组）
[
  {{"engine": "data", "action": "get_daily_history", "params": {{"code": "{target}"}}}},
  {{"engine": "info", "action": "get_news", "params": {{"code": "{target}"}}}}
]

注意：params 中 code 字段必须填写股票代码 {target}。最多请求 {max_requests} 条。"""


def build_data_request_prompt(role: str, target: str, round: int, context: str) -> str:
    """构建数据请求专用 prompt"""
    allowed = DEBATE_DATA_WHITELIST.get(role, [])
    allowed_str = "\n".join(f"- {a}" for a in allowed)
    persona = DEBATE_PERSONAS.get(role, {})
    role_desc = persona.get("role", role)
    return _DATA_REQUEST_TEMPLATE.format(
        role_desc=role_desc, target=target, round=round,
        context=context, allowed_actions=allowed_str,
        max_requests=MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND,
    )
```

- [ ] **Step 2: 在 `debate.py` 中新增 `request_data_for_round` 函数（在 `fetch_initial_data` 之后）**

注意：`ChatMessage` 和 `BaseLLMProvider` 已在 `debate.py` 顶部通过 `from llm.providers import BaseLLMProvider, ChatMessage` 导入，无需重复。

```python
async def request_data_for_round(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """专家本轮数据请求：LLM 决策 → fetch → 推送 blackboard_update"""
    from agent.personas import build_data_request_prompt
    context = _build_context_for_role(blackboard)
    prompt = build_data_request_prompt(role, blackboard.target, blackboard.round, context)

    try:
        raw = await asyncio.wait_for(
            llm.chat([ChatMessage(role="user", content=prompt)]),
            timeout=15.0,
        )
        parsed = json.loads(_extract_json(raw))
        if not isinstance(parsed, list):
            parsed = []
    except Exception as e:
        logger.warning(f"[{role}] 数据请求 LLM 调用失败: {e}，跳过")
        return

    requests = [
        DataRequest(
            requested_by=role, engine=dr.get("engine", "data"),
            action=dr.get("action", ""), params=dr.get("params", {}),
            round=blackboard.round,
        )
        for dr in parsed if dr.get("action")
    ]
    requests = validate_data_requests(role, requests)

    ACTION_TITLE_MAP = {
        "get_stock_info": "股票基本信息", "get_daily_history": "日线行情",
        "get_news": "最新新闻", "get_announcements": "公告",
        "get_factor_scores": "因子评分", "get_technical_indicators": "技术指标",
        "get_money_flow": "资金流向", "get_northbound_holding": "北向持仓",
        "get_margin_balance": "融资融券", "get_turnover_rate": "换手率",
        "get_cluster_for_stock": "聚类分析", "get_financials": "财务数据",
        "get_restrict_stock_unlock": "限售解禁", "get_signal_history": "信号历史",
    }

    for req in requests:
        req_id = f"{role}_{req.action}_{blackboard.round}"
        title = ACTION_TITLE_MAP.get(req.action, req.action)
        yield sse("blackboard_update", {
            "request_id": req_id, "source": role,
            "engine": req.engine, "action": req.action, "title": title,
            "status": "pending", "result_summary": "", "round": blackboard.round,
        })
        try:
            result = await asyncio.wait_for(
                data_fetcher.fetch_by_request(req), timeout=15.0
            )
            req.result = result
            req.status = "done"
            blackboard.data_requests.append(req)
            yield sse("blackboard_update", {
                "request_id": req_id, "source": role,
                "engine": req.engine, "action": req.action, "title": title,
                "status": "done", "result_summary": str(result)[:300] if result else "",
                "round": blackboard.round,
            })
        except Exception as e:
            logger.warning(f"[{role}] 数据请求失败 [{req.action}]: {e}")
            req.status = "failed"
            yield sse("blackboard_update", {
                "request_id": req_id, "source": role,
                "engine": req.engine, "action": req.action, "title": title,
                "status": "failed", "result_summary": str(e)[:200],
                "round": blackboard.round,
            })
```

- [ ] **Step 3: Commit**

```bash
git add engine/agent/debate.py engine/agent/personas.py
git commit -m "feat: 新增 request_data_for_round，专家每轮发言前独立搜索数据"
```

---

### Task 3: 重构 `run_debate()` 主循环

**Files:**
- Modify: `engine/agent/debate.py`

- [ ] **Step 1: 在 `run_debate()` 的 `yield sse("debate_start", ...)` 之后、`while` 循环之前，插入公用数据拉取**

找到注释 `# ── 主循环` 下方的 `yield sse("debate_start", {...})` 块，在其后、`while blackboard.round < blackboard.max_rounds:` 之前插入：

```python
    # 公用初始数据
    async for event in fetch_initial_data(blackboard, data_fetcher):
        yield event
```

- [ ] **Step 2: 在每轮循环中，`yield sse("debate_round_start", ...)` 之后插入专家数据请求**

找到注释 `# 1. 多头发言（流式）` 之前，在 `yield sse("debate_round_start", {...})` 之后插入：

```python
        # 1. 专家数据请求（发言前，最终轮跳过）
        if not is_final:
            async for event in request_data_for_round("bull_expert", blackboard, llm, data_fetcher):
                yield event
            async for event in request_data_for_round("bear_expert", blackboard, llm, data_fetcher):
                yield event
```

然后将原来的注释 `# 1. 多头发言（流式）` 改为 `# 2. 多头发言（流式）`，`# 2. 空头发言（流式）` 改为 `# 3. 空头发言（流式）`，`# 3. 观察员` 改为 `# 4. 观察员`，`# 4. concede 检查` 改为 `# 5. concede 检查`。

完整的多头发言调用（保持原有参数不变）：
```python
        async for event in speak_stream("bull_expert", blackboard, llm, memory, is_final):
            yield event
            if event["event"] == "debate_entry_complete":
                last_bull = event["data"]
```

- [ ] **Step 3: 删除旧的"数据请求逐个事件化"代码块**

找到注释 `# 5. 数据请求逐个事件化`（当前编号，删除后编号会变），删除从该注释到 `yield sse("data_batch_complete", {...})` 的整段代码（含 `data_batch_complete` yield）。

- [ ] **Step 4: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: run_debate 重构，公用数据+专家数据请求前置"
```

---

### Task 4: 清理 `speak_stream()` 和 `personas.py`

**Files:**
- Modify: `engine/agent/debate.py`
- Modify: `engine/agent/personas.py`

- [ ] **Step 1: 在 `personas.py` 的 `_DEBATER_SYSTEM_TEMPLATE` 中删除【数据请求】相关行**

找到并删除以下两行：
```
- 如果需要更多数据支撑论点，可通过 data_requests 请求（最后一轮除外）
```
和：
```
4. 如需补充数据，用"【数据请求】"标记（每条一行，格式：引擎.动作(参数)）
```

同时将第 4 点之后的编号调整（如果有第 5 点，改为第 4 点）。

- [ ] **Step 2: 在 `debate.py` 的 `_parse_debate_entry` 中删除【数据请求】块解析**

找到注释 `# 提取【数据请求】块`，删除从该注释到 `text = text[:data_req_match.start()].strip()` 的整段代码（含 `data_requests: list[DataRequest] = []` 初始化行和 `data_req_match` 代码块）。

同时删除函数签名中 `data_requests` 变量的初始化，以及 `DebateEntry(...)` 构造中的 `data_requests=data_requests` 参数（改为不传，使用默认空列表）。

注意：此步骤必须在 Step 4/5 之前完成，因为 `speak_stream()` 和 `speak()` 中的 `validate_data_requests` 调用依赖 `entry.data_requests`，Step 2 完成后该字段始终为空列表，Step 4/5 的清理才是安全的 no-op 删除。

- [ ] **Step 3: 在 `debate.py` 的 `extract_structure` 函数中删除 `data_requests` 相关内容**

找到 `extract_prompt` 字符串中的 `"data_requests"` 字段说明行，删除它。

找到 `allowed_actions` / `allowed_actions_str` 相关的两行局部变量（仅用于 data_requests 约束），删除它们。

在返回 dict 中，将 `"data_requests": [DataRequest(...) for ...]` 替换为 `"data_requests": []`。

- [ ] **Step 4: 在 `speak_stream()` 中删除数据请求处理**

找到 `speak_stream` 函数末尾（`entry = DebateEntry(...)` 之后）的这两行，删除：
```python
        validated = validate_data_requests(role, entry.data_requests)
        blackboard.data_requests.extend(validated)
```

- [ ] **Step 5: 在 `speak()` 函数中删除相同的两行**

找到 `speak` 函数中同样的两行，删除：
```python
    validated = validate_data_requests(role, entry.data_requests)
    blackboard.data_requests.extend(validated)
```

- [ ] **Step 6: Commit**

```bash
git add engine/agent/debate.py engine/agent/personas.py
git commit -m "refactor: 清理 speak_stream 数据请求逻辑，专家发言不再声明数据请求"
```

---

## Chunk 2: 前端 — Store + BlackboardPanel + 布局

### Task 5: Store 新增 `blackboardItems`

**Files:**
- Modify: `web/stores/useDebateStore.ts`

- [ ] **Step 1: 在文件顶部 `TranscriptItem` 类型定义之后，新增 `BlackboardItem` 类型**

```typescript
export interface BlackboardItem {
  id: string;
  source: "public" | "bull_expert" | "bear_expert";
  engine: string;
  action: string;
  title: string;
  status: "pending" | "done" | "failed";
  result_summary?: string;
  round: number;
}
```

- [ ] **Step 2: 在 `DebateStore` interface 中新增字段**

```typescript
blackboardItems: BlackboardItem[];
```

- [ ] **Step 3: 在初始 state 中新增**

```typescript
blackboardItems: [],
```

- [ ] **Step 4: 在 `reset()` 中新增**

```typescript
blackboardItems: [],
```

- [ ] **Step 5: 在 `_handleSSEEvent` 的 switch 中新增两个 case**

注意：使用 `get()` 在操作时重新获取最新 state，避免快速连续事件（pending→done）时的 stale state 竞态问题。

```typescript
    case "blackboard_update": {
      const item: BlackboardItem = {
        id: data.request_id as string,
        source: data.source as BlackboardItem["source"],
        engine: data.engine as string,
        action: data.action as string,
        title: data.title as string,
        status: data.status as BlackboardItem["status"],
        result_summary: data.result_summary as string | undefined,
        round: data.round as number,
      };
      const current = get().blackboardItems;
      const existing = current.findIndex(i => i.id === item.id);
      if (existing >= 0) {
        const updated = [...current];
        updated[existing] = item;
        set({ blackboardItems: updated });
      } else {
        set({ blackboardItems: [...current, item] });
      }
      break;
    }

    case "initial_data_complete":
      // 静默处理，无需 UI 状态变更
      break;
```

- [ ] **Step 6: TypeScript 检查**

```bash
cd web && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add web/stores/useDebateStore.ts
git commit -m "feat: store 新增 blackboardItems，处理 blackboard_update 事件"
```

---

### Task 6: 新增 `BlackboardPanel` 组件

**Files:**
- Create: `web/components/debate/BlackboardPanel.tsx`

- [ ] **Step 1: 创建组件文件**

```typescript
"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, ChevronUp, Loader2, Database, TrendingUp, Newspaper } from "lucide-react";
import type { BlackboardItem } from "@/stores/useDebateStore";

const SOURCE_LABEL: Record<string, string> = {
  public: "公用",
  bull_expert: "多头",
  bear_expert: "空头",
};

const SOURCE_COLOR: Record<string, string> = {
  public: "text-[var(--text-tertiary)] bg-[var(--bg-primary)]",
  bull_expert: "text-red-400 bg-red-500/10",
  bear_expert: "text-emerald-400 bg-emerald-500/10",
};

const ENGINE_ICON: Record<string, ReactNode> = {
  data: <Database size={11} />,
  quant: <TrendingUp size={11} />,
  info: <Newspaper size={11} />,
};

function BlackboardItemRow({ item }: { item: BlackboardItem }) {
  const [open, setOpen] = useState(false);
  const isPending = item.status === "pending";
  const isFailed = item.status === "failed";

  return (
    <div className="border-b border-[var(--border)] last:border-0">
      <button
        onClick={() => !isPending && setOpen(v => !v)}
        disabled={isPending}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--bg-primary)] transition-colors"
      >
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 ${SOURCE_COLOR[item.source]}`}>
          {SOURCE_LABEL[item.source] ?? item.source}
        </span>
        <span className="text-[var(--text-tertiary)] shrink-0">
          {ENGINE_ICON[item.engine] ?? <Database size={11} />}
        </span>
        <span className="text-xs text-[var(--text-secondary)] flex-1 truncate">{item.title}</span>
        {isPending
          ? <Loader2 size={11} className="animate-spin text-[var(--text-tertiary)] shrink-0" />
          : isFailed
          ? <span className="text-red-400 text-[10px] shrink-0">✗</span>
          : item.result_summary
          ? (open ? <ChevronUp size={11} className="text-[var(--text-tertiary)] shrink-0" />
                  : <ChevronDown size={11} className="text-[var(--text-tertiary)] shrink-0" />)
          : <span className="text-emerald-400 text-[10px] shrink-0">✓</span>
        }
      </button>
      {open && item.result_summary && (
        <div className="px-3 pb-2 text-[11px] text-[var(--text-secondary)] leading-relaxed bg-[var(--bg-primary)] border-t border-[var(--border)]">
          {item.result_summary}
        </div>
      )}
    </div>
  );
}

export default function BlackboardPanel({ items }: { items: BlackboardItem[] }) {
  return (
    <div className="w-60 shrink-0 flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--border)] shrink-0">
        <span className="text-xs font-semibold text-[var(--text-secondary)]">黑板</span>
        <span className="text-[10px] text-[var(--text-tertiary)] ml-2">{items.length} 条数据</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[var(--text-tertiary)] text-xs py-8">
            等待数据...
          </div>
        ) : (
          items.map(item => <BlackboardItemRow key={item.id} item={item} />)
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 检查**

```bash
cd web && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add web/components/debate/BlackboardPanel.tsx
git commit -m "feat: 新增 BlackboardPanel 组件"
```

---

### Task 7: 布局接入 BlackboardPanel

**Files:**
- Modify: `web/components/debate/BullBearArena.tsx`
- Modify: `web/components/debate/DebatePage.tsx`

- [ ] **Step 1: 修改 `BullBearArena.tsx`**

在文件顶部新增 import：
```typescript
import BlackboardPanel from "./BlackboardPanel";
import type { BlackboardItem } from "@/stores/useDebateStore";
```

在 `BullBearArenaProps` 中新增：
```typescript
blackboardItems: BlackboardItem[];
```

在组件签名中新增 `blackboardItems`，在 JSX 末尾（空头区之后）新增：
```tsx
      {/* 黑板面板 */}
      <BlackboardPanel items={blackboardItems} />
```

- [ ] **Step 2: 修改 `DebatePage.tsx`**

在 `useDebateStore()` 解构中新增 `blackboardItems`：
```typescript
const {
  status, transcript, roleState, blackboardItems,
  judgeVerdict, isReplayMode, error, currentTarget,
  startDebate, loadReplay, reset, stopDebate,
} = useDebateStore();
```

在 `<BullBearArena>` 调用中新增 prop：
```tsx
<BullBearArena
  transcript={transcript}
  roleState={roleState}
  verdict={isReplayMode ? judgeVerdict : null}
  blackboardItems={blackboardItems}
/>
```

- [ ] **Step 3: TypeScript 检查**

```bash
cd web && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add web/components/debate/BullBearArena.tsx web/components/debate/DebatePage.tsx
git commit -m "feat: 布局接入 BlackboardPanel，辩论页四列布局完成"
```

---

## 验收标准

1. 辩论开始后，黑板面板立即出现三条公用数据（股票信息/日线/新闻），pending 状态转圈，完成后显示 ✓
2. 每轮辩论开始前，多头/空头各自的数据请求出现在黑板，带来源标签（红/绿）
3. 点击已完成的黑板条目可展开查看结果摘要
4. 专家发言中不再出现【数据请求】文本
5. 对话流中不再出现 `data_request` 类型的气泡（旧的 data_request_start/done 事件已被新流程替代）
