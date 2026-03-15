# 投资专家 Agent 设计文档

**日期:** 2026-03-15
**状态:** 待实现
**目标:** 构建一个有持久世界观、能被用户说服、会主动查资料的投资专家 Agent，以 GraphRAG 知识图谱驱动认知。

---

## 1. 背景与目标

现有系统已有辩论专家（bull/bear/judge）和 ChromaDB 向量记忆，但这些专家是无状态的——每次辩论结束后不会真正"成长"。

本设计引入一个**持续存在的投资专家**，特点：
- 有自己的投资哲学（初始为 general 风格，偏理性、多元视角）
- 通过逻辑推理被用户说服后，真正更新世界观
- 对话中发现信息缺口时主动调用引擎查资料
- 知识图谱记录他的认知演化历史，不删除旧信念，只追加更新边

这是项目引入 GraphRAG 的第一步，后续可将此模式推广到辩论系统。

---

## 2. 系统架构

```
用户对话 (HTTP POST /api/v1/expert/chat, SSE 流式)
    ↓
ExpertAgent
    ├── 图谱召回 (KnowledgeGraph)
    ├── 记忆召回 (ChromaDB AgentMemory)
    ├── 思考决策 (LLM)
    ├── 工具调用 (DataFetcher / QuantEngine / ClusterEngine)
    ├── 流式回复 (SSE)
    └── 认知更新 (KnowledgeGraph 写回)

KnowledgeGraph
    ├── 存储: NetworkX 内存图 + JSON 持久化
    └── 路径: data/expert_knowledge_graph.json

AgentMemory (已有 ChromaDB)
    └── collection: memory_expert

DataFetcher / QuantEngine / ClusterEngine (已有)
```

**新增模块:** `engine/expert/`，独立于现有 `engine/agent/`，共享 LLM、DataFetcher。

---

## 3. 知识图谱设计

### 3.1 节点类型

| 类型 | 字段 | 说明 |
|------|------|------|
| `stock` | code, name | 股票，如 300750 宁德时代 |
| `sector` | name | 行业板块，如 新能源 |
| `event` | name, date, description | 市场事件，如 储能补贴政策 2024Q3 |
| `belief` | content, confidence, created_at | 专家信念，如 "政策驱动比基本面更重要" |
| `stance` | target, signal, score, confidence, created_at | 对某标的的看法 |

### 3.2 边类型

| 关系 | 方向 | 说明 |
|------|------|------|
| `belongs_to` | stock → sector | 股票属于板块 |
| `influenced_by` | stance → event | 看法受某事件影响 |
| `supports` | event → belief | 事件支持某信念 |
| `contradicts` | node → belief | 与信念矛盾 |
| `updated_by` | old_belief → new_belief | 被说服后的认知更新，保留历史 |
| `researched` | expert → stock/event | 专家主动研究过的节点 |

### 3.3 认知更新规则

- 旧信念节点**永不删除**，加 `updated_by` 边指向新节点
- 每条 `updated_by` 边记录 `reason`（被什么论据说服）和 `timestamp`
- 图谱变更后触发 `belief_updated` SSE 事件通知前端

---

## 4. ExpertAgent 对话流程

每次用户发消息，走以下流程：

```
1. graph_recall   — 从图谱找与消息相关的节点（股票/信念/事件）
2. memory_recall  — ChromaDB 召回相关历史对话（top_k=5）
3. think          — LLM 判断：是否需要查数据？调哪个引擎？（见 4.3）
4. tool_calls     — 按需调用引擎（可多次，串行）
5. reply_stream   — 流式生成回复
6. belief_update  — 对话结束后，LLM 判断图谱是否需要更新（见 4.4）
7. memory_store   — 将本轮对话摘要存入 ChromaDB（agent_role="expert"）
```

### 4.1 工具调用能力

专家可调用的引擎：

| 工具 | 能力 |
|------|------|
| `data.get_daily_history` | 日线行情 |
| `data.get_company_profile` | 公司概况 |
| `quant.get_factor_scores` | 多因子评分 |
| `quant.get_technical_indicators` | 技术指标 |
| `cluster.get_terrain_data` | 聚类地形 |
| `debate.start` | 触发专家辩论（深度分析时，见 4.5） |

### 4.2 专家初始人格

General 风格，写入初始图谱节点：

```json
{
  "beliefs": [
    {"content": "基本面是长期定价的锚，但短期价格由情绪和资金驱动", "confidence": 0.7},
    {"content": "分散投资优于集中押注，除非有极高确定性", "confidence": 0.65},
    {"content": "政策是A股不可忽视的系统性变量", "confidence": 0.75},
    {"content": "散户情绪是反向指标，极度乐观时需警惕", "confidence": 0.6}
  ]
}
```

### 4.3 think 步骤：LLM 输出契约

`think` 步骤向 LLM 发送系统 prompt + 用户消息 + 图谱召回上下文，要求返回如下 JSON：

```json
{
  "needs_data": true,
  "tool_calls": [
    {"engine": "data", "action": "get_daily_history", "params": {"code": "300750", "days": 30}},
    {"engine": "quant", "action": "get_factor_scores", "params": {"code": "300750"}}
  ],
  "reasoning": "用户问宁德时代近期走势，需要日线数据和因子评分才能回答"
}
```

- `needs_data: false` 时 `tool_calls` 为空，直接进入 `reply_stream`
- `tool_calls` 按顺序串行执行，每次执行前后各推送 `tool_call` / `tool_result` SSE 事件
- LLM 解析失败时降级为 `needs_data: false`，直接回复

### 4.4 belief_update 步骤：触发条件与输出契约

`reply_stream` 完成后，向 LLM 发送本轮完整对话（用户消息 + 专家回复），要求判断是否有信念需要更新：

```json
{
  "updated": true,
  "changes": [
    {
      "old_belief_id": "belief_uuid_xxx",
      "new_content": "政策是A股最重要的系统性变量，权重高于基本面",
      "new_confidence": 0.85,
      "reason": "用户提供了2024年多个政策驱动行情的案例，逻辑充分"
    }
  ]
}
```

- `updated: false` 时跳过图谱写入
- `old_belief_id` 对应图谱中现有 belief 节点的 UUID
- 旧节点保留，新建节点，加 `updated_by` 边（含 `reason` 和 `timestamp`）
- 触发 `belief_updated` SSE 事件，`old`/`new` 字段为完整节点对象 `{id, content, confidence}`

### 4.5 debate.start 工具接口

`debate.start` 在 `tools.py` 中封装为：

```python
async def start_debate(code: str, max_rounds: int = 2) -> str:
    """触发专家辩论，消费完整 SSE 流，返回裁判裁决摘要文本"""
```

- 调用 `POST /api/v1/debate`（已有端点），消费 SSE 流
- 只返回最终 `judge_verdict` 的 `summary` 字段作为工具结果
- 辩论过程的 SSE 事件不透传给前端（避免嵌套流复杂度），只在 `tool_result` 中返回摘要

---

## 5. SSE 事件协议

**前端消费方式：** `POST /api/v1/expert/chat` 返回 SSE 流，前端必须使用 `fetch()` + `ReadableStream` 手动解析，不能使用浏览器原生 `EventSource`（仅支持 GET）。现有辩论页已采用相同模式。

| 事件 | data 字段 | 说明 |
|------|-----------|------|
| `thinking_start` | `{}` | 开始思考 |
| `graph_recall` | `{nodes: [{id, type, label, confidence?}]}` | 召回的图谱节点列表 |
| `tool_call` | `{engine, action, params}` | 调用引擎 |
| `tool_result` | `{engine, action, summary}` | 引擎返回摘要（截断至200字） |
| `reply_token` | `{token, seq}` | 流式回复 token |
| `reply_complete` | `{full_text}` | 回复完整文本 |
| `belief_updated` | `{old: {id, content, confidence}, new: {id, content, confidence}, reason}` | 图谱信念更新 |
| `error` | `{message}` | 错误 |

`graph_recall` 节点对象字段：`id`（UUID）、`type`（stock/sector/event/belief/stance）、`label`（显示名）、`confidence`（仅 belief/stance 有）。

---

## 6. 后端文件结构

```
engine/expert/
    __init__.py
    agent.py           # ExpertAgent 主类，对话流程
    knowledge_graph.py # KnowledgeGraph，NetworkX + JSON 持久化（asyncio.Lock 保护写操作）
    tools.py           # 工具调用适配层（封装各引擎调用）
    schemas.py         # 数据结构（Node, Edge, BeliefUpdate 等）
    personas.py        # 初始人格定义
    routes.py          # FastAPI 路由 /api/v1/expert/*
```

**路由注册：** `engine/main.py` 中添加：
```python
from expert.routes import router as expert_router
app.include_router(expert_router)
```

**并发安全：** `KnowledgeGraph` 内部持有一个模块级 `asyncio.Lock`，所有图谱写操作（`add_node`、`add_edge`、`update_belief`、`save`）必须在 lock 内执行。读操作不加锁。

**API 端点：**

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/expert/chat` | 发消息，SSE 流式返回 |
| `GET` | `/api/v1/expert/graph` | 返回当前知识图谱（JSON） |
| `GET` | `/api/v1/expert/beliefs` | 返回当前信念列表（仅最新版本） |
| `GET` | `/api/v1/expert/history` | 返回对话历史摘要（从 DuckDB `expert.conversation_log` 表读取，按时间倒序） |

**对话历史持久化：** 每轮对话结束后写入 DuckDB `expert.conversation_log` 表（与 `shared.debate_records` 同库），字段：`id`、`user_message`、`expert_reply`、`belief_changes`（JSON）、`tools_used`（JSON）、`created_at`。ChromaDB 仅用于语义召回，DuckDB 用于有序历史展示。

---

## 7. 前端文件结构

```
web/app/expert/
    page.tsx          # 主页面

web/components/expert/
    ChatArea.tsx      # 聊天区，渲染消息列表
    MessageBubble.tsx # 单条消息，含折叠思考面板
    ThinkingPanel.tsx # 思考过程展示（graph_recall/tool_call/belief_updated）
    InputBar.tsx      # 输入框 + 发送按钮

web/store/expertStore.ts  # Zustand store，管理消息列表和 SSE 状态
```

**页面布局：**
```
┌─────────────────────────────────────────────┐
│  顶部栏: "投资专家"  +  状态指示灯            │
├─────────────────────────────────────────────┤
│                                             │
│  聊天区（主体，flex-col，overflow-y-auto）   │
│                                             │
│  ┌─ 专家消息 ──────────────────────────┐   │
│  │ [▶ 思考过程]  ← 默认折叠            │   │
│  │ 正文回复内容（流式渲染）             │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  ┌─ 用户消息 ──────────────────────────┐   │
│  │ 你说的内容                          │   │
│  └─────────────────────────────────────┘   │
│                                             │
├─────────────────────────────────────────────┤
│  输入框（多行）                    [发送]    │
└─────────────────────────────────────────────┘
```

思考面板展开后显示：
- 📊 图谱召回的节点
- 🔧 调用的引擎和参数
- ✅ 引擎返回摘要
- 🧠 信念更新（如有）

---

## 8. 依赖

新增（添加到 `engine/pyproject.toml` 的 `dependencies` 列表）：
- `networkx>=3.0` — 图结构存储与遍历

已有（复用）：
- `chromadb` — 对话记忆语义召回
- `duckdb` — 对话历史持久化
- `httpx` — 引擎调用
- `fastapi` + `loguru` — 后端框架
- `pydantic` — 数据结构

---

## 9. 实现顺序

1. `knowledge_graph.py` + `schemas.py` — 图谱核心，可独立测试
2. `tools.py` — 引擎调用适配层
3. `agent.py` — 对话流程（依赖 1+2）
4. `routes.py` — API 端点（依赖 3）
5. 前端 `expertStore.ts` + `ChatArea` + `MessageBubble` + `ThinkingPanel`
6. 前端 `InputBar` + `page.tsx` 组装

---

## 10. 不在本期范围内

- 专家主动推送（用户未发消息时专家主动找你）
- 多专家对话（本期只有一个专家）
- 图谱可视化界面
- 专家人格切换
