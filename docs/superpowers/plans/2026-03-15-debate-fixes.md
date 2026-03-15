# 辩论系统修复与增强 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复辩论系统三个问题：扩展专家数据接口、修复 retail_sentiment_score 类型错误、对齐前端 SSE 事件处理。

**Architecture:** 后端新增 6 个 AKShare 数据方法挂在 DataFetcher 上，通过 self-routing 分支分发；前端 store 补全所有 SSE 事件处理，TranscriptFeed 新增 streaming 气泡和数据请求卡片。

**Tech Stack:** Python/FastAPI/AKShare (后端), TypeScript/Next.js/Zustand (前端)

**Spec:** `docs/superpowers/specs/2026-03-15-debate-fixes-design.md`

---

## Chunk 1: 后端 Bug 修复

### Task 1: 修复 retail_sentiment_score 类型错误 + debate_quality 枚举不一致

**Files:**
- Modify: `engine/agent/debate.py`

- [ ] **Step 1a: 修复 extract_structure prompt（约第 77 行）**

在 `engine/agent/debate.py` 的 `extract_structure()` 函数中，将 `extract_prompt` 里的这一行：
```python
  "retail_sentiment_score": null,
```
改为：
```python
  "retail_sentiment_score": null,  # 仅 retail_investor 角色填写，其他角色必须为 null。格式：单一浮点数 -1.0 到 +1.0，+1 极度乐观，-1 极度悲观
```

同时在 prompt 的 `data_requests` 示例中，将 `"params": {}` 改为 `"params": {"code": "<股票代码>"}`，引导 LLM 正确填写 code 参数：
```python
  "data_requests": [{"engine": "quant|data|info", "action": "动作名", "params": {"code": "<股票代码>"}}],
```

- [ ] **Step 1b: 修复 extract_structure 类型保护（第 98 行）**

将第 98 行：
```python
"retail_sentiment_score": parsed.get("retail_sentiment_score"),
```
改为：
```python
score = parsed.get("retail_sentiment_score")
"retail_sentiment_score": float(score) if isinstance(score, (int, float)) else None,
```

- [ ] **Step 2: 修复 _extract_judge_verdict prompt 中的 debate_quality 枚举**

在 `_extract_judge_verdict()` 的 `extract_prompt` 中（约第 578 行），将：
```
"debate_quality": "strong_disagreement" | "moderate_disagreement" | "consensus"
```
改为：
```
"debate_quality": "strong_disagreement" | "consensus" | "one_sided"
```

- [ ] **Step 3: 验证语法正确**

```bash
cd engine && .venv/bin/python -c "from agent.debate import extract_structure; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add engine/agent/debate.py
git commit -m "fix: retail_sentiment_score 类型保护 + debate_quality 枚举对齐"
```

---

### Task 2: 扩展白名单

**Files:**
- Modify: `engine/agent/personas.py`

- [ ] **Step 1: 扩展 DEBATE_DATA_WHITELIST**

将 `engine/agent/personas.py` 中的 `DEBATE_DATA_WHITELIST` 替换为：

```python
DEBATE_DATA_WHITELIST: dict[str, list[str]] = {
    "bull_expert": [
        "get_stock_info", "get_daily_history", "get_factor_scores",
        "get_news", "get_announcements", "get_technical_indicators",
        "get_cluster_for_stock", "get_financials", "get_turnover_rate",
    ],
    "bear_expert": [
        "get_stock_info", "get_daily_history", "get_factor_scores",
        "get_news", "get_announcements", "get_technical_indicators",
        "get_cluster_for_stock", "get_financials", "get_restrict_stock_unlock",
        "get_margin_balance",
    ],
    "retail_investor": [
        "get_news", "get_money_flow",
    ],
    "smart_money": [
        "get_technical_indicators", "get_factor_scores",
        "get_money_flow", "get_northbound_holding", "get_margin_balance",
        "get_turnover_rate",
    ],
}
```

- [ ] **Step 2: 验证**

```bash
cd engine && .venv/bin/python -c "
from agent.personas import DEBATE_DATA_WHITELIST
assert 'get_money_flow' in DEBATE_DATA_WHITELIST['smart_money']
assert 'get_financials' in DEBATE_DATA_WHITELIST['bull_expert']
print('ok')
"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add engine/agent/personas.py
git commit -m "feat: 扩展辩论数据白名单"
```

---

### Task 3: 实现新数据接口

**Files:**
- Modify: `engine/agent/data_fetcher.py`

- [ ] **Step 1: 扩展 fetch_by_request 支持 self-routing**

将 `fetch_by_request` 方法（约第 106 行）中的路由逻辑改为：

```python
async def fetch_by_request(self, req) -> Any:
    """按 DataRequest 路由到对应引擎方法或 DataFetcher 自身方法"""
    if req.action in ACTION_DISPATCH:
        module_name, getter_fn, method_name, is_async = ACTION_DISPATCH[req.action]
        mod = importlib.import_module(module_name)
        engine = getattr(mod, getter_fn)()
        method = getattr(engine, method_name)
        if is_async:
            return await method(**req.params)
        else:
            return await asyncio.to_thread(method, **req.params)
    elif hasattr(self, req.action):
        method = getattr(self, req.action)
        result = await asyncio.to_thread(method, **req.params)
        # 截断返回值，避免超出 LLM 上下文预算（debate.py data_request_done 也会截断到 200 字符，这里先截到 300）
        if isinstance(result, dict):
            return {k: str(v)[:300] if isinstance(v, str) else v for k, v in result.items()}
        return result
    else:
        raise ValueError(f"不支持的 action: {req.action}")
```

- [ ] **Step 2: 实现 get_financials**

在 `DataFetcher` 类末尾添加：

```python
def get_financials(self, code: str) -> dict:
    """获取最新一期财报关键指标"""
    try:
        import akshare as ak
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2020")
        if df.empty:
            return {"error": f"无财务数据: {code}"}
        row = df.iloc[-1]
        result: dict = {"code": code, "report_date": str(row.get("日期", ""))}
        for col in ["净资产收益率", "总资产净利率", "营业收入", "净利润", "资产负债率"]:
            if col in row.index:
                result[col] = str(row[col])
        return result
    except Exception as e:
        logger.warning(f"get_financials 失败 [{code}]: {e}")
        return {"error": str(e)}
```

- [ ] **Step 3: 实现 get_money_flow**

```python
def get_money_flow(self, code: str) -> dict:
    """获取当日资金流向"""
    try:
        import akshare as ak
        market = "sh" if code.startswith("6") else "sz"
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        if df.empty:
            return {"error": f"无资金流向数据: {code}"}
        row = df.iloc[-1]
        return {
            "code": code,
            "date": str(row.get("日期", "")),
            "主力净流入": str(row.get("主力净流入-净额", "")),
            "主力净流入占比": str(row.get("主力净流入-净占比", "")),
            "超大单净流入": str(row.get("超大单净流入-净额", "")),
            "大单净流入": str(row.get("大单净流入-净额", "")),
            "小单净流入": str(row.get("小单净流入-净额", "")),
        }
    except Exception as e:
        logger.warning(f"get_money_flow 失败 [{code}]: {e}")
        return {"error": str(e)}
```

- [ ] **Step 4: 实现 get_northbound_holding**

```python
def get_northbound_holding(self, code: str) -> dict:
    """获取北向持股数据"""
    try:
        import akshare as ak
        df = ak.stock_hsgt_individual_em(symbol=code)
        if df.empty:
            return {"error": f"无北向持股数据: {code}"}
        row = df.iloc[-1]
        return {
            "code": code,
            "date": str(row.get("日期", "")),
            "持股数量": str(row.get("持股数量", "")),
            "持股市值": str(row.get("持股市值", "")),
            "持股占比": str(row.get("持股占A股百分比", "")),
            "持股变化": str(row.get("持股变化数量", "")),
        }
    except Exception as e:
        logger.warning(f"get_northbound_holding 失败 [{code}]: {e}")
        return {"error": str(e)}
```

- [ ] **Step 5: 实现 get_margin_balance**

```python
def get_margin_balance(self, code: str) -> dict:
    """获取融资融券余额（按交易所路由：6xxxxx=上交所，其余=深交所）"""
    try:
        import akshare as ak
        if code.startswith("6"):
            df = ak.stock_margin_detail_sse(symbol=code)
        else:
            df = ak.stock_margin_detail_szse(symbol=code)
        if df.empty:
            return {"error": f"无融资融券数据: {code}"}
        row = df.iloc[-1]
        return {
            "code": code,
            "date": str(row.iloc[0]),
            "融资余额": str(row.get("融资余额", "")),
            "融券余量": str(row.get("融券余量", "")),
        }
    except Exception as e:
        logger.warning(f"get_margin_balance 失败 [{code}]: {e}")
        return {"error": str(e)}
```

- [ ] **Step 6: 实现 get_turnover_rate**

```python
def get_turnover_rate(self, code: str) -> dict:
    """从 DataEngine snapshot 获取换手率"""
    try:
        from data_engine import get_data_engine
        snapshot = get_data_engine().get_snapshot()
        row = snapshot[snapshot["code"] == code]
        if row.empty:
            return {"error": f"未找到 {code}"}
        return {"code": code, "turnover_rate": float(row.iloc[0]["turnover_rate"])}
    except Exception as e:
        logger.warning(f"get_turnover_rate 失败 [{code}]: {e}")
        return {"error": str(e)}
```

- [ ] **Step 7: 实现 get_restrict_stock_unlock**

```python
def get_restrict_stock_unlock(self, code: str) -> dict:
    """获取限售股解禁计划（最近 3 条）"""
    try:
        import akshare as ak
        df = ak.stock_restricted_release_detail_em(symbol=code)
        if df.empty:
            return {"code": code, "unlocks": []}
        unlocks = []
        for _, r in df.head(3).iterrows():
            unlocks.append({
                "解禁日期": str(r.get("解禁日期", "")),
                "解禁数量": str(r.get("解禁数量", "")),
                "解禁类型": str(r.get("限售类型", "")),
            })
        return {"code": code, "unlocks": unlocks}
    except Exception as e:
        logger.warning(f"get_restrict_stock_unlock 失败 [{code}]: {e}")
        return {"error": str(e)}
```

- [ ] **Step 8: 验证 self-routing**

```bash
cd engine && .venv/bin/python -c "
from agent.data_fetcher import DataFetcher
df = DataFetcher()
for action in ['get_financials','get_money_flow','get_northbound_holding','get_margin_balance','get_turnover_rate','get_restrict_stock_unlock']:
    assert hasattr(df, action), f'missing: {action}'
print('all 6 methods present')
"
```
Expected: `all 6 methods present`

- [ ] **Step 9: Commit**

```bash
git add engine/agent/data_fetcher.py
git commit -m "feat: DataFetcher 新增 6 个数据接口 + self-routing 分支"
```

---

## Chunk 2: 前端 SSE 对齐

### Task 4: 更新 TypeScript 类型 + store

**Files:**
- Modify: `web/types/debate.ts`
- Modify: `web/stores/useDebateStore.ts`

- [ ] **Step 1: 在 debate.ts 末尾新增类型**

```typescript
export interface DataRequestItem {
  id: string;
  requested_by: string;
  action: string;
  status: "pending" | "done" | "failed";
  result_summary?: string;
  duration_ms?: number;
}
```

- [ ] **Step 2: 更新 TranscriptItem 类型**

在 `web/stores/useDebateStore.ts` 中，将 `TranscriptItem` 替换为：

```typescript
export type TranscriptItem =
  | { type: "entry"; data: DebateEntry }
  | { type: "round_divider"; round: number; is_final: boolean }
  | { type: "system"; text: string }
  | { type: "streaming"; role: string; round: number | null; tokens: string }
  | { type: "data_request"; id: string; requested_by: string; action: string; status: "pending" | "done" | "failed"; result_summary?: string; duration_ms?: number };
```

- [ ] **Step 3: 替换 _handleSSEEvent 中废弃的 case，补全新 case**

删除 `debate_entry`、`data_fetching`、`data_ready` 三个 case。

新增以下 case（插入到 `debate_round_start` 之后）：

```typescript
case "debate_token": {
  const { role, round, tokens } = data as { role: string; round: number | null; tokens: string };
  const existing = state.transcript.findIndex(
    (item) => item.type === "streaming" && item.role === role && item.round === round
  );
  if (existing >= 0) {
    const updated = [...state.transcript];
    const item = updated[existing] as { type: "streaming"; role: string; round: number | null; tokens: string };
    updated[existing] = { ...item, tokens: item.tokens + tokens };
    set({ transcript: updated });
  } else {
    set({ transcript: [...state.transcript, { type: "streaming", role, round, tokens }] });
  }
  break;
}

case "debate_entry_complete": {
  const entry = data as unknown as DebateEntry;
  // 用 role + round 精确匹配 streaming item（避免多轮同角色替换错误）
  const idx = state.transcript.findLastIndex(
    (item) => item.type === "streaming" && item.role === entry.role && item.round === entry.round
  );
  const newTranscript = idx >= 0
    ? [...state.transcript.slice(0, idx), { type: "entry" as const, data: entry }, ...state.transcript.slice(idx + 1)]
    : [...state.transcript, { type: "entry" as const, data: entry }];

  if (DEBATERS.includes(entry.role)) {
    set({
      transcript: newTranscript,
      roleState: {
        ...state.roleState,
        [entry.role]: { stance: entry.stance, confidence: entry.confidence, conceded: entry.stance === "concede" },
      },
    });
  } else if (OBSERVERS.includes(entry.role)) {
    set({
      transcript: newTranscript,
      observerState: {
        ...state.observerState,
        [entry.role]: { speak: entry.speak, argument: entry.argument, retail_sentiment_score: entry.retail_sentiment_score ?? undefined },
      },
      _observerSpokenThisRound: { ...state._observerSpokenThisRound, [entry.role]: true },
    });
  } else {
    set({ transcript: newTranscript });
  }
  break;
}

case "data_request_start": {
  const { request_id, requested_by, action } = data as { request_id: string; requested_by: string; action: string };
  set({
    transcript: [...state.transcript, { type: "data_request", id: request_id, requested_by, action, status: "pending" }],
  });
  break;
}

case "data_request_done": {
  const { request_id, status, result_summary, duration_ms } = data as { request_id: string; status: "done" | "failed"; result_summary: string; duration_ms: number };
  set({
    transcript: state.transcript.map((item) =>
      item.type === "data_request" && item.id === request_id
        ? { ...item, status, result_summary, duration_ms }
        : item
    ),
  });
  break;
}

case "judge_token": {
  const { tokens } = data as { tokens: string };
  const existing = state.transcript.findIndex(
    (item) => item.type === "streaming" && item.role === "judge"
  );
  if (existing >= 0) {
    const updated = [...state.transcript];
    const item = updated[existing] as { type: "streaming"; role: string; round: number | null; tokens: string };
    updated[existing] = { ...item, tokens: item.tokens + tokens };
    set({ transcript: updated });
  } else {
    set({ transcript: [...state.transcript, { type: "streaming", role: "judge", round: null, tokens }] });
  }
  break;
}
```

- [ ] **Step 4: Commit**

```bash
git add web/types/debate.ts web/stores/useDebateStore.ts
git commit -m "feat: 补全 SSE 事件处理（debate_token/entry_complete/data_request/judge_token）"
```

---

### Task 5: 更新 TranscriptFeed 渲染新类型

**Files:**
- Modify: `web/components/debate/TranscriptFeed.tsx`

- [ ] **Step 1: 修复 "speech" 死代码，新增 streaming 和 data_request 渲染**

1. 将第 76 行 `item.type === "speech"` 改为 `item.type === "entry"`，保留其中的 `<ObserverBar>` 渲染（仅在辩论者发言后显示观察员状态，这是正确行为）：

```tsx
if (item.type === "entry") {
  const retail = observerState["retail_investor"];
  const smart = observerState["smart_money"];
  return (
    <div key={idx} className="space-y-3">
      <SpeechBubble entry={item.data} />
      <ObserverBar retail={retail} smart={smart} />
    </div>
  );
}
```

2. 删除旧的 `item.type === "loading"` 块（第 65-74 行）

3. 在 `item.type === "system"` 块之后，新增 streaming 渲染：

```tsx
if (item.type === "streaming") {
  const roleLabel: Record<string, string> = {
    bull_expert: "多头专家", bear_expert: "空头专家",
    retail_investor: "散户", smart_money: "主力", judge: "裁判",
  };
  return (
    <div key={idx} className="flex justify-start px-1">
      <div className="max-w-[85%] rounded-2xl px-4 py-3 bg-[var(--bg-secondary)] border border-[var(--border)] text-sm text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">
        <span className="text-xs text-[var(--text-tertiary)] block mb-1">
          {roleLabel[item.role] ?? item.role}
        </span>
        {item.tokens}
        <span className="inline-block w-0.5 h-4 bg-[var(--text-primary)] animate-pulse ml-0.5 align-middle" />
      </div>
    </div>
  );
}
```

4. 新增 data_request 渲染：

```tsx
if (item.type === "data_request") {
  const isPending = item.status === "pending";
  const isFailed = item.status === "failed";
  return (
    <div key={idx} className="flex justify-center">
      <div className={`flex flex-col gap-1 px-4 py-2 rounded-xl border text-xs max-w-[90%] ${
        isPending ? "border-[var(--border)] bg-[var(--bg-primary)]"
        : isFailed ? "border-red-500/20 bg-red-500/5"
        : "border-emerald-500/20 bg-emerald-500/5"
      }`}>
        <div className="flex items-center gap-2">
          {isPending && <Loader2 size={11} className="animate-spin text-[var(--text-tertiary)]" />}
          {!isPending && <span className={isFailed ? "text-red-400" : "text-emerald-400"}>{isFailed ? "✗" : "✓"}</span>}
          <span className="text-[var(--text-tertiary)]">{item.requested_by}</span>
          <span className="font-medium text-[var(--text-secondary)]">{item.action}</span>
          {item.duration_ms !== undefined && (
            <span className="text-[var(--text-tertiary)]">{item.duration_ms}ms</span>
          )}
        </div>
        {item.result_summary && (
          <p className="text-[var(--text-secondary)] pl-4 leading-relaxed">{item.result_summary}</p>
        )}
      </div>
    </div>
  );
}
```

5. 将最后的 fallback（第 86 行）`return <SpeechBubble key={idx} entry={item.data} />;` 改为 `return null;`

   **注意：** 此时 `entry` 类型已在上方 Step 1 的 `item.type === "entry"` 块中处理，fallback `null` 只会被 `streaming`/`data_request` 之外的未知类型触发，不会丢失任何发言。Step 1 的 `"entry"` 块必须先完成，否则所有发言会消失。

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd web && npx tsc --noEmit 2>&1 | head -30
```
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add web/components/debate/TranscriptFeed.tsx
git commit -m "feat: TranscriptFeed 支持 streaming 气泡和数据请求卡片"
```

> **注意：** `SpeechBubble.tsx` 无需修改。streaming 状态的光标动画已在 `TranscriptFeed` 的 `streaming` item 渲染中内联实现，不依赖 `SpeechBubble`。

---

## Chunk 3: 端到端验证

### Task 6: 冒烟测试

- [ ] **Step 1: 验证后端新接口可调用**

```bash
cd engine && .venv/bin/python -c "
import asyncio
from agent.data_fetcher import DataFetcher
from agent.schemas import DataRequest

async def test():
    df = DataFetcher()
    req = DataRequest(requested_by='test', engine='self', action='get_turnover_rate', params={'code': '600406'}, round=0)
    result = await df.fetch_by_request(req)
    print('get_turnover_rate:', result)

asyncio.run(test())
"
```
Expected: `{'code': '600406', 'turnover_rate': ...}`

- [ ] **Step 2: 验证 retail_sentiment_score 修复**

```bash
cd engine && .venv/bin/python -c "
import asyncio, json
from unittest.mock import patch, MagicMock, AsyncMock
from agent.schemas import Blackboard

async def test():
    from agent.debate import extract_structure
    blackboard = Blackboard(target='600406', debate_id='test_001')
    mock_llm = MagicMock()
    bad_response = json.dumps({
        'stance': 'insist', 'confidence': 0.7, 'challenges': [],
        'data_requests': [],
        'retail_sentiment_score': {'国际医学': -0.8, '裕同科技': 0.45},
        'speak': True
    })
    with patch('agent.debate.asyncio.wait_for', new=AsyncMock(return_value=bad_response)):
        result = await extract_structure('test', 'retail_investor', blackboard, mock_llm)
    assert result['retail_sentiment_score'] is None, f'Expected None, got {result[\"retail_sentiment_score\"]}'
    print('PASS')

asyncio.run(test())
"
```
Expected: `PASS`

- [ ] **Step 3: 验证前端编译**

```bash
cd web && npx tsc --noEmit 2>&1 | grep -E "error|Error" | head -10
```
Expected: 无输出（无错误）

- [ ] **Step 4: 最终 commit**

```bash
git add -A
git commit -m "feat: 辩论系统修复完成 - 数据接口/类型修复/前端SSE对齐"
```
