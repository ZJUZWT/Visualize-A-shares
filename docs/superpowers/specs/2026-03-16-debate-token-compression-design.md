# 辩论 Token 压缩 — 双模式设计

## 目标

为辩论系统增加「标准/快速」双模式切换，快速模式通过 LLM 预压缩初始数据，大幅减少后续每次 LLM 调用的 context 大小。

## 现状分析

一次 3 轮辩论约 33 次 LLM 调用，其中 16 次注入完整 blackboard context。`_build_context_for_role` 每次注入：
- 20 条日线全量数据
- 全部新闻（标题+内容+情感）
- 行业认知完整结构（产业链、供需、陷阱等）
- 所有历史发言（随轮次线性增长）
- 所有补充数据（无截断）

## 方案：单次 LLM 预压缩

在 `fetch_initial_data` + `generate_industry_cognition` 之后、辩论主循环之前，增加一次 LLM 调用，将全量 facts + 行业认知压缩为结构化摘要（约 500-800 字）。后续所有角色的 context 注入使用摘要替代原始数据。

### 压缩范围

| 数据 | 标准模式 | 快速模式 |
|------|---------|---------|
| 日线（20条） | 全量 | 压缩为关键统计（区间涨跌、均价、放量日、支撑/压力位） |
| 新闻 | 全量（标题+内容+情感） | 压缩为事件摘要（关键事件+整体情感倾向） |
| 股票基本信息 | 全量 | 保留（本身很小） |
| 行业认知 | 全量 | 压缩为核心驱动+陷阱+周期定位（去掉上下游细节、成本结构等） |
| 历史发言 | 全量 | 全量（不压缩，保持辩论连贯性） |
| 补充数据 | 全量 | 全量（专家主动请求的数据不压缩） |

### 预估收益

- 预压缩调用：+1 次 LLM 调用（约 10-15s）
- 每次 context 注入：从 ~4000 tokens 降到 ~1500 tokens
- 3 轮辩论总计：省约 40k input tokens（16 次调用 × 2500 tokens 节省）
- 辩论总时长：因 context 更小，每次 LLM 响应更快，整体可能更快

## 数据流

```
fetch_initial_data → blackboard.facts (全量)
                   ↓
generate_industry_cognition → blackboard.industry_cognition (全量)
                   ↓
[快速模式] compress_facts() → blackboard.facts_summary (摘要字符串)
                   ↓
_build_context_for_role:
  标准模式 → 注入 facts + industry_cognition 全量
  快速模式 → 注入 facts_summary
                   ↓
speak_stream / judge_summarize / ...
```

## 接口变更

### API

`POST /api/v1/debate` 请求体新增：
```json
{
  "code": "600519",
  "max_rounds": 3,
  "mode": "standard"  // "standard" | "fast"，默认 "standard"
}
```

### SSE 事件

新增两个事件（仅快速模式触发）：
- `facts_compression_start`: `{ "mode": "fast" }`
- `facts_compression_done`: `{ "original_tokens_est": 4000, "compressed_tokens_est": 1200, "compression_ratio": 0.3 }`

### 数据模型

`Blackboard` 新增：
```python
mode: Literal["standard", "fast"] = "standard"
facts_summary: str | None = None  # 快速模式下的压缩摘要
```

## 后端实现

### 新增 `compress_facts()` 函数

位置：`engine/agent/debate.py`

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

在 `run_debate()` 中 `generate_industry_cognition` 之后：
```python
if blackboard.mode == "fast":
    async for event in compress_facts(blackboard, llm):
        yield event
```

### 修改 `_build_context_for_role()`

```python
def _build_context_for_role(blackboard: Blackboard) -> str:
    parts = []
    # 时间锚点（不变）
    ...

    if blackboard.mode == "fast" and blackboard.facts_summary:
        # 快速模式：用压缩摘要替代 facts + industry_cognition
        parts.append("## 市场数据摘要（压缩版）")
        parts.append(blackboard.facts_summary)
    else:
        # 标准模式：原有逻辑不变
        # 行业认知全量注入
        ...
        # facts 全量注入
        ...

    # 以下不变：worker verdicts, transcript, 补充数据
    ...
```

## 前端实现

### InputBar 新增模式切换

在轮次选择器旁边加一个切换按钮：

```tsx
<button
  onClick={() => setMode(m => m === "standard" ? "fast" : "standard")}
  className="h-10 px-3 rounded-lg text-xs ..."
>
  {mode === "fast" ? "⚡ 快速" : "📊 标准"}
</button>
```

### useDebateStore

- `startDebate` 签名变更：`(code: string, maxRounds: number, mode: string)`
- `TranscriptItem` 新增 `facts_compression` 类型
- 处理 `facts_compression_start/done` SSE 事件

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `engine/agent/schemas.py` | Blackboard 新增 `mode`, `facts_summary` 字段 |
| `engine/agent/debate.py` | 新增 `compress_facts()`，修改 `_build_context_for_role()` 和 `run_debate()` |
| `engine/api/routes/debate.py` | DebateRequest 新增 `mode` 字段，传入 Blackboard |
| `web/stores/useDebateStore.ts` | startDebate 新增 mode 参数，新增 SSE 事件处理 |
| `web/components/debate/InputBar.tsx` | 新增模式切换按钮 |
| `web/components/debate/TranscriptFeed.tsx` | 新增 FactsCompressionCard 组件 |

## 不做的事

- 不压缩历史发言（保持辩论连贯性）
- 不压缩专家补充数据（专家主动请求的数据应完整呈现）
- 不减少 LLM 调用次数（保留所有环节：数据请求、发言、结构提取、评委小评）
- 不做连续可调的压缩级别（YAGNI）
