# 辩论 Token 压缩实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为辩论系统增加标准/快速双模式，快速模式通过 LLM 预压缩初始数据减少后续 context 大小。

**Architecture:** API 入口接收 mode 参数，存入 Blackboard。快速模式在初始数据拉取后增加一次 LLM 调用将 facts + 行业认知压缩为摘要。`_build_context_for_role` 根据 mode 选择注入全量数据或摘要。前端 InputBar 加模式切换按钮。

**Tech Stack:** Python/FastAPI/Pydantic (后端), Next.js/Zustand/TypeScript (前端), SSE streaming

**Spec:** `docs/superpowers/specs/2026-03-16-debate-token-compression-design.md`

---

## Chunk 1: 后端核心

### Task 1: Blackboard 数据模型扩展

**Files:**
- Modify: `engine/agent/schemas.py:139-170` (Blackboard class)

- [ ] **Step 1: 添加 mode 和 facts_summary 字段**

在 `Blackboard` 类中，`as_of_date` 字段之后添加：

```python
mode: Literal["standard", "fast"] = "standard"
facts_summary: str | None = None  # 快速模式下的 LLM 压缩摘要
```

确保 `Literal` 已在文件顶部的 `typing` import 中（已有）。

- [ ] **Step 2: 验证**

```bash
cd engine && .venv/bin/python -c "from agent.schemas import Blackboard; b = Blackboard(target='test', debate_id='test_001', mode='fast'); print(b.mode, b.facts_summary)"
```

Expected: `fast None`

- [ ] **Step 3: Commit**

```bash
git add engine/agent/schemas.py
git commit -m "feat: Blackboard 新增 mode 和 facts_summary 字段"
```

---

### Task 2: compress_facts() 函数

**Files:**
- Modify: `engine/agent/debate.py`

- [ ] **Step 1: 添加 FACTS_COMPRESSION_PROMPT 常量**

在 `INDUSTRY_COGNITION_PROMPT` 常量之后（约 line 610 附近），添加：

```python
FACTS_COMPRESSION_PROMPT = """你是金融数据分析师。请将以下原始市场数据压缩为结构化摘要，保留对多空辩论最关键的信息。

## 原始数据
{raw_facts}

## 压缩要求
输出一段结构化文本（非 JSON），包含：
1. 【标的概况】一句话（名称、行业、市值量级）
2. 【近期走势】区间涨跌幅、关键价位（支撑/压力）、成交量变化趋势（3-5句）
3. 【关键事件】最重要的 2-3 条新闻/公告及其情感倾向
4. 【行业背景】核心驱动变量、当前周期定位、最关键的认知陷阱（2-3句）

总字数控制在 500-800 字。只保留对投资决策有直接影响的信息。"""
```

- [ ] **Step 2: 添加 _serialize_facts_for_compression() 辅助函数**

在 FACTS_COMPRESSION_PROMPT 之后添加。此函数将 blackboard 的 facts + industry_cognition 序列化为纯文本，供压缩 prompt 使用：

```python
def _serialize_facts_for_compression(blackboard: Blackboard) -> str:
    """将 facts + industry_cognition 序列化为压缩用的原始文本"""
    parts = []

    # 股票基本信息
    info = blackboard.facts.get("get_stock_info", {})
    if info:
        parts.append(f"## 股票信息\n{_format_fact(info)}")

    # 日线数据
    daily = blackboard.facts.get("get_daily_history", {})
    if daily and isinstance(daily, dict) and "recent" in daily:
        parts.append(f"## 日线行情（{daily.get('days', '?')}个交易日）")
        for row in daily["recent"]:
            date_str = str(row.get("date", ""))[:10]
            parts.append(
                f"  {date_str} 开:{row.get('open','')} 高:{row.get('high','')} "
                f"低:{row.get('low','')} 收:{row.get('close','')} "
                f"涨跌:{row.get('pct_chg','')}% 换手:{row.get('turnover_rate','')}%"
            )

    # 新闻
    news = blackboard.facts.get("get_news")
    if news:
        parts.append("## 新闻")
        items = news if isinstance(news, list) else [news]
        for item in items:
            if isinstance(item, dict):
                parts.append(f"  [{item.get('sentiment','')}] {item.get('title','')} — {item.get('content','')[:200]}")
            elif hasattr(item, "model_dump"):
                d = item.model_dump()
                parts.append(f"  [{d.get('sentiment','')}] {d.get('title','')} — {d.get('content','')[:200]}")

    # 行业认知
    ic = blackboard.industry_cognition
    if ic:
        parts.append(f"## 行业认知（{ic.industry}）")
        parts.append(f"产业链: 上游={ic.upstream}, 下游={ic.downstream}")
        parts.append(f"核心驱动: {ic.core_drivers}")
        parts.append(f"成本结构: {ic.cost_structure}")
        parts.append(f"壁垒: {ic.barriers}")
        parts.append(f"供需: {ic.supply_demand}")
        parts.append(f"认知陷阱: {ic.common_traps}")
        parts.append(f"周期: {ic.cycle_position} — {ic.cycle_reasoning}")
        parts.append(f"催化剂: {ic.catalysts}")
        parts.append(f"风险: {ic.risks}")

    return "\n".join(parts)
```

- [ ] **Step 3: 添加 compress_facts() async generator**

在 `_serialize_facts_for_compression` 之后添加：

```python
async def compress_facts(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> AsyncGenerator[dict, None]:
    """快速模式：LLM 预压缩 facts + 行业认知为摘要"""
    yield sse("facts_compression_start", {"mode": "fast"})

    raw_facts = _serialize_facts_for_compression(blackboard)
    if not raw_facts.strip():
        logger.warning("无数据可压缩，跳过")
        blackboard.mode = "standard"
        yield sse("facts_compression_done", {"error": True, "fallback": "standard"})
        return

    prompt = FACTS_COMPRESSION_PROMPT.format(raw_facts=raw_facts)
    original_est = len(raw_facts) // 2  # 粗略估算 token 数

    try:
        chunks: list[str] = []
        async for token in llm.chat_stream([ChatMessage(role="user", content=prompt)]):
            chunks.append(token)
        summary = "".join(chunks).strip()

        if not summary or len(summary) < 50:
            raise ValueError(f"压缩结果过短: {len(summary)} 字符")

        blackboard.facts_summary = summary
        compressed_est = len(summary) // 2
        ratio = round(compressed_est / max(original_est, 1), 2)

        yield sse("facts_compression_done", {
            "original_tokens_est": original_est,
            "compressed_tokens_est": compressed_est,
            "compression_ratio": ratio,
        })
        logger.info(f"数据压缩完成: {original_est} → {compressed_est} tokens (ratio={ratio})")

    except Exception as e:
        logger.warning(f"数据压缩失败，降级为标准模式: {type(e).__name__}: {e}")
        blackboard.mode = "standard"
        blackboard.facts_summary = None
        yield sse("facts_compression_done", {"error": True, "fallback": "standard"})
```

- [ ] **Step 4: 验证语法**

```bash
cd engine && .venv/bin/python -c "from agent.debate import compress_facts; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: compress_facts() LLM 预压缩函数"
```

---

### Task 3: _build_context_for_role 快速模式分支 + run_debate 集成

**Files:**
- Modify: `engine/agent/debate.py`

- [ ] **Step 1: 修改 _build_context_for_role()**

找到 `_build_context_for_role` 函数（约 line 270）。在时间锚点之后、行业认知注入之前，添加快速模式分支：

将当前的行业认知 + facts 注入逻辑包裹在 else 分支中：

```python
def _build_context_for_role(blackboard: Blackboard) -> str:
    parts = []

    # 时间锚点
    if blackboard.as_of_date:
        parts.append(f"## 辩论时间基准\n当前讨论基于 {blackboard.as_of_date} 收盘后的市场环境。所有数据截止到该日期。\n")

    # 快速模式：用压缩摘要替代 facts + industry_cognition
    if blackboard.mode == "fast" and blackboard.facts_summary:
        parts.append("## 市场数据摘要（压缩版）")
        parts.append(blackboard.facts_summary)
        parts.append("")
    else:
        # 标准模式：行业认知全量注入（现有代码不变）
        if blackboard.industry_cognition:
            ...  # 保持现有行业认知注入代码不变

        # 公用初始数据 facts 全量注入（现有代码不变）
        if blackboard.facts:
            ...  # 保持现有 facts 注入代码不变

    # 以下代码不变：worker verdicts, conflicts, transcript, 补充数据
    ...
```

关键：只需要在现有的行业认知和 facts 注入代码外面包一层 `if/else`，不要删除或修改现有逻辑。

- [ ] **Step 2: 在 run_debate() 中集成 compress_facts**

找到 `run_debate()` 函数中 `generate_industry_cognition` 调用之后（约 line 1287），在 `while blackboard.round < blackboard.max_rounds:` 之前，添加：

```python
    # 快速模式：LLM 预压缩
    if blackboard.mode == "fast":
        async for event in compress_facts(blackboard, llm):
            yield event
```

- [ ] **Step 3: 在 debate_start 事件中包含 mode**

找到 `run_debate()` 中的 `yield sse("debate_start", {...})` 调用，在 payload dict 中添加 `"mode": blackboard.mode`：

```python
    yield sse("debate_start", {
        "debate_id": blackboard.debate_id,
        "target": blackboard.target,
        "as_of_date": blackboard.as_of_date,
        "max_rounds": blackboard.max_rounds,
        "mode": blackboard.mode,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"],
    })
```

- [ ] **Step 4: 验证语法**

```bash
cd engine && .venv/bin/python -c "from agent.debate import run_debate; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: _build_context_for_role 快速模式分支 + run_debate 集成 compress_facts"
```

---

### Task 4: API 路由支持 mode 参数

**Files:**
- Modify: `engine/api/routes/debate.py:17-43`

- [ ] **Step 1: DebateRequest 新增 mode 字段**

```python
class DebateRequest(BaseModel):
    code: str = Field(description="股票代码，如 '001896'")
    max_rounds: int = Field(default=3, ge=1, le=5)
    mode: str = Field(default="standard", description="辩论模式: standard | fast")
```

- [ ] **Step 2: 传入 Blackboard**

在 `start_debate` 函数中，创建 Blackboard 时传入 mode：

```python
    blackboard = Blackboard(
        target=req.code,
        debate_id=f"{req.code}_{now.strftime('%Y%m%d%H%M%S')}",
        max_rounds=req.max_rounds,
        mode=req.mode if req.mode in ("standard", "fast") else "standard",
    )
```

- [ ] **Step 3: 验证**

```bash
cd engine && .venv/bin/python -c "
from api.routes.debate import DebateRequest
r = DebateRequest(code='600519', mode='fast')
print(r.mode)
"
```

Expected: `fast`

- [ ] **Step 4: Commit**

```bash
git add engine/api/routes/debate.py
git commit -m "feat: DebateRequest 新增 mode 参数，传入 Blackboard"
```

---

## Chunk 2: 前端

### Task 5: useDebateStore SSE 事件处理

**Files:**
- Modify: `web/stores/useDebateStore.ts`

- [ ] **Step 1: TranscriptItem 新增 facts_compression 类型**

在 `TranscriptItem` 联合类型中添加：

```typescript
  | { id: string; type: "facts_compression"; mode: string; loading: boolean;
      original_tokens_est?: number; compressed_tokens_est?: number;
      compression_ratio?: number; error?: boolean; fallback?: string }
```

- [ ] **Step 2: startDebate 签名新增 mode 参数**

修改 `DebateStore` interface：
```typescript
startDebate: (code: string, maxRounds: number, mode?: string) => Promise<void>;
```

修改 `startDebate` 实现，接收 mode 参数并传入请求体：
```typescript
startDebate: async (code, maxRounds, mode = "standard") => {
    ...
    body: JSON.stringify({ code, max_rounds: maxRounds, mode }),
    ...
```

- [ ] **Step 3: 添加 SSE 事件处理**

在 `_handleSSEEvent` 的 switch 中，`industry_cognition_start` case 之前添加：

```typescript
    case "facts_compression_start": {
      set({
        transcript: [...state.transcript, {
          id: "facts_compression",
          type: "facts_compression",
          mode: data.mode as string,
          loading: true,
        }],
      });
      break;
    }

    case "facts_compression_done": {
      set({
        transcript: state.transcript.map((item) =>
          item.type === "facts_compression"
            ? {
                ...item,
                loading: false,
                original_tokens_est: data.original_tokens_est as number | undefined,
                compressed_tokens_est: data.compressed_tokens_est as number | undefined,
                compression_ratio: data.compression_ratio as number | undefined,
                error: data.error as boolean | undefined,
                fallback: data.fallback as string | undefined,
              }
            : item
        ),
      });
      break;
    }
```

- [ ] **Step 4: 验证前端编译**

```bash
cd web && npx next build 2>&1 | tail -5
```

Expected: `✓ Compiled successfully`

- [ ] **Step 5: Commit**

```bash
git add web/stores/useDebateStore.ts
git commit -m "feat: useDebateStore 支持 mode 参数 + facts_compression SSE 事件"
```

---

### Task 6: InputBar 模式切换 + TranscriptFeed 压缩卡片

**Files:**
- Modify: `web/components/debate/InputBar.tsx`
- Modify: `web/components/debate/TranscriptFeed.tsx`

- [ ] **Step 1: InputBar 新增 mode state 和切换按钮**

修改 `InputBarProps`，新增 mode 相关：
```typescript
interface InputBarProps {
  status: DebateStatus;
  isReplayMode: boolean;
  onStart: (code: string, maxRounds: number, mode: string) => void;
  onHistoryOpen: () => void;
  onStop: () => void;
  onExport?: () => void;
}
```

在组件内添加 state：
```typescript
const [mode, setMode] = useState<"standard" | "fast">("standard");
```

在轮次 `<select>` 和开始按钮之间添加切换按钮：
```tsx
<button
  onClick={() => setMode(m => m === "standard" ? "fast" : "standard")}
  disabled={busy}
  className="h-10 px-3 rounded-lg text-xs font-medium border border-[var(--border)]
             text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]
             disabled:opacity-50 transition-colors shrink-0"
  title={mode === "fast" ? "快速模式：压缩数据，加速辩论" : "标准模式：完整数据，深度分析"}
>
  {mode === "fast" ? "⚡ 快速" : "📊 标准"}
</button>
```

修改开始按钮的 onClick：
```tsx
onClick={() => { code && onStart(code, maxRounds, mode); }}
```

- [ ] **Step 2: 更新 DebatePage 中 InputBar 的 onStart 调用**

找到使用 `InputBar` 的页面组件，确保 `onStart` 传递 mode 参数到 `startDebate`。

查找文件：
```bash
grep -r "onStart=" web/components/debate/ web/app/
```

在对应的 `onStart` handler 中传递 mode：
```tsx
onStart={(code, rounds, mode) => startDebate(code, rounds, mode)}
```

- [ ] **Step 3: TranscriptFeed 新增 FactsCompressionCard**

在 `TranscriptFeed.tsx` 的 `transcript.map` 中，`industry_cognition` 判断之前添加：
```tsx
if (item.type === "facts_compression") {
  return <FactsCompressionCard key={item.id} item={item} />;
}
```

在 `IndustryCognitionCard` 组件之前添加 `FactsCompressionCard`：

```tsx
// ── 数据压缩卡片 ────────────────────────────────────
function FactsCompressionCard({ item }: { item: Extract<TranscriptItem, { type: "facts_compression" }> }) {
  if (item.loading) {
    return (
      <div className="flex justify-center">
        <div className="w-full max-w-[90%] rounded-xl border border-blue-500/20 bg-blue-500/5 text-xs overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 text-[var(--text-tertiary)]">
            <Loader2 size={12} className="animate-spin text-blue-400" />
            <span className="text-blue-400 font-medium">数据压缩</span>
            <span>正在压缩市场数据...</span>
          </div>
        </div>
      </div>
    );
  }

  if (item.error) {
    return (
      <div className="flex justify-center">
        <div className="w-full max-w-[90%] rounded-xl border border-yellow-500/20 bg-yellow-500/5 text-xs overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 text-[var(--text-tertiary)]">
            <span className="text-yellow-400">⚠</span>
            <span className="text-yellow-400 font-medium">数据压缩</span>
            <span>压缩失败，已降级为标准模式</span>
          </div>
        </div>
      </div>
    );
  }

  const pct = item.compression_ratio != null ? Math.round(item.compression_ratio * 100) : null;
  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[90%] rounded-xl border border-blue-500/20 bg-blue-500/5 text-xs overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2.5 text-[var(--text-tertiary)]">
          <span className="text-blue-400">⚡</span>
          <span className="text-blue-400 font-medium">数据压缩</span>
          <span>
            {item.original_tokens_est} → {item.compressed_tokens_est} tokens
            {pct != null && <span className="ml-1 text-blue-400">({pct}%)</span>}
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 验证前端编译**

```bash
cd web && npx next build 2>&1 | tail -5
```

Expected: `✓ Compiled successfully`

- [ ] **Step 5: Commit**

```bash
git add web/components/debate/InputBar.tsx web/components/debate/TranscriptFeed.tsx
git commit -m "feat: InputBar 模式切换按钮 + FactsCompressionCard 组件"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 重启后端**

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null
cd engine && nohup .venv/bin/python main.py > /tmp/stockterrain_backend.log 2>&1 &
sleep 3 && tail -5 /tmp/stockterrain_backend.log
```

Expected: `Application startup complete.`

- [ ] **Step 2: 测试标准模式（回归）**

```bash
curl -s -N -X POST http://localhost:8000/api/v1/debate \
  -H "Content-Type: application/json" \
  -d '{"code": "600519", "max_rounds": 1, "mode": "standard"}' 2>&1 | head -20
```

Expected: `debate_start` 事件包含 `"mode": "standard"`，无 `facts_compression` 事件。

- [ ] **Step 3: 测试快速模式**

```bash
curl -s -N -X POST http://localhost:8000/api/v1/debate \
  -H "Content-Type: application/json" \
  -d '{"code": "600519", "max_rounds": 1, "mode": "fast"}' 2>&1 | grep -E "facts_compression|debate_start"
```

Expected:
- `debate_start` 包含 `"mode": "fast"`
- `facts_compression_start` 事件
- `facts_compression_done` 事件（含 `original_tokens_est`, `compressed_tokens_est`, `compression_ratio`）

- [ ] **Step 4: 验证前端编译**

```bash
cd web && npx next build 2>&1 | tail -5
```

Expected: `✓ Compiled successfully`
