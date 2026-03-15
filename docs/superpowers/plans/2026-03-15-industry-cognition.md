# 辩论系统行业认知层 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 辩论启动时自动生成/检索行业产业链认知，注入黑板供所有专家共享，前端展示行业认知卡片。

**Architecture:** 新增 `IndustryCognition` 数据模型和 `generate_industry_cognition()` 异步生成器。辩论启动时在拉取个股数据之后、辩论轮次之前插入行业认知阶段。LLM 生成结果缓存到 DuckDB（结构化）+ ChromaDB（语义检索）。前端新增可折叠的行业认知卡片。

**Tech Stack:** Python/FastAPI/Pydantic (后端), TypeScript/Next.js/Zustand (前端), DuckDB + ChromaDB (缓存)

**Spec:** `docs/superpowers/specs/2026-03-15-industry-cognition-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| `engine/agent/schemas.py` | 新增 `IndustryCognition` 模型，`Blackboard` 新增字段 |
| `engine/agent/debate.py` | 新增 `generate_industry_cognition()` 生成器，`_build_context_for_role` 注入，`run_debate` 调用 |
| `engine/agent/personas.py` | 四个辩论角色 system prompt 追加产业链推理指令 |
| `engine/data_engine/store.py` | 新增 `shared.industry_cognition` 表 |
| `web/stores/useDebateStore.ts` | `TranscriptItem` 新增类型，SSE 事件处理 |
| `web/components/debate/TranscriptFeed.tsx` | 新增 `IndustryCognitionCard` 组件 |

---

## Chunk 1: 后端数据模型与缓存

### Task 1: IndustryCognition 数据模型

**Files:**
- Modify: `engine/agent/schemas.py`

- [ ] **Step 1: 在 schemas.py 中新增 IndustryCognition 模型**

在 `Blackboard` 类之前（约第 107 行前）插入：

```python
class IndustryCognition(BaseModel):
    """行业产业链认知 — LLM 生成，缓存复用"""
    industry: str                    # 行业名称（如"小金属"、"半导体"）
    target: str                      # 触发股票代码

    # 产业链结构
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)
    core_drivers: list[str] = Field(default_factory=list)
    cost_structure: str = ""
    barriers: str = ""

    # 供需格局
    supply_demand: str = ""

    # 认知陷阱
    common_traps: list[str] = Field(default_factory=list)

    # 周期定位
    cycle_position: str = ""         # 景气上行|下行|拐点向上|拐点向下|高位震荡|底部盘整
    cycle_reasoning: str = ""

    # 催化剂/风险
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    # 元数据
    generated_at: str = ""
    as_of_date: str = ""
```

- [ ] **Step 2: Blackboard 新增 industry_cognition 字段**

在 `Blackboard` 类的 `as_of_date` 字段之后添加：

```python
    industry_cognition: IndustryCognition | None = None  # 行业认知
```

- [ ] **Step 3: 验证**

```bash
cd engine && .venv/bin/python -c "
from agent.schemas import IndustryCognition, Blackboard
ic = IndustryCognition(industry='小金属', target='600549')
bb = Blackboard(target='600549', debate_id='test', industry_cognition=ic)
assert bb.industry_cognition.industry == '小金属'
print('ok')
"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add engine/agent/schemas.py
git commit -m "feat: 新增 IndustryCognition 数据模型，Blackboard 新增 industry_cognition 字段"
```

---

### Task 2: DuckDB 缓存表

**Files:**
- Modify: `engine/data_engine/store.py`

- [ ] **Step 1: 在 _init_tables() 末尾新增 industry_cognition 表**

在 `_init_tables()` 方法末尾（约第 221 行之前的 `except` 之前）添加：

```python
        # 行业认知缓存
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shared.industry_cognition (
                industry    VARCHAR NOT NULL,
                as_of_date  VARCHAR NOT NULL,
                target      VARCHAR NOT NULL,
                cognition_json TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (industry, as_of_date)
            )
        """)
```

- [ ] **Step 2: 验证**

```bash
cd engine && .venv/bin/python -c "
from data_engine.store import DuckDBStore
store = DuckDBStore(':memory:')
tables = store._conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema='shared'\").fetchall()
names = [t[0] for t in tables]
assert 'industry_cognition' in names, f'missing, got {names}'
print('ok')
"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add engine/data_engine/store.py
git commit -m "feat: DuckDB 新增 shared.industry_cognition 缓存表"
```

---

## Chunk 2: 后端行业认知生成与注入

### Task 3: generate_industry_cognition() 生成器

**Files:**
- Modify: `engine/agent/debate.py`

- [ ] **Step 1: 新增行业认知生成 prompt 常量**

在 `debate.py` 的 `ACTION_TITLE_MAP` 之后（约第 499 行后）添加：

```python
INDUSTRY_COGNITION_PROMPT = """你是产业链分析专家。请基于你对 {industry} 行业的深度理解，生成以下结构化分析。
当前讨论标的：{target}（{stock_name}），时间基准：{as_of_date}。

请以 JSON 格式返回：
{{
  "upstream": ["上游环节1", "上游环节2"],
  "downstream": ["下游应用1", "下游应用2"],
  "core_drivers": ["核心驱动变量1 — 简要说明", "..."],
  "cost_structure": "成本结构描述（原材料占比、人工、能源等）",
  "barriers": "行业壁垒（资源、技术、资质、规模等）",
  "supply_demand": "当前供需格局分析（供给端变化、需求端趋势、库存状态）",
  "common_traps": [
    "认知陷阱1 — 表面逻辑 vs 实际逻辑",
    "认知陷阱2 — ..."
  ],
  "cycle_position": "景气上行 | 景气下行 | 拐点向上 | 拐点向下 | 高位震荡 | 底部盘整",
  "cycle_reasoning": "周期判断的具体依据",
  "catalysts": ["潜在催化剂1", "..."],
  "risks": ["关键风险1", "..."]
}}

要求：
- common_traps 是最关键的部分，必须列出该行业中投资者最容易犯的认知错误
- 每个陷阱要说明「表面逻辑」和「实际逻辑」的差异
- cycle_position 必须给出明确判断，不能模棱两可
- 所有分析基于 {as_of_date} 时点的行业状态"""
```

- [ ] **Step 2: 新增缓存读写辅助函数**

在 prompt 常量之后添加：

```python
def _load_cached_cognition(industry: str, as_of_date: str) -> IndustryCognition | None:
    """从 DuckDB 读取缓存的行业认知"""
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn
        row = con.execute(
            "SELECT cognition_json FROM shared.industry_cognition WHERE industry = ? AND as_of_date = ?",
            [industry, as_of_date],
        ).fetchone()
        if row:
            import json
            data = json.loads(row[0])
            return IndustryCognition(**data)
    except Exception as e:
        logger.debug(f"行业认知缓存读取失败: {e}")
    return None


def _save_cognition_cache(cognition: IndustryCognition):
    """写入 DuckDB + ChromaDB 缓存"""
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn
        con.execute(
            "INSERT OR REPLACE INTO shared.industry_cognition (industry, as_of_date, target, cognition_json) VALUES (?, ?, ?, ?)",
            [cognition.industry, cognition.as_of_date, cognition.target, cognition.model_dump_json()],
        )
    except Exception as e:
        logger.warning(f"行业认知 DuckDB 缓存写入失败: {e}")

    # ChromaDB 语义缓存
    try:
        from agent.memory import AgentMemory
        memory = AgentMemory()
        text = (
            f"行业: {cognition.industry}\n"
            f"产业链: 上游={cognition.upstream}, 下游={cognition.downstream}\n"
            f"核心驱动: {cognition.core_drivers}\n"
            f"供需: {cognition.supply_demand}\n"
            f"认知陷阱: {cognition.common_traps}\n"
            f"周期: {cognition.cycle_position} — {cognition.cycle_reasoning}"
        )
        memory.store(
            agent_role="industry_cognition",
            target=cognition.industry,
            content=text,
            metadata={"industry": cognition.industry, "as_of_date": cognition.as_of_date, "target": cognition.target},
        )
    except Exception as e:
        logger.debug(f"行业认知 ChromaDB 缓存写入失败: {e}")
```

- [ ] **Step 3: 新增 generate_industry_cognition() 异步生成器**

```python
async def generate_industry_cognition(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> AsyncGenerator[dict, None]:
    """生成/检索行业产业链认知，推送 SSE 事件"""
    # 从 facts 中获取行业信息
    stock_info = blackboard.facts.get("get_stock_info", {})
    industry = stock_info.get("industry", "")
    stock_name = stock_info.get("name", blackboard.target)

    if not industry:
        logger.info("未获取到行业信息，跳过行业认知生成")
        return

    # 检查缓存
    cached = _load_cached_cognition(industry, blackboard.as_of_date)
    if cached:
        logger.info(f"行业认知缓存命中: {industry} @ {blackboard.as_of_date}")
        blackboard.industry_cognition = cached
        yield sse("industry_cognition_start", {"industry": industry, "cached": True})
        yield sse("industry_cognition_done", {
            "industry": industry,
            "summary": f"产业链: {' → '.join(cached.upstream[:2])} → [{stock_name}] → {' → '.join(cached.downstream[:2])}",
            "cycle_position": cached.cycle_position,
            "traps_count": len(cached.common_traps),
            "cached": True,
        })
        return

    # LLM 生成
    yield sse("industry_cognition_start", {"industry": industry, "cached": False})

    prompt = INDUSTRY_COGNITION_PROMPT.format(
        industry=industry,
        target=blackboard.code or blackboard.target,
        stock_name=stock_name,
        as_of_date=blackboard.as_of_date,
    )

    try:
        raw = await asyncio.wait_for(
            llm.chat([ChatMessage(role="user", content=prompt)]),
            timeout=30.0,
        )
        parsed = _lenient_json_loads(raw)
        if not isinstance(parsed, dict):
            logger.warning(f"行业认知 LLM 返回非 dict: {type(parsed)}")
            return

        cognition = IndustryCognition(
            industry=industry,
            target=blackboard.code or blackboard.target,
            generated_at=datetime.now(tz=ZoneInfo("Asia/Shanghai")).isoformat(),
            as_of_date=blackboard.as_of_date,
            **{k: v for k, v in parsed.items() if k in IndustryCognition.model_fields},
        )
        blackboard.industry_cognition = cognition

        # 写缓存
        _save_cognition_cache(cognition)

        yield sse("industry_cognition_done", {
            "industry": industry,
            "summary": f"产业链: {' → '.join(cognition.upstream[:2])} → [{stock_name}] → {' → '.join(cognition.downstream[:2])}",
            "cycle_position": cognition.cycle_position,
            "traps_count": len(cognition.common_traps),
            "cached": False,
        })
        logger.info(f"行业认知生成完成: {industry}, 周期={cognition.cycle_position}, 陷阱={len(cognition.common_traps)}条")

    except Exception as e:
        logger.warning(f"行业认知生成失败: {e}")
        yield sse("industry_cognition_done", {
            "industry": industry,
            "summary": f"行业认知生成失败: {e}",
            "cycle_position": "",
            "traps_count": 0,
            "cached": False,
            "error": True,
        })
```

- [ ] **Step 4: 在 debate.py 顶部 import 中添加 IndustryCognition**

在现有的 `from .schemas import ...` 行中追加 `IndustryCognition`。

- [ ] **Step 5: 验证语法**

```bash
cd engine && .venv/bin/python -c "from agent.debate import generate_industry_cognition; print('ok')"
```
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: 新增 generate_industry_cognition() 行业认知生成器 + 缓存读写"
```

---

### Task 4: run_debate 集成行业认知阶段

**Files:**
- Modify: `engine/agent/debate.py`

- [ ] **Step 1: 在 run_debate() 中插入行业认知阶段**

在 `fetch_initial_data` 之后、`while blackboard.round < blackboard.max_rounds` 之前插入：

```python
    # 行业产业链认知
    async for event in generate_industry_cognition(blackboard, llm):
        yield event
```

- [ ] **Step 2: _build_context_for_role 注入行业认知**

在 `_build_context_for_role` 函数中，在时间锚点之后、facts 之前，插入行业认知序列化：

```python
    # 行业底层逻辑
    if blackboard.industry_cognition:
        ic = blackboard.industry_cognition
        parts.append(f"## 行业底层逻辑（{ic.industry}）")
        parts.append(f"\n### 产业链")
        parts.append(f"上游: {', '.join(ic.upstream)}")
        parts.append(f"下游: {', '.join(ic.downstream)}")
        parts.append(f"核心驱动变量: {', '.join(ic.core_drivers)}")
        parts.append(f"\n### 成本结构\n{ic.cost_structure}")
        parts.append(f"\n### 行业壁垒\n{ic.barriers}")
        parts.append(f"\n### 供需格局\n{ic.supply_demand}")
        if ic.common_traps:
            parts.append(f"\n### ⚠ 常见认知陷阱（务必注意）")
            for i, trap in enumerate(ic.common_traps, 1):
                parts.append(f"{i}. {trap}")
        parts.append(f"\n### 周期定位\n{ic.cycle_position}：{ic.cycle_reasoning}")
        if ic.catalysts:
            parts.append(f"\n### 潜在催化剂")
            for c in ic.catalysts:
                parts.append(f"- {c}")
        if ic.risks:
            parts.append(f"\n### 关键风险")
            for r in ic.risks:
                parts.append(f"- {r}")
        parts.append("")  # 空行分隔
```

- [ ] **Step 3: 验证语法**

```bash
cd engine && .venv/bin/python -c "from agent.debate import run_debate, _build_context_for_role; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat: run_debate 集成行业认知阶段，_build_context_for_role 注入行业逻辑"
```

---

### Task 5: Persona Prompt 追加产业链推理指令

**Files:**
- Modify: `engine/agent/personas.py`

- [ ] **Step 1: 在 _DEBATER_SYSTEM_TEMPLATE 末尾追加产业链指令**

在 `_DEBATER_SYSTEM_TEMPLATE` 字符串末尾（闭合引号之前）追加：

```python
\n\n【重要】你必须基于产业链底层逻辑进行推理，不能只看技术面和情绪面。
黑板上的「行业底层逻辑」是你的分析基础，你的论点必须与产业链逻辑一致，或明确说明为什么你的判断与产业链逻辑不同。
特别注意「常见认知陷阱」，避免被表面叙事误导。
```

- [ ] **Step 2: 在 _OBSERVER_SYSTEM_TEMPLATE 末尾追加同样指令**

在 `_OBSERVER_SYSTEM_TEMPLATE` 字符串末尾追加相同的产业链推理指令。

- [ ] **Step 3: 验证**

```bash
cd engine && .venv/bin/python -c "
from agent.personas import build_debate_system_prompt
p = build_debate_system_prompt('bull_expert', '600549', False)
assert '产业链' in p, 'missing 产业链 in prompt'
p2 = build_debate_system_prompt('retail_investor', '600549', False)
assert '认知陷阱' in p2, 'missing 认知陷阱 in observer prompt'
print('ok')
"
```
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add engine/agent/personas.py
git commit -m "feat: 辩论角色 prompt 追加产业链推理指令"
```

---

## Chunk 3: 前端展示

### Task 6: useDebateStore SSE 事件处理

**Files:**
- Modify: `web/stores/useDebateStore.ts`

- [ ] **Step 1: TranscriptItem 新增 industry_cognition 类型**

在 `TranscriptItem` 类型联合中（约第 19 行 `round_eval` 之后）添加：

```typescript
  | { id: string; type: "industry_cognition"; status: "pending" | "done"; industry: string; summary?: string; cycle_position?: string; traps_count?: number; error?: boolean }
```

- [ ] **Step 2: _handleSSEEvent 新增两个 case**

在 `initial_data_complete` case 之前添加：

```typescript
    case "industry_cognition_start": {
      const { industry, cached } = data as { industry: string; cached: boolean };
      set({
        transcript: [
          ...state.transcript,
          { id: `industry_cognition_${industry}`, type: "industry_cognition", status: "pending", industry },
        ],
      });
      break;
    }

    case "industry_cognition_done": {
      const { industry, summary, cycle_position, traps_count, error } = data as {
        industry: string; summary: string; cycle_position: string; traps_count: number; error?: boolean;
      };
      set({
        transcript: state.transcript.map((item) =>
          item.type === "industry_cognition" && item.industry === industry
            ? { ...item, status: "done" as const, summary, cycle_position, traps_count, error }
            : item
        ),
      });
      break;
    }
```

- [ ] **Step 3: Commit**

```bash
cd web && git add stores/useDebateStore.ts
git commit -m "feat: useDebateStore 处理 industry_cognition SSE 事件"
```

---

### Task 7: IndustryCognitionCard 前端组件

**Files:**
- Modify: `web/components/debate/TranscriptFeed.tsx`

- [ ] **Step 1: 在 TranscriptFeed 的 map 中添加 industry_cognition 渲染**

在 `item.type === "blackboard_data"` 判断之后添加：

```tsx
        if (item.type === "industry_cognition") {
          return <IndustryCognitionCard key={item.id} item={item} />;
        }
```

- [ ] **Step 2: 新增 IndustryCognitionCard 组件**

在 `BlackboardCard` 组件之后添加：

```tsx
function IndustryCognitionCard({ item }: { item: Extract<TranscriptItem, { type: "industry_cognition" }> }) {
  const [open, setOpen] = useState(false);
  const isPending = item.status === "pending";

  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[90%] rounded-xl border border-blue-500/20 bg-blue-500/5 text-xs overflow-hidden">
        <button
          onClick={() => !isPending && setOpen(v => !v)}
          className="w-full flex items-center gap-2 px-4 py-2 text-left text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
          disabled={isPending}
        >
          {isPending
            ? <Loader2 size={12} className="animate-spin shrink-0" />
            : open ? <ChevronUp size={12} /> : <ChevronDown size={12} />
          }
          <span className="text-blue-400 font-medium">
            {isPending ? `正在分析 ${item.industry} 行业逻辑...` : `行业认知 · ${item.industry}`}
          </span>
          {!isPending && item.cycle_position && (
            <span className="ml-auto flex items-center gap-2">
              <span className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">{item.cycle_position}</span>
              {item.traps_count !== undefined && item.traps_count > 0 && (
                <span className="text-yellow-500">⚠ {item.traps_count} 个陷阱</span>
              )}
            </span>
          )}
        </button>
        {open && item.summary && (
          <div className="px-4 pb-3 border-t border-blue-500/10 pt-2">
            <p className="text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">{item.summary}</p>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd web && npx tsc --noEmit 2>&1 | head -20
```
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
cd web && git add components/debate/TranscriptFeed.tsx
git commit -m "feat: TranscriptFeed 新增 IndustryCognitionCard 行业认知卡片"
```

---

## Chunk 4: 端到端验证

### Task 8: 冒烟测试

- [ ] **Step 1: 重启后端**

```bash
lsof -ti:8000 | xargs kill 2>/dev/null; sleep 2
cd engine && nohup .venv/bin/python main.py > /tmp/stockterrain_backend.log 2>&1 &
sleep 3 && lsof -ti:8000 && echo "running"
```

- [ ] **Step 2: 验证行业认知生成**

```bash
curl -s -N -X POST http://localhost:8000/api/v1/debate \
  -H 'Content-Type: application/json' \
  -d '{"code":"600549","max_rounds":1}' 2>&1 | grep -E "industry_cognition" | head -5
```
Expected: 看到 `industry_cognition_start` 和 `industry_cognition_done` 事件

- [ ] **Step 3: 验证缓存命中**

再次发起同一股票辩论，确认 `cached: true`：

```bash
curl -s -N -X POST http://localhost:8000/api/v1/debate \
  -H 'Content-Type: application/json' \
  -d '{"code":"600549","max_rounds":1}' 2>&1 | grep "industry_cognition_start"
```
Expected: `"cached": true`

- [ ] **Step 4: 验证前端编译**

```bash
cd web && npx tsc --noEmit 2>&1 | grep -E "error|Error" | head -10
```
Expected: 无输出

- [ ] **Step 5: 最终 commit**

```bash
git add -A && git status
```
确认无遗漏文件，如有则 commit。
