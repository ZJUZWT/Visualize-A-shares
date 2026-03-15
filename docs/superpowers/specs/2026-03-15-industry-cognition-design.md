# 辩论系统行业认知层设计

## 背景与动机

当前辩论系统的专家只能看到个股维度的数据（K 线、财务、新闻），缺少行业底层运行逻辑。这导致专家容易被表面叙事误导——比如 DeepSeek 发布时市场认为"小模型减少算力需求"从而看空英伟达，但从产业链逻辑看，小模型推理量爆发反而增加算力需求。

辩论需要的不是"行业板块辩论"功能，而是**每次辩论都应该具备产业链认知**，无论讨论的是单只股票还是行业方向。

## 目标

1. 辩论启动时自动生成/检索目标股票所在行业的产业链认知
2. 认知内容注入黑板，所有专家共享
3. 专家 prompt 强制要求基于产业逻辑推理
4. 认知结果缓存复用，同一交易日内同行业不重复生成
5. 前端展示行业认知卡片（可折叠，生成中显示 loading）

## 非目标

- 不做独立的行业板块辩论模式（后续 Roadmap）
- 不构建独立的 IndustryEngine（后续 Roadmap，见 memory）
- 不接入行业级实时数据源（板块行情、行业资金流向等）

## 架构

### 辩论流程变更

```
resolve_stock_code
  → resolve_as_of_date
  → [NEW] generate_industry_cognition   ← 新增阶段
  → fetch_initial_data
  → debate rounds
```

### 核心组件

1. **`generate_industry_cognition()`** — 异步生成器，位于 `engine/agent/debate.py`
   - 输入：`blackboard`（含 code、行业信息、as_of_date）、`llm`
   - 流程：查缓存 → 未命中则 LLM 生成 → 写缓存 → 注入 blackboard
   - 输出：SSE 事件 `industry_cognition_start` / `industry_cognition_done`

2. **`IndustryCognition` 数据模型** — 位于 `engine/agent/schemas.py`

3. **缓存层** — DuckDB 结构化 + ChromaDB 非结构化

<!-- PLACEHOLDER_SECTION_2 -->

## 数据模型

### IndustryCognition

```python
class IndustryCognition(BaseModel):
    industry: str                    # 行业名称（如"小金属"、"半导体"）
    target: str                      # 触发股票代码

    # 产业链结构
    upstream: list[str]              # 上游（原材料/供应商）
    downstream: list[str]            # 下游（客户/应用场景）
    core_drivers: list[str]          # 核心驱动变量（如"钨精矿价格"、"算力需求"）
    cost_structure: str              # 成本结构描述
    barriers: str                    # 行业壁垒

    # 供需格局
    supply_demand: str               # 当前供需格局分析

    # 认知陷阱
    common_traps: list[str]          # 市场常见认知陷阱

    # 周期定位
    cycle_position: str              # 当前行业周期位置（景气上行/下行/拐点）
    cycle_reasoning: str             # 周期判断依据

    # 关键催化剂/风险
    catalysts: list[str]             # 潜在催化剂
    risks: list[str]                 # 关键风险

    # 元数据
    generated_at: str                # 生成时间
    as_of_date: str                  # 基于的时间锚点
```

### Blackboard 扩展

```python
class Blackboard(BaseModel):
    # ... 现有字段 ...
    industry_cognition: IndustryCognition | None = None  # 行业认知（新增）
```

### TranscriptItem 扩展

```typescript
| { id: string; type: "industry_cognition"; status: "pending" | "done"; industry: string; summary?: string }
```

## 缓存策略

### DuckDB 表：`shared.industry_cognition`

```sql
CREATE TABLE IF NOT EXISTS shared.industry_cognition (
    industry    VARCHAR NOT NULL,
    as_of_date  VARCHAR NOT NULL,
    cognition_json TEXT NOT NULL,    -- IndustryCognition 序列化 JSON
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (industry, as_of_date)
);
```

- 精确匹配 `(industry, as_of_date)`，同一交易日内复用
- 跨交易日不复用（周期定位可能变化）

### ChromaDB 集合：`industry_cognition`

- document：完整认知文本（产业链 + 陷阱 + 周期定位拼接）
- metadata：`{ industry, as_of_date, target }`
- 用途：语义检索，支持跨行业关联查询（如搜"算力需求"命中半导体）

### 命中逻辑

```
1. 查 DuckDB: SELECT cognition_json FROM shared.industry_cognition
              WHERE industry = ? AND as_of_date = ?
2. 命中 → 反序列化为 IndustryCognition，跳过 LLM
3. 未命中 → LLM 生成 → 写入 DuckDB + ChromaDB → 返回
```

## LLM 生成 Prompt

```
你是产业链分析专家。请基于你对 {industry} 行业的深度理解，生成以下结构化分析。
当前讨论标的：{target}（{stock_name}），时间基准：{as_of_date}。

请以 JSON 格式返回：
{
  "upstream": ["上游环节1", "上游环节2"],
  "downstream": ["下游应用1", "下游应用2"],
  "core_drivers": ["核心驱动变量1 — 简要说明", ...],
  "cost_structure": "成本结构描述（原材料占比、人工、能源等）",
  "barriers": "行业壁垒（资源、技术、资质、规模等）",
  "supply_demand": "当前供需格局分析（供给端变化、需求端趋势、库存状态）",
  "common_traps": [
    "认知陷阱1 — 为什么这个直觉判断是错的",
    "认知陷阱2 — ..."
  ],
  "cycle_position": "景气上行 | 景气下行 | 拐点向上 | 拐点向下 | 高位震荡 | 底部盘整",
  "cycle_reasoning": "周期判断的具体依据",
  "catalysts": ["潜在催化剂1", ...],
  "risks": ["关键风险1", ...]
}

要求：
- common_traps 是最关键的部分，必须列出该行业中投资者最容易犯的认知错误
- 每个陷阱要说明「表面逻辑」和「实际逻辑」的差异
- cycle_position 必须给出明确判断，不能模棱两可
- 所有分析基于 {as_of_date} 时点的行业状态
```

## 上下文注入

### _build_context_for_role 变更

在 facts 之前注入行业认知：

```
## 行业底层逻辑（{industry}）

### 产业链
上游：{upstream}
下游：{downstream}
核心驱动变量：{core_drivers}

### 成本结构
{cost_structure}

### 行业壁垒
{barriers}

### 供需格局
{supply_demand}

### ⚠ 常见认知陷阱
{common_traps}  ← 逐条列出

### 周期定位
{cycle_position}：{cycle_reasoning}

### 催化剂与风险
催化剂：{catalysts}
风险：{risks}
```

### Persona System Prompt 追加

在 bull_expert、bear_expert、retail_investor、smart_money 的 system prompt 末尾追加：

```
【重要】你必须基于产业链底层逻辑进行推理，不能只看技术面和情绪面。
黑板上的「行业底层逻辑」是你的分析基础，你的论点必须与产业链逻辑一致，
或明确说明为什么你的判断与产业链逻辑不同。
特别注意「常见认知陷阱」，避免被表面叙事误导。
```

## SSE 事件

### industry_cognition_start

```json
{
  "event": "industry_cognition_start",
  "data": { "industry": "小金属", "cached": false }
}
```

### industry_cognition_done

```json
{
  "event": "industry_cognition_done",
  "data": {
    "industry": "小金属",
    "summary": "钨产业链：上游钨精矿→中游APT/氧化钨→下游硬质合金/军工...",
    "cycle_position": "高位震荡",
    "traps_count": 3,
    "cached": false
  }
}
```

## 前端变更

### useDebateStore

- `_handleSSEEvent` 新增 `industry_cognition_start` / `industry_cognition_done` 处理
- `TranscriptItem` 新增 `type: "industry_cognition"` 变体
- `industry_cognition_start` → 插入 pending 状态的 transcript item
- `industry_cognition_done` → 更新为 done 状态，附带 summary 和完整数据

### TranscriptFeed

新增 `IndustryCognitionCard` 组件：
- pending 状态：显示 Loader2 圈 + "正在分析 {industry} 行业逻辑..."
- done 状态：可折叠卡片
  - 折叠态：行业名 + 周期定位标签 + 陷阱数量
  - 展开态：产业链、供需、陷阱、周期定位等分区展示
- 样式：紫色/蓝色边框区分于其他卡片类型，表示这是"认知层"而非"数据层"

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `engine/agent/schemas.py` | 新增 `IndustryCognition` 模型，`Blackboard` 新增字段 |
| `engine/agent/debate.py` | 新增 `generate_industry_cognition()` 生成器，`_build_context_for_role` 注入行业认知，`run_debate` 调用新阶段 |
| `engine/agent/personas.py` | 四个辩论角色 system prompt 追加产业链推理指令 |
| `web/stores/useDebateStore.ts` | `TranscriptItem` 新增类型，SSE 事件处理 |
| `web/components/debate/TranscriptFeed.tsx` | 新增 `IndustryCognitionCard` 组件 |
| `web/types/debate.ts` | 新增 `IndustryCognition` TypeScript 类型（可选） |
