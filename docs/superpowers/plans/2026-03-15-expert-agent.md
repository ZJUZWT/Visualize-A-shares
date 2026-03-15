# 投资专家 Agent 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个有持久知识图谱、能被用户说服更新信念、会主动查资料的投资专家 Agent，提供 SSE 流式对话接口和配套前端页面。

**Architecture:** 新增 `engine/expert/` 模块，包含 KnowledgeGraph（NetworkX + JSON 持久化）、ExpertAgent 对话流程、工具调用适配层和 FastAPI 路由。前端新增 `web/app/expert/` 页面和 `web/components/expert/` 组件，使用 Zustand store 管理 SSE 状态。

**Tech Stack:** Python/FastAPI/NetworkX/ChromaDB/DuckDB（后端），Next.js/TypeScript/Zustand（前端）

---


## Chunk 0: 前置依赖

### Task 0: 安装 networkx

- [ ] **Step 1: 安装 networkx**

```bash
cd engine && .venv/bin/pip install "networkx>=3.0" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

- [ ] **Step 2: 添加到 `engine/pyproject.toml` 的 `dependencies` 列表**

```toml
"networkx>=3.0",
```

- [ ] **Step 3: Commit**

```bash
git add engine/pyproject.toml
git commit -m "chore: 添加 networkx 依赖"
```

---

## Chunk 1: 后端核心数据结构

### Task 1: schemas.py — 节点、边、信念更新数据结构

**Files:**
- Create: `engine/expert/schemas.py`
- Create: `engine/expert/__init__.py`

- [ ] **Step 1: 创建 `engine/expert/__init__.py`**

```python
"""投资专家 Agent 模块"""
```

- [ ] **Step 2: 创建 `engine/expert/schemas.py`**

```python
"""投资专家 Agent 数据结构"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid.uuid4())


# ─── 节点类型 ────────────────────────────────────────────────

class StockNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["stock"] = "stock"
    code: str
    name: str


class SectorNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["sector"] = "sector"
    name: str


class EventNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["event"] = "event"
    name: str
    date: str
    description: str


class BeliefNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["belief"] = "belief"
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StanceNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["stance"] = "stance"
    target: str  # 股票代码
    signal: Literal["bullish", "bearish", "neutral"]
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


GraphNode = StockNode | SectorNode | EventNode | BeliefNode | StanceNode


# ─── 边类型 ──────────────────────────────────────────────────

class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation: Literal[
        "belongs_to", "influenced_by", "supports",
        "contradicts", "updated_by", "researched"
    ]
    reason: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ─── LLM 契约 ────────────────────────────────────────────────

class ToolCall(BaseModel):
    engine: str
    action: str
    params: dict


class ThinkOutput(BaseModel):
    needs_data: bool
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning: str = ""


class BeliefChange(BaseModel):
    old_belief_id: str
    new_content: str
    new_confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class BeliefUpdateOutput(BaseModel):
    updated: bool
    changes: list[BeliefChange] = Field(default_factory=list)


# ─── API 请求/响应 ───────────────────────────────────────────

class ExpertChatRequest(BaseModel):
    message: str
    session_id: str | None = None
```

- [ ] **Step 3: 写单元测试**

```python
# engine/tests/expert/test_schemas.py
import pytest
from expert.schemas import BeliefNode, StockNode, ThinkOutput, BeliefUpdateOutput, new_id


def test_belief_node_has_uuid_id():
    b = BeliefNode(content="test", confidence=0.7)
    assert len(b.id) == 36  # UUID format
    assert b.type == "belief"


def test_stock_node_fields():
    s = StockNode(code="300750", name="宁德时代")
    assert s.code == "300750"
    assert s.type == "stock"


def test_think_output_defaults():
    t = ThinkOutput(needs_data=False)
    assert t.tool_calls == []


def test_belief_update_output():
    out = BeliefUpdateOutput(updated=False)
    assert out.changes == []
```

- [ ] **Step 4: 运行测试**

```bash
cd engine && .venv/bin/pytest tests/expert/test_schemas.py -v
```

Expected: 4 passed

- [ ] **Step 5: 创建测试目录并 commit**

```bash
mkdir -p engine/tests/expert && touch engine/tests/expert/__init__.py
git add engine/expert/ engine/tests/expert/
git commit -m "feat: expert schemas + node/edge/LLM contract types"
```

---

### Task 2: knowledge_graph.py — NetworkX 图谱 + JSON 持久化

**Files:**
- Create: `engine/expert/knowledge_graph.py`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/expert/test_knowledge_graph.py
import json
import pytest
from pathlib import Path
from expert.knowledge_graph import KnowledgeGraph
from expert.schemas import BeliefNode, StockNode


@pytest.fixture
def tmp_graph(tmp_path):
    path = tmp_path / "test_graph.json"
    return KnowledgeGraph(path=str(path))


def test_add_and_get_node(tmp_graph):
    node = BeliefNode(content="政策是A股最重要变量", confidence=0.75)
    tmp_graph.add_node(node)
    result = tmp_graph.get_node(node.id)
    assert result is not None
    assert result["content"] == "政策是A股最重要变量"


def test_add_edge(tmp_graph):
    n1 = StockNode(code="300750", name="宁德时代")
    n2 = BeliefNode(content="新能源长期看好", confidence=0.8)
    tmp_graph.add_node(n1)
    tmp_graph.add_node(n2)
    tmp_graph.add_edge(n1.id, n2.id, "supports")
    neighbors = tmp_graph.get_neighbors(n1.id)
    assert any(n["id"] == n2.id for n in neighbors)


def test_persist_and_reload(tmp_graph, tmp_path):
    node = BeliefNode(content="分散投资优于集中押注", confidence=0.65)
    tmp_graph.add_node(node)
    tmp_graph.save()
    path = tmp_path / "test_graph.json"
    graph2 = KnowledgeGraph(path=str(path))
    result = graph2.get_node(node.id)
    assert result is not None
    assert result["content"] == "分散投资优于集中押注"


def test_update_belief_creates_updated_by_edge(tmp_graph):
    old = BeliefNode(content="旧信念", confidence=0.5)
    tmp_graph.add_node(old)
    new_id = tmp_graph.update_belief(
        old_belief_id=old.id,
        new_content="新信念",
        new_confidence=0.85,
        reason="用户提供了充分论据"
    )
    assert new_id is not None
    new_node = tmp_graph.get_node(new_id)
    assert new_node["content"] == "新信念"
    # 旧节点仍存在
    old_node = tmp_graph.get_node(old.id)
    assert old_node is not None


def test_recall_by_stock_code(tmp_graph):
    stock = StockNode(code="300750", name="宁德时代")
    tmp_graph.add_node(stock)
    results = tmp_graph.recall(message="300750 近期走势如何")
    assert any(n["id"] == stock.id for n in results)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && .venv/bin/pytest tests/expert/test_knowledge_graph.py -v
```

Expected: ImportError (knowledge_graph not yet created)

- [ ] **Step 3: 实现 `engine/expert/knowledge_graph.py`**

```python
"""KnowledgeGraph — NetworkX 内存图 + JSON 持久化"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import networkx as nx
from loguru import logger

from expert.schemas import GraphNode, BeliefNode, new_id

_LOCK = asyncio.Lock()


class KnowledgeGraph:
    """投资专家知识图谱

    节点存储在 NetworkX DiGraph 中，持久化为 JSON 文件。
    写操作通过模块级 asyncio.Lock 保护并发安全。
    """

    def __init__(self, path: str):
        self._path = Path(path)
        self._graph: nx.DiGraph = nx.DiGraph()
        if self._path.exists():
            self._load()
            logger.info(f"知识图谱加载: {self._path}, 节点数={self._graph.number_of_nodes()}")
        else:
            logger.info(f"知识图谱初始化（空图）: {self._path}")

    # ─── 读操作（不加锁）────────────────────────────────────

    def get_node(self, node_id: str) -> dict | None:
        if node_id not in self._graph:
            return None
        return dict(self._graph.nodes[node_id])

    def get_neighbors(self, node_id: str) -> list[dict]:
        result = []
        for neighbor_id in self._graph.successors(node_id):
            node_data = self._graph.nodes.get(neighbor_id, {})
            result.append({"id": neighbor_id, **node_data})
        return result

    def get_all_beliefs(self) -> list[dict]:
        """返回所有最新版本的 belief 节点（排除被 updated_by 指向的旧节点）"""
        superseded = set()
        for u, v, data in self._graph.edges(data=True):
            if data.get("relation") == "updated_by":
                superseded.add(u)
        beliefs = []
        for node_id, data in self._graph.nodes(data=True):
            if data.get("type") == "belief" and node_id not in superseded:
                beliefs.append({"id": node_id, **data})
        return sorted(beliefs, key=lambda x: x.get("confidence", 0), reverse=True)

    def recall(self, message: str, top_k: int = 10) -> list[dict]:
        """从消息中提取关键词，召回相关图谱节点（最多 top_k 个）"""
        matched_ids: set[str] = set()

        # 1. 股票代码匹配（6位数字）
        codes = re.findall(r"\b\d{6}\b", message)
        for node_id, data in self._graph.nodes(data=True):
            if data.get("type") == "stock" and data.get("code") in codes:
                matched_ids.add(node_id)

        # 2. 名称关键词匹配（stock/sector/event）
        for node_id, data in self._graph.nodes(data=True):
            node_type = data.get("type")
            if node_type in ("stock", "sector", "event"):
                label = data.get("name", "") or data.get("code", "")
                if label and label in message:
                    matched_ids.add(node_id)

        # 3. 信念关键词匹配
        belief_keywords = ["政策", "基本面", "情绪", "估值", "资金", "技术", "分散", "集中"]
        if any(kw in message for kw in belief_keywords):
            for node_id, data in self._graph.nodes(data=True):
                if data.get("type") == "belief":
                    matched_ids.add(node_id)

        # 4. 1-hop 扩展
        hop_ids: set[str] = set()
        for node_id in list(matched_ids):
            for neighbor in self._graph.successors(node_id):
                hop_ids.add(neighbor)
            for neighbor in self._graph.predecessors(node_id):
                hop_ids.add(neighbor)
        matched_ids.update(hop_ids)

        # 5. 排序并截取
        priority = {"stock": 0, "belief": 1, "stance": 2, "event": 3, "sector": 4}
        nodes = []
        for node_id in matched_ids:
            data = self._graph.nodes.get(node_id, {})
            nodes.append({"id": node_id, **data})
        nodes.sort(key=lambda x: priority.get(x.get("type", ""), 9))
        return nodes[:top_k]

    def to_dict(self) -> dict:
        return nx.node_link_data(self._graph, edges="links")

    # ─── 写操作（调用方负责加锁）────────────────────────────

    def add_node(self, node: GraphNode) -> None:
        data = node.model_dump()
        node_id = data.pop("id")
        self._graph.add_node(node_id, **data)

    def add_edge(self, source_id: str, target_id: str, relation: str,
                 reason: str | None = None, timestamp: str | None = None) -> None:
        from datetime import datetime
        self._graph.add_edge(
            source_id, target_id,
            relation=relation,
            reason=reason,
            timestamp=timestamp or datetime.now().isoformat(),
        )

    def update_belief(self, old_belief_id: str, new_content: str,
                      new_confidence: float, reason: str) -> str:
        """创建新 belief 节点，加 updated_by 边，返回新节点 ID"""
        new_node = BeliefNode(content=new_content, confidence=new_confidence)
        self.add_node(new_node)
        self.add_edge(old_belief_id, new_node.id, "updated_by", reason=reason)
        return new_node.id

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._graph, edges="links")
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    # ─── 内部 ────────────────────────────────────────────────

    def _load(self) -> None:
        data = json.loads(self._path.read_text())
        self._graph = nx.node_link_graph(data, edges="links")
```

- [ ] **Step 4: 运行测试**

```bash
cd engine && .venv/bin/pytest tests/expert/test_knowledge_graph.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/expert/knowledge_graph.py engine/tests/expert/test_knowledge_graph.py
git commit -m "feat: KnowledgeGraph — NetworkX + JSON 持久化 + recall 算法"
```

---

## Chunk 2: 后端 personas + tools

### Task 3: personas.py — 初始人格 + THINK_SYSTEM_PROMPT

**Files:**
- Create: `engine/expert/personas.py`

- [ ] **Step 1: 创建 `engine/expert/personas.py`**

```python
"""投资专家人格定义 + LLM System Prompt"""

INITIAL_BELIEFS = [
    {"content": "基本面是长期定价的锚，但短期价格由情绪和资金驱动", "confidence": 0.7},
    {"content": "分散投资优于集中押注，除非有极高确定性", "confidence": 0.65},
    {"content": "政策是A股不可忽视的系统性变量", "confidence": 0.75},
    {"content": "散户情绪是反向指标，极度乐观时需警惕", "confidence": 0.6},
]

THINK_SYSTEM_PROMPT = """你是一位理性、多元视角的A股投资专家。你有自己的投资哲学和信念体系。
当用户提问时，你需要判断是否需要查询实时数据才能给出有价值的回答。

你的当前信念（知识图谱召回）：
{graph_context}

相关历史对话：
{memory_context}

可用工具：
- engine: "data", action: "get_daily_history", params: {"code": "股票代码", "days": 30}
- engine: "data", action: "get_stock_info", params: {"code": "股票代码"}
- engine: "quant", action: "get_factor_scores", params: {"code": "股票代码"}
- engine: "quant", action: "get_technical_indicators", params: {"code": "股票代码"}
- engine: "cluster", action: "get_cluster_for_stock", params: {"code": "股票代码"}
- engine: "debate", action: "start", params: {"code": "股票代码", "max_rounds": 2}

请以 JSON 格式输出你的决策，不要输出任何其他内容：
{"needs_data": true/false, "tool_calls": [...], "reasoning": "简短说明"}"""

BELIEF_UPDATE_PROMPT = """你是一位理性的投资专家。请分析以下对话，判断你的信念是否需要更新。

当前信念列表（含 ID）：
{beliefs_context}

本轮对话：
用户: {user_message}
你的回复: {expert_reply}

如果用户提供了充分的逻辑论据或数据，你应该更新相关信念。
如果只是情绪化表达或无新信息，不更新。

请以 JSON 格式输出，不要输出任何其他内容：
{"updated": true/false, "changes": [{"old_belief_id": "UUID", "new_content": "...", "new_confidence": 0.0-1.0, "reason": "..."}]}"""


def format_graph_context(nodes: list[dict]) -> str:
    if not nodes:
        return "（无相关图谱节点）"
    lines = []
    for n in nodes:
        t = n.get("type", "")
        if t == "belief":
            lines.append(f"- [信念 {n['id'][:8]}] {n.get('content')} (置信度: {n.get('confidence')})")
        elif t == "stock":
            lines.append(f"- [股票] {n.get('code')} {n.get('name')}")
        elif t == "stance":
            lines.append(f"- [看法] {n.get('target')} {n.get('signal')} 评分:{n.get('score')}")
        else:
            lines.append(f"- [{t}] {n.get('name', n.get('id', ''))}")
    return "\n".join(lines)


def format_memory_context(memories: list[dict]) -> str:
    if not memories:
        return "（无相关历史对话）"
    return "\n".join(f"- {m['content'][:200]}" for m in memories[:3])


def format_beliefs_context(beliefs: list[dict]) -> str:
    if not beliefs:
        return "（暂无信念）"
    return "\n".join(
        f"- ID:{b['id']} 内容:{b.get('content')} 置信度:{b.get('confidence')}"
        for b in beliefs
    )
```

- [ ] **Step 2: 写测试**

```python
# engine/tests/expert/test_personas.py
from expert.personas import format_graph_context, format_memory_context, INITIAL_BELIEFS

def test_initial_beliefs_count():
    assert len(INITIAL_BELIEFS) == 4

def test_format_graph_context_empty():
    assert "无" in format_graph_context([])

def test_format_graph_context_belief():
    nodes = [{"id": "abc123xx", "type": "belief", "content": "政策重要", "confidence": 0.75}]
    result = format_graph_context(nodes)
    assert "政策重要" in result and "0.75" in result

def test_format_memory_context_empty():
    assert "无" in format_memory_context([])
```

- [ ] **Step 3: 运行测试**

```bash
cd engine && .venv/bin/pytest tests/expert/test_personas.py -v
```

Expected: 4 passed

- [ ] **Step 4: Commit**

```bash
git add engine/expert/personas.py engine/tests/expert/test_personas.py
git commit -m "feat: expert personas — 初始信念 + LLM system prompts"
```

---

### Task 4: tools.py — 引擎调用适配层

**Files:**
- Create: `engine/expert/tools.py`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/expert/test_tools.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from expert.tools import ExpertTools

@pytest.fixture
def tools():
    return ExpertTools()

@pytest.mark.asyncio
async def test_execute_unknown_engine_returns_error(tools):
    result = await tools.execute("unknown_engine", "some_action", {})
    assert "不支持" in result

@pytest.mark.asyncio
async def test_summarize_truncates(tools):
    long_str = "x" * 300
    result = tools._summarize(long_str)
    assert len(result) <= 200

@pytest.mark.asyncio
async def test_execute_debate_start_timeout(tools):
    with patch.object(tools, "_run_debate", new_callable=AsyncMock, side_effect=Exception("timeout")):
        result = await tools.execute("debate", "start", {"code": "300750"})
        assert "失败" in result or "超时" in result
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && .venv/bin/pytest tests/expert/test_tools.py -v
```

Expected: ImportError

- [ ] **Step 3: 实现 `engine/expert/tools.py`**

```python
"""ExpertTools — 工具调用适配层"""

import asyncio
import json
from typing import Any

import httpx
from loguru import logger

from agent.data_fetcher import DataFetcher
from agent.schemas import DataRequest


class ExpertTools:
    DEBATE_URL = "http://localhost:8000/api/v1/debate"
    DEBATE_TIMEOUT = 180.0

    def __init__(self):
        self._fetcher = DataFetcher()

    async def execute(self, engine: str, action: str, params: dict) -> str:
        try:
            if engine == "debate" and action == "start":
                return await asyncio.wait_for(
                    self._run_debate(params.get("code", ""), params.get("max_rounds", 2)),
                    timeout=self.DEBATE_TIMEOUT,
                )
            elif engine in ("data", "quant", "cluster"):
                req = DataRequest(requested_by="expert", engine=engine, action=action, params=params)
                result = await self._fetcher.fetch_by_request(req)
                return self._summarize(result)
            else:
                return f"不支持的引擎: {engine}"
        except asyncio.TimeoutError:
            logger.warning(f"工具调用超时: {engine}.{action}")
            return f"工具调用超时（{engine}.{action}）"
        except Exception as e:
            logger.error(f"工具调用失败 [{engine}.{action}]: {e}")
            return f"工具调用失败: {e}"

    async def _run_debate(self, code: str, max_rounds: int) -> str:
        summary = ""
        async with httpx.AsyncClient(timeout=self.DEBATE_TIMEOUT) as client:
            async with client.stream(
                "POST", self.DEBATE_URL,
                json={"code": code, "max_rounds": max_rounds},
                headers={"Accept": "text/event-stream"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    if isinstance(data, dict) and "summary" in data:
                        summary = data["summary"]
        return summary[:500] if summary else "辩论完成，未获取到裁决摘要"

    def _summarize(self, result: Any) -> str:
        if result is None:
            return "无数据"
        if isinstance(result, str):
            return result[:200]
        try:
            text = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            text = str(result)
        return text[:200]
```

- [ ] **Step 4: 运行测试**

```bash
cd engine && .venv/bin/pytest tests/expert/test_tools.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add engine/expert/tools.py engine/tests/expert/test_tools.py
git commit -m "feat: ExpertTools — 引擎调用适配层 + debate SSE 消费"
```

---

## Chunk 3: ExpertAgent 对话流程

### Task 5: agent.py — 对话流程主类

**Files:**
- Create: `engine/expert/agent.py`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/expert/test_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from expert.agent import ExpertAgent


@pytest.fixture
def agent(tmp_path):
    graph_path = str(tmp_path / "graph.json")
    with patch("expert.agent.AgentMemory"), \
         patch("expert.agent.LLMProviderFactory"), \
         patch("expert.agent.llm_settings"):
        return ExpertAgent(graph_path=graph_path, chromadb_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_chat_yields_sse_events(agent):
    events = []
    async for event in agent.chat("宁德时代最近怎么样"):
        events.append(event)
    event_types = [e["event"] for e in events]
    assert "thinking_start" in event_types
    assert "reply_complete" in event_types


@pytest.mark.asyncio
async def test_chat_graph_recall_event(agent):
    # 先加一个股票节点
    from expert.schemas import StockNode
    agent._graph.add_node(StockNode(code="300750", name="宁德时代"))
    events = []
    async for event in agent.chat("300750 近期走势"):
        events.append(event)
    event_types = [e["event"] for e in events]
    assert "graph_recall" in event_types


@pytest.mark.asyncio
async def test_chat_error_event_on_llm_failure(agent):
    agent._llm = None  # 模拟 LLM 未配置
    events = []
    async for event in agent.chat("测试"):
        events.append(event)
    event_types = [e["event"] for e in events]
    assert "error" in event_types or "reply_complete" in event_types
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && .venv/bin/pytest tests/expert/test_agent.py -v
```

Expected: ImportError

- [ ] **Step 3: 实现 `engine/expert/agent.py`**

```python
"""ExpertAgent — 投资专家对话流程"""

import asyncio
import json
from typing import AsyncGenerator

from loguru import logger

from agent.memory import AgentMemory
from llm.providers import ChatMessage
from expert.knowledge_graph import KnowledgeGraph
from expert.tools import ExpertTools
from expert.schemas import BeliefNode, ThinkOutput, BeliefUpdateOutput
from expert.personas import (
    INITIAL_BELIEFS, THINK_SYSTEM_PROMPT, BELIEF_UPDATE_PROMPT,
    format_graph_context, format_memory_context, format_beliefs_context,
)

class ExpertAgent:
    """投资专家 Agent

    对话流程：
    1. graph_recall → 2. memory_recall → 3. think → 4. tool_calls
    → 5. reply_stream → 6. belief_update → 7. memory_store → 8. history_store
    """

    def __init__(self, graph_path: str, chromadb_dir: str):
        self._graph = KnowledgeGraph(path=graph_path)
        self._memory = AgentMemory(persist_dir=chromadb_dir)
        self._tools = ExpertTools()
        self._lock = asyncio.Lock()
        self._llm = self._init_llm()
        self._init_beliefs()

    def _init_llm(self):
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            if llm_settings.api_key:
                return LLMProviderFactory.create(llm_settings)
        except Exception as e:
            logger.warning(f"LLM 初始化失败: {e}")
        return None

    def _init_beliefs(self):
        """首次启动时写入初始信念"""
        if self._graph.get_all_beliefs():
            return
        for b in INITIAL_BELIEFS:
            node = BeliefNode(content=b["content"], confidence=b["confidence"])
            self._graph.add_node(node)
        self._graph.save()
        logger.info("初始信念已写入知识图谱")

    async def chat(self, message: str) -> AsyncGenerator[dict, None]:
        """处理用户消息，yield SSE 事件字典"""
        yield {"event": "thinking_start", "data": {}}

        # 1. graph_recall
        recalled_nodes = self._graph.recall(message)
        yield {"event": "graph_recall", "data": {"nodes": [
            {"id": n["id"], "type": n.get("type"), "label": n.get("name") or n.get("content", "")[:40],
             "confidence": n.get("confidence")}
            for n in recalled_nodes
        ]}}

        # 2. memory_recall
        memories = self._memory.recall(agent_role="expert", query=message, top_k=5)

        # 3. think
        tool_calls = []
        if self._llm:
            think_output = await self._think(message, recalled_nodes, memories)
            tool_calls = think_output.tool_calls if think_output.needs_data else []

        # 4. tool_calls
        tool_results = []
        for tc in tool_calls:
            yield {"event": "tool_call", "data": {"engine": tc.engine, "action": tc.action, "params": tc.params}}
            summary = await self._tools.execute(tc.engine, tc.action, tc.params)
            tool_results.append({"engine": tc.engine, "action": tc.action, "summary": summary})
            yield {"event": "tool_result", "data": {"engine": tc.engine, "action": tc.action, "summary": summary}}

        # 5. reply_stream
        expert_reply = ""
        if self._llm:
            async for token, full_text in self._reply_stream(message, recalled_nodes, memories, tool_results):
                if token:
                    expert_reply = full_text
                    yield {"event": "reply_token", "data": {"token": token}}
        else:
            expert_reply = "LLM 未配置，无法生成回复。"

        yield {"event": "reply_complete", "data": {"full_text": expert_reply}}

        # 6. belief_update
        if self._llm and expert_reply:
            async for event in self._belief_update(message, expert_reply):
                yield event

        # 7. memory_store
        stock_codes = [n["code"] for n in recalled_nodes if n.get("type") == "stock"]
        target = stock_codes[0] if stock_codes else "general"
        self._memory.store(
            agent_role="expert",
            target=target,
            content=f"用户: {message}\n专家: {expert_reply}",
            metadata={"tools_used": str([tc.action for tc in tool_calls])},
        )

        # 8. history_store（由 routes.py 调用，此处不重复）

    async def _think(self, message: str, nodes: list, memories: list) -> ThinkOutput:
        """调用 LLM 判断是否需要查数据"""
        prompt = THINK_SYSTEM_PROMPT.format(
            graph_context=format_graph_context(nodes),
            memory_context=format_memory_context(memories),
        )
        try:
            response = await self._llm.chat([
                ChatMessage("system", prompt),
                ChatMessage("user", message),
            ])
            data = json.loads(response)
            return ThinkOutput(**data)
        except Exception as e:
            logger.warning(f"think 步骤解析失败，降级为无工具调用: {e}")
            return ThinkOutput(needs_data=False)

    async def _reply_stream(self, message: str, nodes: list, memories: list,
                             tool_results: list) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复，yield (token, accumulated_text)"""
        context_parts = [format_graph_context(nodes)]
        if tool_results:
            context_parts.append("数据查询结果：\n" + "\n".join(
                f"- {r['engine']}.{r['action']}: {r['summary']}" for r in tool_results
            ))
        system = "你是一位理性的A股投资专家，请基于以下上下文回答用户问题。\n\n" + "\n\n".join(context_parts)
        accumulated = ""
        try:
            async for token in self._llm.chat_stream([
                ChatMessage("system", system),
                ChatMessage("user", message),
            ]):
                accumulated += token
                yield token, accumulated
        except Exception as e:
            logger.error(f"reply_stream 失败: {e}")
            yield f"回复生成失败: {e}", f"回复生成失败: {e}"

    async def _belief_update(self, user_message: str, expert_reply: str) -> AsyncGenerator[dict, None]:
        """判断并执行信念更新"""
        beliefs = self._graph.get_all_beliefs()
        prompt = BELIEF_UPDATE_PROMPT.format(
            beliefs_context=format_beliefs_context(beliefs),
            user_message=user_message,
            expert_reply=expert_reply,
        )
        try:
            response = await self._llm.chat([
                ChatMessage("user", prompt),
            ])
            data = json.loads(response)
            output = BeliefUpdateOutput(**data)
            if output.updated:
                async with self._lock:
                    for change in output.changes:
                        old_node = self._graph.get_node(change.old_belief_id)
                        if not old_node:
                            continue
                        new_id = self._graph.update_belief(
                            old_belief_id=change.old_belief_id,
                            new_content=change.new_content,
                            new_confidence=change.new_confidence,
                            reason=change.reason,
                        )
                        self._graph.save()
                        new_node = self._graph.get_node(new_id)
                        yield {"event": "belief_updated", "data": {
                            "old": {"id": change.old_belief_id, "content": old_node.get("content"),
                                    "confidence": old_node.get("confidence")},
                            "new": {"id": new_id, "content": new_node.get("content"),
                                    "confidence": new_node.get("confidence")},
                            "reason": change.reason,
                        }}
        except Exception as e:
            logger.warning(f"belief_update 失败，跳过: {e}")
```

- [ ] **Step 4: 运行测试**

```bash
cd engine && .venv/bin/pytest tests/expert/test_agent.py -v
```

Expected: 3 passed（LLM 相关测试会走降级路径）

- [ ] **Step 5: Commit**

```bash
git add engine/expert/agent.py engine/tests/expert/test_agent.py
git commit -m "feat: ExpertAgent — 完整对话流程 + SSE 事件生成"
```

---

## Chunk 4: 后端路由 + main.py 注册

### Task 6: routes.py — FastAPI 路由 + DuckDB 表初始化

**Files:**
- Create: `engine/expert/routes.py`
- Modify: `engine/main.py`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/expert/test_routes.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture
def client():
    from fastapi import FastAPI
    app = FastAPI()
    with patch("expert.routes.get_expert_agent") as mock_agent_fn:
        mock_agent = MagicMock()
        mock_agent.chat = AsyncMock(return_value=iter([
            {"event": "thinking_start", "data": {}},
            {"event": "reply_complete", "data": {"full_text": "测试回复"}},
        ]))
        mock_agent_fn.return_value = mock_agent
        from expert.routes import router
        app.include_router(router)
        yield TestClient(app)


def test_get_beliefs_returns_list(client):
    with patch("expert.routes.get_expert_agent") as mock_fn:
        mock_agent = MagicMock()
        mock_agent._graph.get_all_beliefs.return_value = [
            {"id": "abc", "content": "测试信念", "confidence": 0.7}
        ]
        mock_fn.return_value = mock_agent
        resp = client.get("/api/v1/expert/beliefs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


def test_get_graph_returns_dict(client):
    with patch("expert.routes.get_expert_agent") as mock_fn:
        mock_agent = MagicMock()
        mock_agent._graph.to_dict.return_value = {"nodes": [], "links": []}
        mock_fn.return_value = mock_agent
        resp = client.get("/api/v1/expert/graph")
        assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && .venv/bin/pytest tests/expert/test_routes.py -v
```

Expected: ImportError

- [ ] **Step 3: 实现 `engine/expert/routes.py`**

```python
"""投资专家 API 路由"""

import json
from datetime import datetime

import duckdb
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger

from config import settings
from expert.schemas import ExpertChatRequest

router = APIRouter(prefix="/api/v1/expert", tags=["expert"])

_agent = None


def get_expert_agent():
    global _agent
    if _agent is None:
        from expert.agent import ExpertAgent
        _agent = ExpertAgent(
            graph_path=str(settings.DATA_DIR / "expert_knowledge_graph.json"),
            chromadb_dir=str(settings.chromadb.persist_dir),
        )
    return _agent


def _get_db():
    return duckdb.connect(str(settings.DB_PATH))


async def _init_db():
    """启动时建表（幂等）"""
    try:
        con = _get_db()
        con.execute("""
            CREATE SCHEMA IF NOT EXISTS expert;
            CREATE TABLE IF NOT EXISTS expert.conversation_log (
                id VARCHAR PRIMARY KEY,
                user_message VARCHAR,
                expert_reply VARCHAR,
                belief_changes JSON,
                tools_used JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.close()
        logger.info("expert.conversation_log 表初始化完成")
    except Exception as e:
        logger.error(f"expert DB 初始化失败: {e}")


@router.post("/chat")
async def expert_chat(req: ExpertChatRequest):
    """发消息给专家，SSE 流式返回"""
    agent = get_expert_agent()

    async def event_stream():
        full_reply = ""
        belief_changes = []
        tools_used = []
        try:
            async for event in agent.chat(req.message):
                evt_type = event["event"]
                if evt_type == "reply_complete":
                    full_reply = event["data"].get("full_text", "")
                elif evt_type == "tool_call":
                    tools_used.append(event["data"].get("action", ""))
                elif evt_type == "belief_updated":
                    belief_changes.append(event["data"])
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"expert chat 流程错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 写入 DuckDB 历史
        try:
            import uuid
            con = _get_db()
            con.execute(
                "INSERT INTO expert.conversation_log VALUES (?, ?, ?, ?, ?, ?)",
                [str(uuid.uuid4()), req.message, full_reply,
                 json.dumps(belief_changes, ensure_ascii=False),
                 json.dumps(tools_used, ensure_ascii=False),
                 datetime.now()]
            )
            con.close()
        except Exception as e:
            logger.warning(f"对话历史写入失败: {e}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/graph")
async def get_graph():
    """返回当前知识图谱 JSON"""
    agent = get_expert_agent()
    return agent._graph.to_dict()


@router.get("/beliefs")
async def get_beliefs():
    """返回当前最新信念列表"""
    agent = get_expert_agent()
    return agent._graph.get_all_beliefs()


@router.get("/history")
async def get_history(limit: int = 20):
    """返回对话历史（按时间倒序）"""
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT id, user_message, expert_reply, belief_changes, tools_used, created_at "
            "FROM expert.conversation_log ORDER BY created_at DESC LIMIT ?",
            [limit]
        ).fetchall()
        con.close()
        return [
            {"id": r[0], "user_message": r[1], "expert_reply": r[2],
             "belief_changes": r[3], "tools_used": r[4], "created_at": str(r[5])}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        return []
```

- [ ] **Step 4: 注册路由到 `engine/main.py`**

在 `engine/main.py` 的 import 区域添加：
```python
from expert.routes import router as expert_router
```

在 `app.include_router(info_router)` 后添加：
```python
app.include_router(expert_router)
```

在 `engine/main.py` 的 `@app.on_event("startup")` 处（或新建一个）添加 DB 初始化调用：
```python
@app.on_event("startup")
async def startup_event():
    from expert.routes import _init_db
    await _init_db()
```

注意：`routes.py` 中的 `@router.on_event("startup")` 不会被 FastAPI 自动触发，必须在 `app` 级别注册。

- [ ] **Step 5: 运行测试**

```bash
cd engine && .venv/bin/pytest tests/expert/test_routes.py -v
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add engine/expert/routes.py engine/main.py engine/tests/expert/test_routes.py
git commit -m "feat: expert routes — SSE chat + graph/beliefs/history 端点 + DuckDB 初始化"
```

---

## Chunk 5: 前端

### Task 7: expertStore.ts — Zustand store + SSE 状态管理

**Files:**
- Create: `web/stores/useExpertStore.ts`
- Create: `web/types/expert.ts`

- [ ] **Step 1: 创建 `web/types/expert.ts`**

```typescript
export type ExpertEventType =
  | "thinking_start"
  | "graph_recall"
  | "tool_call"
  | "tool_result"
  | "reply_token"
  | "reply_complete"
  | "belief_updated"
  | "error";

export interface GraphNode {
  id: string;
  type: "stock" | "sector" | "event" | "belief" | "stance";
  label: string;
  confidence?: number;
}

export interface ToolCallData {
  engine: string;
  action: string;
  params: Record<string, unknown>;
}

export interface ToolResultData {
  engine: string;
  action: string;
  summary: string;
}

export interface BeliefUpdatedData {
  old: { id: string; content: string; confidence: number };
  new: { id: string; content: string; confidence: number };
  reason: string;
}

export type ThinkingItem =
  | { type: "graph_recall"; nodes: GraphNode[] }
  | { type: "tool_call"; data: ToolCallData }
  | { type: "tool_result"; data: ToolResultData }
  | { type: "belief_updated"; data: BeliefUpdatedData };

export interface ExpertMessage {
  id: string;
  role: "user" | "expert";
  content: string;
  thinking: ThinkingItem[];
  isStreaming: boolean;
}

export type ExpertStatus = "idle" | "thinking" | "error";
```

- [ ] **Step 2: 创建 `web/stores/useExpertStore.ts`**

```typescript
import { create } from "zustand";
import type {
  ExpertMessage, ExpertStatus, ThinkingItem,
  GraphNode, ToolCallData, ToolResultData, BeliefUpdatedData,
} from "@/types/expert";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

let _abort: AbortController | null = null;

interface ExpertStore {
  messages: ExpertMessage[];
  status: ExpertStatus;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  reset: () => void;
}

function newId() {
  return Math.random().toString(36).slice(2);
}

export const useExpertStore = create<ExpertStore>((set, get) => ({
  messages: [],
  status: "idle",
  error: null,

  reset: () => {
    _abort?.abort();
    _abort = null;
    set({ messages: [], status: "idle", error: null });
  },

  sendMessage: async (text: string) => {
    // 追加用户消息
    const userMsg: ExpertMessage = {
      id: newId(), role: "user", content: text, thinking: [], isStreaming: false,
    };
    const expertMsg: ExpertMessage = {
      id: newId(), role: "expert", content: "", thinking: [], isStreaming: true,
    };
    set(s => ({ messages: [...s.messages, userMsg, expertMsg], status: "thinking", error: null }));

    _abort = new AbortController();
    try {
      const res = await fetch(`${API_BASE}/api/v1/expert/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        signal: _abort.signal,
      });
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";

        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const data = JSON.parse(line.slice(5).trim());
            set(s => {
              const msgs = [...s.messages];
              const idx = msgs.findIndex(m => m.id === expertMsg.id);
              if (idx === -1) return s;
              const msg = { ...msgs[idx] };

              if (eventType === "reply_token") {
                msg.content += data.token ?? "";
              } else if (eventType === "reply_complete") {
                msg.content = data.full_text ?? msg.content;
                msg.isStreaming = false;
              } else if (eventType === "graph_recall") {
                msg.thinking = [...msg.thinking, { type: "graph_recall", nodes: data.nodes as GraphNode[] }];
              } else if (eventType === "tool_call") {
                msg.thinking = [...msg.thinking, { type: "tool_call", data: data as ToolCallData }];
              } else if (eventType === "tool_result") {
                msg.thinking = [...msg.thinking, { type: "tool_result", data: data as ToolResultData }];
              } else if (eventType === "belief_updated") {
                msg.thinking = [...msg.thinking, { type: "belief_updated", data: data as BeliefUpdatedData }];
              } else if (eventType === "error") {
                msg.content = `错误: ${data.message}`;
                msg.isStreaming = false;
              }

              msgs[idx] = msg;
              return { messages: msgs };
            });
          }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      set(s => {
        const msgs = [...s.messages];
        const idx = msgs.findIndex(m => m.id === expertMsg.id);
        if (idx !== -1) {
          msgs[idx] = { ...msgs[idx], content: `请求失败: ${(e as Error).message}`, isStreaming: false };
        }
        return { messages: msgs, status: "error", error: (e as Error).message };
      });
    } finally {
      set({ status: "idle" });
    }
  },
}));
```

- [ ] **Step 3: Commit**

```bash
git add web/types/expert.ts web/stores/useExpertStore.ts
git commit -m "feat: expert store — Zustand + SSE 状态管理"
```

---

### Task 8: 前端组件

**Files:**
- Create: `web/components/expert/ThinkingPanel.tsx`
- Create: `web/components/expert/MessageBubble.tsx`
- Create: `web/components/expert/ChatArea.tsx`
- Create: `web/components/expert/InputBar.tsx`
- Create: `web/app/expert/page.tsx`

- [ ] **Step 1: 创建 `web/components/expert/ThinkingPanel.tsx`**

```tsx
"use client";
import { useState } from "react";
import type { ThinkingItem } from "@/types/expert";

export default function ThinkingPanel({ items }: { items: ThinkingItem[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;

  return (
    <div className="mb-2 text-xs text-gray-500">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 hover:text-gray-300 transition-colors"
      >
        <span>{open ? "▼" : "▶"}</span>
        <span>思考过程 ({items.length} 步)</span>
      </button>
      {open && (
        <div className="mt-1 pl-3 border-l border-gray-700 space-y-1">
          {items.map((item, i) => (
            <div key={i}>
              {item.type === "graph_recall" && (
                <div>
                  <span className="text-blue-400">图谱召回</span>
                  {item.nodes.map(n => (
                    <span key={n.id} className="ml-1 px-1 bg-gray-800 rounded text-gray-300">
                      {n.label}
                    </span>
                  ))}
                </div>
              )}
              {item.type === "tool_call" && (
                <div>
                  <span className="text-yellow-400">调用</span>
                  <span className="ml-1 text-gray-300">{item.data.engine}.{item.data.action}</span>
                </div>
              )}
              {item.type === "tool_result" && (
                <div>
                  <span className="text-green-400">结果</span>
                  <span className="ml-1 text-gray-400">{item.data.summary.slice(0, 80)}...</span>
                </div>
              )}
              {item.type === "belief_updated" && (
                <div>
                  <span className="text-purple-400">信念更新</span>
                  <span className="ml-1 text-gray-300">{item.data.new.content.slice(0, 60)}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 创建 `web/components/expert/MessageBubble.tsx`**

```tsx
import ThinkingPanel from "./ThinkingPanel";
import type { ExpertMessage } from "@/types/expert";

export default function MessageBubble({ msg }: { msg: ExpertMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-100"} rounded-lg px-4 py-3`}>
        {!isUser && <ThinkingPanel items={msg.thinking} />}
        <div className="whitespace-pre-wrap text-sm leading-relaxed">
          {msg.content}
          {msg.isStreaming && <span className="animate-pulse ml-1">▋</span>}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 创建 `web/components/expert/ChatArea.tsx`**

```tsx
"use client";
import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { ExpertMessage } from "@/types/expert";

export default function ChatArea({ messages }: { messages: ExpertMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.length === 0 && (
        <div className="text-center text-gray-500 mt-20 text-sm">
          向投资专家提问，他会主动查资料并更新自己的认知
        </div>
      )}
      {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 4: 创建 `web/components/expert/InputBar.tsx`**

```tsx
"use client";
import { useState, useRef } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
}

export default function InputBar({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-gray-700 px-4 py-3 flex gap-2">
      <textarea
        ref={ref}
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="向专家提问... (Enter 发送，Shift+Enter 换行)"
        rows={2}
        className="flex-1 bg-gray-800 text-gray-100 rounded-lg px-3 py-2 text-sm resize-none outline-none border border-gray-700 focus:border-blue-500 disabled:opacity-50"
      />
      <button
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors self-end"
      >
        发送
      </button>
    </div>
  );
}
```

- [ ] **Step 5: 创建 `web/app/expert/page.tsx`**

```tsx
"use client";
import ChatArea from "@/components/expert/ChatArea";
import InputBar from "@/components/expert/InputBar";
import { useExpertStore } from "@/stores/useExpertStore";

export default function ExpertPage() {
  const { messages, status, sendMessage } = useExpertStore();
  const isThinking = status === "thinking";

  return (
    <div className="flex flex-col h-screen bg-gray-900 text-gray-100">
      {/* 顶部栏 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <h1 className="text-base font-semibold">投资专家</h1>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span className={`w-2 h-2 rounded-full ${isThinking ? "bg-yellow-400 animate-pulse" : "bg-green-400"}`} />
          {isThinking ? "思考中..." : "就绪"}
        </div>
      </div>

      {/* 聊天区 */}
      <ChatArea messages={messages} />

      {/* 输入栏 */}
      <InputBar onSend={sendMessage} disabled={isThinking} />
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add web/components/expert/ web/app/expert/
git commit -m "feat: expert 前端 — ChatArea/MessageBubble/ThinkingPanel/InputBar/page"
```

---

## Chunk 6: 依赖 + 集成验证

### Task 9: 添加 networkx 依赖

**Files:**
- Modify: `engine/pyproject.toml`

- [ ] **Step 1: 在 `engine/pyproject.toml` 的 `dependencies` 列表中添加**

```toml
"networkx>=3.0",
```

- [ ] **Step 2: 安装依赖**

```bash
cd engine && .venv/bin/pip install networkx>=3.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

- [ ] **Step 3: 运行全部 expert 测试**

```bash
cd engine && .venv/bin/pytest tests/expert/ -v
```

Expected: 全部 passed

- [ ] **Step 4: Commit**

```bash
git add engine/pyproject.toml
git commit -m "chore: 添加 networkx 依赖"
```

---

### Task 10: 端到端验证

- [ ] **Step 1: 启动后端（手动在终端运行）**

```bash
cd engine && .venv/bin/python main.py
```

- [ ] **Step 2: 验证 API 端点可访问**

```bash
curl http://localhost:8000/api/v1/expert/beliefs
# Expected: JSON 数组，含 4 条初始信念

curl http://localhost:8000/api/v1/expert/graph
# Expected: {"nodes": [...], "links": [...]}
```

- [ ] **Step 3: 验证 SSE chat 端点**

```bash
curl -N -X POST http://localhost:8000/api/v1/expert/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好，请介绍一下你的投资理念"}' \
  --no-buffer
# Expected: SSE 事件流，含 thinking_start, graph_recall, reply_token..., reply_complete
```

- [ ] **Step 4: 验证前端页面（手动在终端运行）**

```bash
cd web && npm run dev
```

访问 `http://localhost:3000/expert`，确认：
- 页面正常加载
- 输入消息后出现流式回复
- 思考面板可折叠展开

- [ ] **Step 5: 最终 commit**

```bash
git add -A
git commit -m "feat: 投资专家 Agent — 完整实现（后端 + 前端）"
```

---

*Spec: `docs/superpowers/specs/2026-03-15-expert-agent-design.md`*
