# 裁判 RAG 化 + 题目预分析 设计文档

## 目标

将辩论系统的裁判从普通 LLM agent 升级为基于 ExpertAgent 的 RAG 裁判，同时新增辩论前题目预分析阶段。核心目的：让辩论系统成为知识图谱的又一个强化入口，每场辩论都丰富共享知识。

## 背景

当前裁判是独立的 LLM 调用（`judge_round_eval` + `judge_summarize_stream`），只读 blackboard 上下文，没有外部知识检索能力。ExpertAgent 已有完整的 GraphRAG 能力（知识图谱召回、工具调用、信念更新），但只在专家聊天页面使用。

## 架构

### 核心原则

- **共享单例**：JudgeRAG 使用 `main.py` 中初始化的全局 ExpertAgent 实例，共享同一个 KnowledgeGraph 和 ChromaDB memory
- **薄编排层**：JudgeRAG 不复制 ExpertAgent 逻辑，只组合调用其公开方法，控制"走哪几步"
- **分级调用**：预分析和最终裁决走完整流程（含工具调用），每轮小评只走轻量路径（recall + LLM）

### 并发安全

ExpertAgent 和 KnowledgeGraph 各有 `asyncio.Lock` 保护写操作。由于 asyncio 是单线程事件循环，锁保证了正确性。当用户同时在专家聊天页面和辩论页面操作时，写操作会串行化，可能有数秒延迟但不会数据损坏。`KnowledgeGraph.save()` 同样受锁保护，不会出现并发写文件问题。

### 系统流程

```
用户输入题目
    ↓
┌─────────────────────────────────┐
│  题目预分析（ExpertAgent 完整流程）  │
│  graph_recall → think → tools    │
│  → reply → learn                 │
│  输出: topic_briefing            │
└─────────────────────────────────┘
    ↓
blackboard.facts["topic_briefing"] = briefing
    ↓
┌─────────────────────────────────┐
│  辩论主循环（每轮）               │
│  ├─ 多头发言                     │
│  ├─ 空头发言                     │
│  ├─ 观察员发言                   │
│  ├─ 数据请求 & 履行              │
│  └─ 每轮小评（JudgeRAG 轻量）    │
│     graph_recall → LLM → RoundEval│
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  最终裁决（ExpertAgent 完整流程）  │
│  graph_recall → think → tools    │
│  → reply → learn → belief_update │
│  输出: JudgeVerdict              │
└─────────────────────────────────┘
```

## 组件设计

### 1. ExpertAgent 公开方法扩展

在 `engine/expert/agent.py` 的 `ExpertAgent` 类上新增组合方法，供 JudgeRAG 调用：

```python
async def recall_and_think(self, query: str, history: list[dict] | None = None) -> tuple[list[dict], list[dict], ThinkOutput]:
    """图谱召回 + 记忆召回 + think，不执行工具
    Returns: (recalled_nodes, memories, think_output)
    内部调用 _graph.recall() + _memory.recall() + _think()，继承 _think 的多层容错解析
    """

async def execute_tools(self, tool_calls: list[ToolCall]) -> list[dict]:
    """并行执行工具调用，返回 tool_results"""

async def learn_from_context(self, message: str, tool_results: list[dict]) -> None:
    """图谱自动学习 — 从对话和工具结果中提取股票/板块/产业链节点
    注意：此方法在 reply 之前调用（与 chat() 流程一致）
    """

async def generate_reply_stream(
    self, message: str, nodes: list[dict], memories: list[dict],
    tool_results: list[dict], history: list[dict] | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """流式生成回复，yield (token, full_text)"""

async def belief_update(self, message: str, reply: str) -> list[dict]:
    """信念更新 — 根据对话结论更新 BeliefNode confidence
    注意：此方法在 reply 之后调用（与 chat() 流程一致）
    返回更新事件列表 [{event: "belief_updated", data: {...}}]
    """
```

这些方法严格对应 `chat()` 的步骤顺序：recall_and_think → execute_tools → learn_from_context → generate_reply_stream → belief_update。`chat()` 方法本身可重构为调用这些公开方法的组合。

### 2. JudgeRAG 模块

新建 `engine/agent/judge.py`：

```python
class JudgeRAG:
    """RAG 裁判 — 基于 ExpertAgent 的辩论裁判"""

    def __init__(self, expert: ExpertAgent):
        self._expert = expert  # 全局单例，共享知识图谱

    async def analyze_topic(self, topic: str) -> AsyncGenerator[dict, None]:
        """预分析辩论题目

        完整 ExpertAgent 流程：recall → think → tools → reply → learn
        yield SSE 事件：topic_analysis_start, judge_graph_recall,
                       judge_tool_call, judge_tool_result, topic_analysis_complete
        返回 briefing dict 写入 blackboard.facts["topic_briefing"]
        """

    async def round_eval(self, round_num: int, blackboard: Blackboard) -> RoundEval:
        """每轮小评 — 轻量级

        只走 recall + LLM：
        1. 构造 recall query = 本轮 bull + bear argument 拼接（截断到 500 字）
        2. graph_recall(query) → 召回相关知识节点
        3. LLM 评估（prompt 中注入图谱上下文 + 本轮发言 + 观察员信息）→ RoundEval
        不调工具，不学习，不更新信念（快速）

        RoundEval schema 不变，评分逻辑不变。
        失败时 fallback：使用辩手自报 confidence 构造默认 RoundEval（与现有行为一致）
        """

    async def final_verdict_stream(self, blackboard: Blackboard) -> AsyncGenerator[dict, None]:
        """最终裁决 — 完整 ExpertAgent 流程

        recall → think → tools → reply → learn → belief_update
        yield SSE 事件：judge_token, judge_graph_recall, judge_tool_call,
                       judge_tool_result, judge_verdict
        图谱自动学习辩论结论，信念更新
        """
```

### 3. debate.py 改动

**函数签名变更：**
```python
# 之前
async def run_debate(blackboard, llm, data_fetcher, memory) -> AsyncGenerator:

# 之后
async def run_debate(blackboard, llm, data_fetcher, memory, judge: JudgeRAG | None = None) -> AsyncGenerator:
```

**流程变更：**
- 当 `judge` 不为 None 时，使用 RAG 路径：
  - 预分析：`judge.analyze_topic(blackboard.target)`
  - 每轮小评：`judge.round_eval()`
  - 最终裁决：`judge.final_verdict_stream()`
- 当 `judge` 为 None 时，回退到现有路径：
  - 无预分析
  - 每轮小评：`judge_round_eval()`（现有函数）
  - 最终裁决：`judge_summarize_stream()`（现有函数）
- 旧的 `judge_round_eval()`、`judge_summarize_stream()` 保留为 fallback，不删除
- `JUDGE_SYSTEM_PROMPT`、`JUDGE_ROUND_EVAL_PROMPT` 同理保留

**保留不变：**
- 辩论主循环结构（多头→空头→观察员→数据请求→小评）
- `speak_stream()`、`extract_structure()` 等辩手逻辑
- `RoundEval`、`JudgeVerdict` schema 不变
- 数据驱动 score 计算逻辑（`calculated_score * 0.7 + llm_score * 0.3`）

### 4. API 路由改动

`engine/api/routes/debate.py`（辩论路由）：

- `run_debate()` 调用时传入 `JudgeRAG` 实例（可为 None）
- JudgeRAG 实例从全局 ExpertAgent 单例构造：
  ```python
  from expert.agent import ExpertAgent
  from agent.judge import JudgeRAG

  expert = get_expert_agent()  # 可能返回 None
  judge = JudgeRAG(expert=expert) if expert else None
  ```

### 5. SSE 事件

**新增事件：**

所有裁判事件携带 `phase` 字段用于前端区分阶段。

| 事件 | 阶段 | data 字段 |
|------|------|-----------|
| `topic_analysis_start` | 预分析开始 | `{target, phase: "topic_analysis"}` |
| `judge_graph_recall` | 裁判图谱召回 | `{nodes: [{id, type, label, confidence}], phase: "topic_analysis" \| "round_eval" \| "final_verdict"}` |
| `judge_tool_call` | 裁判工具调用 | `{engine, action, params, label, phase: "topic_analysis" \| "final_verdict"}` |
| `judge_tool_result` | 裁判工具结果 | `{engine, action, summary, hasError, phase: "topic_analysis" \| "final_verdict"}` |
| `topic_analysis_complete` | 预分析完成 | `{briefing: {focus_areas, related_stocks, key_data, summary}, phase: "topic_analysis"}` |

JudgeRAG 内部拦截 ExpertAgent 产出的 `graph_recall`、`tool_call`、`tool_result` 事件，重命名为 `judge_` 前缀并注入 `phase` 字段。

**保持不变的事件：**
- `judge_round_eval` — 每轮小评结果
- `judge_token` — 最终裁决流式 token
- `judge_verdict` — 最终裁决结构化结果

### 6. 前端改动

**useDebateStore.ts：**
- 新增 `TranscriptItem` 类型：`topic_analysis`（展示预分析 briefing）
- 新增 SSE handler：`topic_analysis_start`、`topic_analysis_complete`、`judge_graph_recall`、`judge_tool_call`、`judge_tool_result`
- 通过 `phase` 字段区分事件属于预分析还是最终裁决阶段

**TranscriptFeed.tsx：**
- 新增 `TopicAnalysisCard` 组件（可折叠，展示 briefing 内容：焦点、相关标的、数据摘要）
- 最终裁决的 `VerdictCard` 可选展示裁判的图谱召回和工具调用（折叠区域）

### 7. 错误处理

每个 JudgeRAG 方法都有明确的降级策略：

| 方法 | 失败场景 | 降级行为 |
|------|---------|---------|
| `analyze_topic` | ExpertAgent 未初始化 / LLM 超时 / 工具调用失败 | 跳过预分析，log warning，辩论正常继续（briefing 为空） |
| `round_eval` | graph recall 返回空 / LLM 解析失败 | 使用辩手自报 confidence 构造默认 RoundEval（与现有 fallback 一致） |
| `final_verdict_stream` | ExpertAgent 完整流程失败 | 降级为现有的纯 LLM 裁决（不走 RAG，直接用 blackboard 上下文生成 verdict） |

**ExpertAgent 不可用时的全局降级：**
- 辩论路由构造 JudgeRAG 时，如果 `get_expert_agent()` 返回 None（初始化失败），则 `judge` 参数传 None
- `run_debate` 检测到 `judge is None` 时，回退到现有的 `judge_round_eval()` + `judge_summarize_stream()` 路径
- 这意味着旧的 judge 函数不立即删除，而是保留为 fallback，待 RAG 路径稳定后再移除

### 8. 知识图谱强化路径

每场辩论对图谱的贡献（基于 `_learn_from_conversation` 现有能力）：

| 阶段 | 图谱操作 | 示例 |
|------|---------|------|
| 预分析 `learn` | 自动提取股票/板块/产业链节点、竞争关系 | 输入"半导体板块" → 创建 SectorNode("半导体")，关联已知 StockNode |
| 最终裁决 `learn` | 从裁决文本和工具结果中提取股票/板块/材料节点 | 裁决提到"中芯国际" → 创建/更新 StockNode，关联 SectorNode |
| 最终裁决 `belief_update` | 更新投资信念 confidence | 辩论结论看多 → 更新 BeliefNode("半导体估值") confidence |
| 最终裁决 `memory_store` | 存入 ChromaDB 语义记忆 | 辩论摘要存入 memory，未来 recall 可召回 |

注意：`_learn_from_conversation` 目前支持提取 StockNode、SectorNode、MaterialNode 和竞争关系边。不支持自动创建 EventNode — 如需从辩论结论中提取事件节点，需在后续迭代中扩展 `_learn_from_conversation`。

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `engine/agent/judge.py` | JudgeRAG 类 |
| 修改 | `engine/expert/agent.py` | 新增 5 个公开组合方法，`chat()` 重构为调用这些方法 |
| 修改 | `engine/agent/debate.py` | run_debate 接收 JudgeRAG，旧 judge 函数保留为 fallback |
| 修改 | `engine/agent/personas.py` | judge prompt 移入 JudgeRAG，旧 prompt 保留为 fallback |
| 修改 | `engine/api/routes/debate.py` | 构造 JudgeRAG 传入 run_debate |
| 修改 | `web/stores/useDebateStore.ts` | 新增 SSE handler + TranscriptItem 类型 |
| 修改 | `web/components/debate/TranscriptFeed.tsx` | 新增 TopicAnalysisCard |
| 修改 | `web/types/debate.ts` | 新增 TopicBriefing 类型 |

## 不在范围内

- 辩论 target 泛化（Spec B 处理）— Spec A 中 `target` 仍为股票代码或股票名，ExpertAgent 的 `recall()` 已支持 6 位代码匹配和名称子串匹配
- 数据引擎新增板块/宏观数据能力（Spec B 处理）
- 辩手 agent 的 RAG 化（辩手保持现有 LLM agent 模式）
- ExpertAgent 本身的功能增强
- `_learn_from_conversation` 扩展支持 EventNode 提取（后续迭代）
