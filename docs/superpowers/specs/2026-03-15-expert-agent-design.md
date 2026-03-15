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
3. think          — LLM 判断：是否需要查数据？调哪个引擎？
4. tool_calls     — 按需调用引擎（可多次，串行）
5. reply_stream   — 流式生成回复
6. belief_update  — 对话结束后，LLM 判断图谱是否需要更新
7. memory_store   — 将本轮对话摘要存入 ChromaDB
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
| `debate.start` | 触发专家辩论（深度分析时） |

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

---

## 5. SSE 事件协议

| 事件 | data 字段 | 说明 |
|------|-----------|------|
| `thinking_start` | `{}` | 开始思考 |
| `graph_recall` | `{nodes: [...]}` | 召回的图谱节点列表 |
| `tool_call` | `{engine, action, params}` | 调用引擎 |
| `tool_result` | `{engine, action, summary}` | 引擎返回摘要 |
| `reply_token` | `{token, seq}` | 流式回复 token |
| `reply_complete` | `{full_text}` | 回复完整文本 |
| `belief_updated` | `{old, new, reason}` | 图谱信念更新 |
| `error` | `{message}` | 错误 |

---

## 6. 后端文件结构

```
engine/expert/
    __init__.py
    agent.py          # ExpertAgent 主类，对话流程
    knowledge_graph.py # KnowledgeGraph，NetworkX + JSON 持久化
    tools.py          # 工具调用适配层（封装各引擎调用）
    schemas.py        # 数据结构（Node, Edge, BeliefUpdate 等）
    personas.py       # 初始人格定义
    routes.py         # FastAPI 路由 /api/v1/expert/*

engine/api/routes/expert.py  # 路由注册（或直接在 expert/routes.py）
```

**API 端点：**

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/expert/chat` | 发消息，SSE 流式返回 |
| `GET` | `/api/v1/expert/graph` | 返回当前知识图谱（JSON） |
| `GET` | `/api/v1/expert/beliefs` | 返回当前信念列表 |
| `GET` | `/api/v1/expert/history` | 返回对话历史摘要 |

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

新增：
- `networkx>=3.0` — 图结构存储与遍历

已有（复用）：
- `chromadb` — 对话记忆
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
