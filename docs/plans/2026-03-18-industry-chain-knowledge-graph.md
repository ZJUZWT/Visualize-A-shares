# 产业链知识图谱（带物理约束）实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个「产业物理学家」级别的产业链推演引擎 + 力导向图可视化页面，让 AI 能够理解产业链中每个环节的物理约束（停产恢复周期、运输瓶颈、产能天花板、替代弹性、库存缓冲），并以交互式力导向图展示传导链。

**Architecture:** 后端新增 ChainAgent（递归多跳 LLM 推演），通过 SSE 流式推送节点/边到前端。前端新增 `/chain` 页面，使用 react-force-graph-2d 渲染力导向图，支持点击展开、拖拽、缩放。推演结果写入现有 KnowledgeGraph 持久化。

**Tech Stack:** Python/FastAPI/Pydantic(后端)，Next.js 15/React 19/Zustand 5/react-force-graph-2d/Tailwind v4(前端)，SSE 流式通信

---

## Task 1: 后端 Schema — 产业链物理约束数据结构

**Files:**
- Create: `backend/engine/industry/chain_schemas.py`
- Test: `tests/test_chain_schemas.py`

**Step 1: Write the failing test**

```python
# tests/test_chain_schemas.py
"""产业链推演 Schema 单元测试"""
import pytest
from engine.industry.chain_schemas import (
    PhysicalConstraint,
    ChainNode,
    ChainLink,
    ChainExploreRequest,
    ChainExploreResult,
)


def test_physical_constraint_defaults():
    pc = PhysicalConstraint(node="乙烯裂解")
    assert pc.node == "乙烯裂解"
    assert pc.shutdown_recovery_time == ""
    assert pc.restart_cost == ""


def test_chain_node_creation():
    node = ChainNode(
        id="n_石油",
        name="石油",
        node_type="material",
        impact="neutral",
    )
    assert node.id == "n_石油"
    assert node.node_type == "material"
    assert node.representative_stocks == []


def test_chain_link_with_constraint():
    link = ChainLink(
        source="石油",
        target="乙烯",
        relation="upstream",
        impact="negative",
        impact_reason="油价上涨推升乙烯成本",
        confidence=0.85,
        transmission_speed="1-3个月",
        transmission_strength="强刚性",
        transmission_mechanism="成本推动",
        dampening_factors=["库存缓冲30天", "长协价锁定"],
        amplifying_factors=["行业集中度高"],
        constraint=PhysicalConstraint(
            node="乙烯裂解",
            shutdown_recovery_time="冷启动需2-4周",
            restart_cost="重启一次数千万元",
        ),
    )
    assert link.confidence == 0.85
    assert len(link.dampening_factors) == 2
    assert link.constraint.shutdown_recovery_time == "冷启动需2-4周"


def test_chain_explore_request_validation():
    req = ChainExploreRequest(event="石油涨价", max_depth=3)
    assert req.event == "石油涨价"
    assert req.max_depth == 3
    assert req.start_node == ""


def test_chain_explore_request_depth_bounds():
    with pytest.raises(Exception):
        ChainExploreRequest(event="石油涨价", max_depth=0)
    with pytest.raises(Exception):
        ChainExploreRequest(event="石油涨价", max_depth=7)


def test_chain_explore_result_empty():
    result = ChainExploreResult(event="石油涨价")
    assert result.nodes == []
    assert result.links == []
    assert result.depth_reached == 0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_schemas.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'engine.industry.chain_schemas'"

**Step 3: Write minimal implementation**

```python
# backend/engine/industry/chain_schemas.py
"""产业链推演数据结构 — 带物理约束的产业认知模型

核心理念：产业链不只是「谁连着谁」（拓扑），
而是「这个连接有什么约束条件」（物理性质）。

每个产业环节有：
- 时间刚性（停产恢复周期）
- 产能天花板（扩产周期）
- 物流瓶颈（运输约束）
- 替代弹性（可替代路径）
- 库存缓冲（能撑多久）

每条传导链有：
- 传导速度（多快影响下游）
- 传导强度（影响多大）
- 衰减/放大因素
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PhysicalConstraint(BaseModel):
    """产业环节的物理/经济约束 — 产业专家与普通分析师的核心认知差距"""

    node: str                                       # 产业环节名称

    # ── 时间刚性 ──
    shutdown_recovery_time: str = ""                # "冷启动需2-4周"
    restart_cost: str = ""                          # "重启一次需数千万元"
    capacity_ramp_curve: str = ""                   # "复产后3-6个月爬坡到满产"

    # ── 产能约束 ──
    capacity_ceiling: str = ""                      # "全球产能2.1亿吨，利用率87%"
    expansion_lead_time: str = ""                   # "新建产能需3-5年"

    # ── 物流瓶颈 ──
    logistics_mode: str = ""                        # "VLCC海运/管道/铁路/公路"
    logistics_bottleneck: str = ""                  # "马六甲海峡/苏伊士运河瓶颈"
    logistics_vulnerability: str = ""               # "单一海峡封锁可致30%供给中断"

    # ── 替代弹性 ──
    substitution_path: str = ""                     # "煤制路线在油价>80美元时有竞争力"
    switching_cost: str = ""                        # "油转煤需要全新装置，不可逆"
    switching_time: str = ""                        # "新建煤化工项目3-4年"

    # ── 库存缓冲 ──
    inventory_buffer_days: str = ""                 # "全球库存覆盖30-45天消费"
    strategic_reserve: str = ""                     # "中国战略储备约XX万吨"

    # ── 进出口依存 ──
    import_dependency: str = ""                     # "中国原油对外依存度72%"
    export_ratio: str = ""                          # "出口占产量15%"
    key_trade_routes: str = ""                      # "中东→马六甲→中国，占进口60%"


class ChainNode(BaseModel):
    """产业链图谱节点"""

    id: str                                         # 节点唯一ID（如 "n_石油"）
    name: str                                       # 显示名称
    node_type: str = "industry"                     # industry | material | company | event | logistics
    impact: str = "neutral"                         # benefit | hurt | neutral | source
    impact_score: float = 0.0                       # -1.0(极度利空) ~ +1.0(极度利好)
    depth: int = 0                                  # 距事件源的跳数
    representative_stocks: list[str] = Field(default_factory=list)  # A股代码列表
    constraint: PhysicalConstraint | None = None    # 该节点的物理约束（可选）
    summary: str = ""                               # 一句话总结该节点受到的影响


class ChainLink(BaseModel):
    """产业链传导边 — 带物理约束"""

    source: str                                     # 源节点名称
    target: str                                     # 目标节点名称
    relation: str                                   # upstream | downstream | substitute | cost_input | byproduct | logistics | competes

    # ── 影响方向 ──
    impact: str = "neutral"                         # positive | negative | neutral
    impact_reason: str = ""                         # 传导逻辑（1-2句话）
    confidence: float = 0.8                         # 置信度 0-1

    # ── 传导特性（核心升级）──
    transmission_speed: str = ""                    # "即时/1-3个月/半年以上"
    transmission_strength: str = ""                 # "强刚性/中等/弱弹性"
    transmission_mechanism: str = ""                # "成本推动/供给收缩/需求替代/情绪传导"
    dampening_factors: list[str] = Field(default_factory=list)   # 衰减因素
    amplifying_factors: list[str] = Field(default_factory=list)  # 放大因素

    # ── 物理约束 ──
    constraint: PhysicalConstraint | None = None    # 目标环节的物理约束


class ChainExploreRequest(BaseModel):
    """产业链探索请求"""

    event: str = Field(description="触发事件，如'石油涨价'、'台海紧张'")
    start_node: str = ""                            # 可选起点节点（如"石油"），为空则AI自行判断
    max_depth: int = Field(default=3, ge=1, le=6)   # 最大展开深度
    focus_area: str = ""                            # 可选聚焦领域（如"化工"、"运输"）


class ChainExploreResult(BaseModel):
    """产业链探索完整结果"""

    event: str
    nodes: list[ChainNode] = Field(default_factory=list)
    links: list[ChainLink] = Field(default_factory=list)
    depth_reached: int = 0
    reasoning_summary: str = ""                     # AI的推理总结
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_schemas.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add backend/engine/industry/chain_schemas.py tests/test_chain_schemas.py
git commit -m "feat(chain): add chain schemas with physical constraints"
```

---

## Task 2: 后端 ChainAgent — 产业物理学家 LLM 推演引擎

**Files:**
- Create: `backend/engine/industry/chain_agent.py`
- Test: `tests/test_chain_agent.py`

**Step 1: Write the failing test**

```python
# tests/test_chain_agent.py
"""ChainAgent 推演引擎测试（使用 mock LLM）"""
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from engine.industry.chain_agent import ChainAgent
from engine.industry.chain_schemas import ChainExploreRequest


# ── Mock LLM 返回预设 JSON ──

MOCK_DEPTH1_RESPONSE = json.dumps({
    "nodes": [
        {
            "name": "石油",
            "node_type": "material",
            "impact": "source",
            "impact_score": 0.0,
            "summary": "事件源：石油价格上涨",
            "representative_stocks": [],
        },
        {
            "name": "乙烯",
            "node_type": "material",
            "impact": "hurt",
            "impact_score": -0.7,
            "summary": "石油涨价直接推升乙烯生产成本",
            "representative_stocks": ["600028"],
        },
    ],
    "links": [
        {
            "source": "石油",
            "target": "乙烯",
            "relation": "upstream",
            "impact": "negative",
            "impact_reason": "石油是乙烯裂解的核心原料，油价上涨直接推升乙烯成本",
            "confidence": 0.9,
            "transmission_speed": "即时",
            "transmission_strength": "强刚性",
            "transmission_mechanism": "成本推动",
            "dampening_factors": ["期货套保可延迟3个月"],
            "amplifying_factors": ["乙烯产能集中度高"],
            "constraint": {
                "node": "乙烯裂解",
                "shutdown_recovery_time": "冷启动需2-4周",
                "restart_cost": "重启一次需数千万元",
                "capacity_ceiling": "全球产能2.1亿吨",
                "logistics_mode": "管道+化学品船",
                "import_dependency": "中国乙烯自给率约60%",
            },
        },
    ],
    "expand_candidates": ["乙烯"],
}, ensure_ascii=False)


def _make_mock_llm(responses: list[str]):
    """创建返回预设响应列表的 mock LLM"""
    llm = MagicMock()
    call_index = [0]

    async def fake_chat_stream(messages):
        idx = min(call_index[0], len(responses) - 1)
        call_index[0] += 1
        for char in responses[idx]:
            yield char

    llm.chat_stream = fake_chat_stream
    return llm


@pytest.mark.asyncio
async def test_chain_agent_single_depth():
    llm = _make_mock_llm([MOCK_DEPTH1_RESPONSE])
    agent = ChainAgent(llm)

    req = ChainExploreRequest(event="石油涨价", max_depth=1)
    events = []
    async for event in agent.explore(req):
        events.append(event)

    # 应该有: explore_start, depth_start, nodes_discovered, links_discovered, explore_complete
    event_types = [e["event"] for e in events]
    assert "explore_start" in event_types
    assert "nodes_discovered" in event_types
    assert "explore_complete" in event_types

    # 检查 explore_complete 中有完整结果
    complete_event = [e for e in events if e["event"] == "explore_complete"][0]
    result = complete_event["data"]
    assert len(result["nodes"]) >= 2
    assert len(result["links"]) >= 1


@pytest.mark.asyncio
async def test_chain_agent_dedup():
    """已展开过的节点不应重复展开"""
    llm = _make_mock_llm([MOCK_DEPTH1_RESPONSE, MOCK_DEPTH1_RESPONSE])
    agent = ChainAgent(llm)

    req = ChainExploreRequest(event="石油涨价", max_depth=2)
    events = []
    async for event in agent.explore(req):
        events.append(event)

    # 不管几层，"石油" 只应出现一次
    complete_event = [e for e in events if e["event"] == "explore_complete"][0]
    node_names = [n["name"] for n in complete_event["data"]["nodes"]]
    assert node_names.count("石油") == 1
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_agent.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'engine.industry.chain_agent'"

**Step 3: Write minimal implementation**

```python
# backend/engine/industry/chain_agent.py
"""ChainAgent — 产业物理学家级 LLM 推演引擎

核心能力：
1. 递归多跳展开产业链传导
2. 每个环节强制输出物理约束（停产恢复、运输瓶颈、产能天花板等）
3. 每条传导边强制输出传导特性（速度、强度、衰减/放大因素）
4. SSE 流式推送，前端看到图逐步生长
5. 去重环检测，避免无限发散
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from .chain_schemas import (
    ChainExploreRequest,
    ChainExploreResult,
    ChainNode,
    ChainLink,
    PhysicalConstraint,
)

# ── 产业物理学家 Prompt ──

CHAIN_EXPLORE_PROMPT = """你是「产业物理学家」，不是普通的行业分析师。你必须像化工厂厂长+航运CEO+贸易商一样思考产业链。

## 当前事件
{event}

## 当前聚焦节点
{focus_nodes}

## 已经分析过的节点（不要重复）
{explored_nodes}

## 你的任务
分析上述事件对聚焦节点的**直接上下游**影响，生成新的传导节点和边。

## 关键要求 — 物理约束思维（这是你和普通分析师的核心区别）
对每个新发现的产业环节，你**必须**思考并输出：

1. **时间刚性**：该环节停产后恢复需要多久？为什么？（物理/化学/工程原因）
2. **产能天花板**：全球/中国产能多少？利用率？新建产能需要几年？
3. **物流约束**：原材料/产品怎么运输？瓶颈在哪？（航线、港口、管道、运力）
4. **替代弹性**：有没有替代路线？切换成本多高？需要多久？
5. **库存缓冲**：行业库存通常能撑多久？有战略储备吗？
6. **进出口依存**：进口依存度多少？出口占比多少？关键贸易路线？

对每条传导边，你**必须**说明：
- **传导速度**：价格变动多快传导到下游？（即时/1-3个月/半年以上）
- **传导强度**：强刚性（无法回避）/ 中等 / 弱弹性（可吸收）
- **衰减因素**：什么会削弱传导？（库存、套保、长协、政策限价…）
- **放大因素**：什么会放大传导？（集中度高、无替代品、消费刚性…）

{focus_area_note}

## 输出格式
直接输出 JSON，格式如下（不要输出任何其他内容）：
{{
  "nodes": [
    {{
      "name": "节点名称",
      "node_type": "material|industry|company|event|logistics",
      "impact": "benefit|hurt|neutral|source",
      "impact_score": 0.0,
      "summary": "一句话说明该节点如何受影响",
      "representative_stocks": ["600028"],
      "constraint": {{
        "node": "节点名称",
        "shutdown_recovery_time": "...",
        "restart_cost": "...",
        "capacity_ramp_curve": "...",
        "capacity_ceiling": "...",
        "expansion_lead_time": "...",
        "logistics_mode": "...",
        "logistics_bottleneck": "...",
        "logistics_vulnerability": "...",
        "substitution_path": "...",
        "switching_cost": "...",
        "switching_time": "...",
        "inventory_buffer_days": "...",
        "strategic_reserve": "...",
        "import_dependency": "...",
        "export_ratio": "...",
        "key_trade_routes": "..."
      }}
    }}
  ],
  "links": [
    {{
      "source": "源节点名称",
      "target": "目标节点名称",
      "relation": "upstream|downstream|substitute|cost_input|byproduct|logistics|competes",
      "impact": "positive|negative|neutral",
      "impact_reason": "传导逻辑说明",
      "confidence": 0.85,
      "transmission_speed": "即时|1-3个月|3-6个月|半年以上",
      "transmission_strength": "强刚性|中等|弱弹性",
      "transmission_mechanism": "成本推动|供给收缩|需求替代|情绪传导|政策驱动",
      "dampening_factors": ["因素1", "因素2"],
      "amplifying_factors": ["因素1", "因素2"],
      "constraint": {{...}}
    }}
  ],
  "expand_candidates": ["值得继续深挖的节点名称1", "节点名称2"]
}}"""


class ChainAgent:
    """产业链推演 Agent — 递归多跳展开"""

    def __init__(self, llm: BaseLLMProvider):
        self._llm = llm

    async def explore(self, req: ChainExploreRequest):
        """递归探索产业链传导，yield SSE 事件流

        事件类型：
        - explore_start: 探索开始
        - depth_start: 某层开始展开
        - nodes_discovered: 发现新节点
        - links_discovered: 发现新边
        - explore_complete: 探索完成，包含完整结果
        - error: 错误
        """
        all_nodes: dict[str, ChainNode] = {}  # name → ChainNode
        all_links: list[ChainLink] = []
        explored: set[str] = set()
        to_expand: list[str] = []

        yield {
            "event": "explore_start",
            "data": {"event": req.event, "max_depth": req.max_depth},
        }

        # ── 第一层：LLM 分析事件本身 ──
        for depth in range(1, req.max_depth + 1):
            if depth == 1:
                focus_nodes = req.start_node if req.start_node else req.event
                focus_list = [focus_nodes]
            else:
                focus_list = to_expand[:5]  # 每层最多展开5个节点

            if not focus_list:
                break

            yield {
                "event": "depth_start",
                "data": {"depth": depth, "expanding": focus_list},
            }

            focus_area_note = ""
            if req.focus_area:
                focus_area_note = f"请重点关注与「{req.focus_area}」相关的传导路径。"

            prompt = CHAIN_EXPLORE_PROMPT.format(
                event=req.event,
                focus_nodes="、".join(focus_list),
                explored_nodes="、".join(explored) if explored else "（无）",
                focus_area_note=focus_area_note,
            )

            try:
                raw = await self._collect_llm_response(prompt)
                parsed = _lenient_json_loads(raw)

                if not isinstance(parsed, dict):
                    logger.warning(f"ChainAgent depth={depth}: LLM 返回非 dict")
                    continue

                # 解析节点
                new_nodes = []
                for nd in parsed.get("nodes", []):
                    name = nd.get("name", "")
                    if not name or name in all_nodes:
                        continue
                    constraint = None
                    if nd.get("constraint"):
                        constraint = PhysicalConstraint(**{
                            k: v for k, v in nd["constraint"].items()
                            if k in PhysicalConstraint.model_fields
                        })
                    node = ChainNode(
                        id=f"n_{name}",
                        name=name,
                        node_type=nd.get("node_type", "industry"),
                        impact=nd.get("impact", "neutral"),
                        impact_score=float(nd.get("impact_score", 0.0)),
                        depth=depth,
                        representative_stocks=nd.get("representative_stocks", []),
                        constraint=constraint,
                        summary=nd.get("summary", ""),
                    )
                    all_nodes[name] = node
                    new_nodes.append(node)

                if new_nodes:
                    yield {
                        "event": "nodes_discovered",
                        "data": {
                            "depth": depth,
                            "nodes": [n.model_dump() for n in new_nodes],
                        },
                    }

                # 解析边
                new_links = []
                for lk in parsed.get("links", []):
                    source = lk.get("source", "")
                    target = lk.get("target", "")
                    if not source or not target:
                        continue
                    # 确保源和目标节点存在
                    for name in [source, target]:
                        if name not in all_nodes:
                            all_nodes[name] = ChainNode(
                                id=f"n_{name}", name=name, depth=depth,
                            )
                    constraint = None
                    if lk.get("constraint"):
                        constraint = PhysicalConstraint(**{
                            k: v for k, v in lk["constraint"].items()
                            if k in PhysicalConstraint.model_fields
                        })
                    link = ChainLink(
                        source=source,
                        target=target,
                        relation=lk.get("relation", "upstream"),
                        impact=lk.get("impact", "neutral"),
                        impact_reason=lk.get("impact_reason", ""),
                        confidence=float(lk.get("confidence", 0.8)),
                        transmission_speed=lk.get("transmission_speed", ""),
                        transmission_strength=lk.get("transmission_strength", ""),
                        transmission_mechanism=lk.get("transmission_mechanism", ""),
                        dampening_factors=lk.get("dampening_factors", []),
                        amplifying_factors=lk.get("amplifying_factors", []),
                        constraint=constraint,
                    )
                    all_links.append(link)
                    new_links.append(link)

                if new_links:
                    yield {
                        "event": "links_discovered",
                        "data": {
                            "depth": depth,
                            "links": [l.model_dump() for l in new_links],
                        },
                    }

                # 标记已探索 & 收集下一轮候选
                explored.update(focus_list)
                candidates = parsed.get("expand_candidates", [])
                to_expand = [c for c in candidates if c not in explored]

            except Exception as e:
                logger.error(f"ChainAgent depth={depth} 失败: {e}")
                yield {
                    "event": "error",
                    "data": {"message": f"第{depth}层推演失败: {type(e).__name__}"},
                }
                break

        # ── 最终结果 ──
        result = ChainExploreResult(
            event=req.event,
            nodes=list(all_nodes.values()),
            links=all_links,
            depth_reached=min(depth, req.max_depth) if all_nodes else 0,
        )

        yield {
            "event": "explore_complete",
            "data": result.model_dump(),
        }

    async def expand_node(self, event: str, node_name: str, existing_graph: dict):
        """交互式展开单个节点（用户双击触发）"""
        req = ChainExploreRequest(
            event=event,
            start_node=node_name,
            max_depth=1,
        )
        async for evt in self.explore(req):
            yield evt

    async def _collect_llm_response(self, prompt: str) -> str:
        """收集完整 LLM 响应"""
        chunks: list[str] = []
        async for token in self._llm.chat_stream(
            [ChatMessage(role="user", content=prompt)]
        ):
            chunks.append(token)
        return "".join(chunks)


# ── JSON 解析工具（复用 industry/agent.py 的模式）──

def _extract_json(text: str) -> str:
    """从 LLM 输出提取 JSON"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
    if "<think>" in text and "</think>" not in text:
        after_tag = text.split("<think>", 1)[-1]
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}', after_tag, re.DOTALL)
        if json_match:
            text = json_match.group(0)
        else:
            text = ""
    elif "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    result = match.group(1).strip() if match else text.strip()
    result = result.replace("\u201c", '"').replace("\u201d", '"')
    result = result.replace("\u2018", "'").replace("\u2019", "'")
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)
    return result


def _lenient_json_loads(text: str) -> dict | list:
    """宽松 JSON 解析"""
    raw = _extract_json(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    fixed2 = fixed.replace("'", '"')
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass
    # 尝试提取最外层 JSON 对象
    m = re.search(r'(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})', fixed, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("Chain JSON 解析失败", raw[:200] if raw else "(空)", 0)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_agent.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/engine/industry/chain_agent.py tests/test_chain_agent.py
git commit -m "feat(chain): add ChainAgent with physical constraint reasoning"
```

---

## Task 3: 后端 SSE 路由 — 产业链探索 API

**Files:**
- Modify: `backend/engine/industry/routes.py` (追加新端点)
- Modify: `backend/main.py:33` (路由已注册，无需改动)
- Test: `tests/test_chain_routes.py`

**Step 1: Write the failing test**

```python
# tests/test_chain_routes.py
"""产业链探索 API 路由测试"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

# 需要 mock LLM 才能启动 app
import os
os.environ.setdefault("LLM_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_chain_explore_endpoint_exists():
    """验证 /api/v1/industry/chain/explore 端点存在"""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # OPTIONS 请求测试端点存在性
        resp = await client.post(
            "/api/v1/industry/chain/explore",
            json={"event": "石油涨价"},
        )
        # 即使 LLM 不可用，也不应该是 404
        assert resp.status_code != 404


@pytest.mark.asyncio
async def test_chain_expand_node_endpoint_exists():
    """验证 /api/v1/industry/chain/expand 端点存在"""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/industry/chain/expand",
            json={"event": "石油涨价", "node_name": "乙烯"},
        )
        assert resp.status_code != 404
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_routes.py -v`
Expected: FAIL (404 because endpoints don't exist yet)

**Step 3: Append new endpoints to routes.py**

在 `backend/engine/industry/routes.py` 末尾追加以下代码（不修改现有端点）：

```python
# ── 产业链推演端点 ──────────────────────────────────────

from .chain_schemas import ChainExploreRequest


@router.post("/chain/explore")
async def chain_explore(req: ChainExploreRequest):
    """产业链物理约束推演（SSE 流式推送图谱生长过程）

    事件类型：
    - explore_start: 探索开始
    - depth_start: 某层开始展开
    - nodes_discovered: 发现新节点
    - links_discovered: 发现新边
    - explore_complete: 探索完成
    - error: 错误
    """
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置，无法进行产业链推演"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm)

    async def event_stream():
        try:
            async for event in agent.explore(req):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"产业链推演失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(type(e).__name__)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class _ChainExpandRequest(BaseModel):
    event: str
    node_name: str
    existing_nodes: list[str] = []


@router.post("/chain/expand")
async def chain_expand_node(req: _ChainExpandRequest):
    """交互式展开单个节点（用户双击触发）"""
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm)

    expand_req = ChainExploreRequest(
        event=req.event,
        start_node=req.node_name,
        max_depth=1,
    )

    async def event_stream():
        try:
            async for event in agent.explore(expand_req):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"节点展开失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(type(e).__name__)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

注意：需要在 routes.py 顶部追加 `BaseModel` 导入（如果还没有的话）：在已有的 `from .schemas import IndustryAnalysisRequest` 旁边确认 `from pydantic import BaseModel` 存在。

**Step 4: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_routes.py -v`
Expected: Tests PASS (endpoints return non-404)

**Step 5: Commit**

```bash
git add backend/engine/industry/routes.py tests/test_chain_routes.py
git commit -m "feat(chain): add SSE endpoints for chain explore and expand"
```

---

## Task 4: 前端类型定义 + Zustand Store

**Files:**
- Create: `frontend/types/chain.ts`
- Create: `frontend/stores/useChainStore.ts`

**Step 1: Create type definitions**

```typescript
// frontend/types/chain.ts

/** 产业环节的物理约束 */
export interface PhysicalConstraint {
  node: string;
  shutdown_recovery_time: string;
  restart_cost: string;
  capacity_ramp_curve: string;
  capacity_ceiling: string;
  expansion_lead_time: string;
  logistics_mode: string;
  logistics_bottleneck: string;
  logistics_vulnerability: string;
  substitution_path: string;
  switching_cost: string;
  switching_time: string;
  inventory_buffer_days: string;
  strategic_reserve: string;
  import_dependency: string;
  export_ratio: string;
  key_trade_routes: string;
}

/** 产业链图谱节点 */
export interface ChainNode {
  id: string;
  name: string;
  node_type: "material" | "industry" | "company" | "event" | "logistics";
  impact: "benefit" | "hurt" | "neutral" | "source";
  impact_score: number;
  depth: number;
  representative_stocks: string[];
  constraint: PhysicalConstraint | null;
  summary: string;
  // react-force-graph 需要的位置字段（可选）
  x?: number;
  y?: number;
  fx?: number; // 固定位置（拖拽后）
  fy?: number;
}

/** 产业链传导边 */
export interface ChainLink {
  source: string; // 节点 name
  target: string;
  relation: string;
  impact: "positive" | "negative" | "neutral";
  impact_reason: string;
  confidence: number;
  transmission_speed: string;
  transmission_strength: string;
  transmission_mechanism: string;
  dampening_factors: string[];
  amplifying_factors: string[];
  constraint: PhysicalConstraint | null;
}

/** SSE 事件 */
export interface ChainSSEEvent {
  event: string;
  data: Record<string, unknown>;
}

/** 探索状态 */
export type ExploreStatus = "idle" | "exploring" | "expanding" | "done" | "error";

/** 节点颜色映射 */
export const IMPACT_COLORS: Record<string, string> = {
  benefit: "#22c55e",   // 绿色 — 利好
  hurt: "#ef4444",      // 红色 — 利空
  neutral: "#94a3b8",   // 灰色 — 中性
  source: "#3b82f6",    // 蓝色 — 事件源
};

/** 节点类型图标映射（lucide icon name） */
export const NODE_TYPE_ICONS: Record<string, string> = {
  material: "⚗️",
  industry: "🏭",
  company: "🏢",
  event: "⚡",
  logistics: "🚢",
};
```

**Step 2: Create Zustand store**

```typescript
// frontend/stores/useChainStore.ts

import { create } from "zustand";
import type { ChainNode, ChainLink, ExploreStatus } from "@/types/chain";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

interface ChainStore {
  // ── 状态 ──
  nodes: ChainNode[];
  links: ChainLink[];
  status: ExploreStatus;
  currentEvent: string;
  currentDepth: number;
  maxDepth: number;
  error: string | null;
  selectedNode: ChainNode | null;
  expandingNodes: string[];  // 正在展开的节点名列表

  // ── 操作 ──
  explore: (event: string, maxDepth?: number, focusArea?: string) => Promise<void>;
  expandNode: (nodeName: string) => Promise<void>;
  selectNode: (node: ChainNode | null) => void;
  setMaxDepth: (depth: number) => void;
  reset: () => void;

  // ── 内部 ──
  _abortController: AbortController | null;
}

export const useChainStore = create<ChainStore>((set, get) => ({
  nodes: [],
  links: [],
  status: "idle",
  currentEvent: "",
  currentDepth: 0,
  maxDepth: 3,
  error: null,
  selectedNode: null,
  expandingNodes: [],
  _abortController: null,

  explore: async (event, maxDepth, focusArea) => {
    // 取消之前的请求
    const prev = get()._abortController;
    if (prev) prev.abort();

    const controller = new AbortController();
    set({
      nodes: [],
      links: [],
      status: "exploring",
      currentEvent: event,
      currentDepth: 0,
      maxDepth: maxDepth || get().maxDepth,
      error: null,
      selectedNode: null,
      _abortController: controller,
    });

    try {
      const res = await fetch(`${API_BASE}/api/v1/industry/chain/explore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event,
          max_depth: maxDepth || get().maxDepth,
          focus_area: focusArea || "",
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        set({ status: "error", error: `HTTP ${res.status}` });
        return;
      }

      await _parseSSE(res, set, get);
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      set({ status: "error", error: (e as Error).message });
    }
  },

  expandNode: async (nodeName) => {
    const { currentEvent, nodes, expandingNodes } = get();
    if (!currentEvent || expandingNodes.includes(nodeName)) return;

    set({ status: "expanding", expandingNodes: [...expandingNodes, nodeName] });

    try {
      const res = await fetch(`${API_BASE}/api/v1/industry/chain/expand`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event: currentEvent,
          node_name: nodeName,
          existing_nodes: nodes.map((n) => n.name),
        }),
      });

      if (!res.ok) {
        set((s) => ({
          status: "done",
          expandingNodes: s.expandingNodes.filter((n) => n !== nodeName),
        }));
        return;
      }

      await _parseSSE(res, set, get, true);
      set((s) => ({
        status: "done",
        expandingNodes: s.expandingNodes.filter((n) => n !== nodeName),
      }));
    } catch (e: unknown) {
      set((s) => ({
        status: "done",
        error: (e as Error).message,
        expandingNodes: s.expandingNodes.filter((n) => n !== nodeName),
      }));
    }
  },

  selectNode: (node) => set({ selectedNode: node }),
  setMaxDepth: (depth) => set({ maxDepth: depth }),

  reset: () => {
    const prev = get()._abortController;
    if (prev) prev.abort();
    set({
      nodes: [],
      links: [],
      status: "idle",
      currentEvent: "",
      currentDepth: 0,
      error: null,
      selectedNode: null,
      expandingNodes: [],
      _abortController: null,
    });
  },
}));


/** 解析 SSE 流并更新 store */
async function _parseSSE(
  res: Response,
  set: (partial: Partial<ChainStore> | ((s: ChainStore) => Partial<ChainStore>)) => void,
  get: () => ChainStore,
  isExpand = false,
) {
  const reader = res.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const eventBlock of events) {
      const lines = eventBlock.split("\n");
      let eventType = "";
      let eventData = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        if (line.startsWith("data: ")) eventData = line.slice(6).trim();
      }
      if (!eventType || !eventData) continue;

      try {
        const parsed = JSON.parse(eventData);

        switch (eventType) {
          case "depth_start":
            set({ currentDepth: parsed.depth || 0 });
            break;

          case "nodes_discovered": {
            const newNodes: ChainNode[] = (parsed.nodes || []).map((n: ChainNode) => ({
              ...n,
              id: n.id || `n_${n.name}`,
            }));
            set((s) => {
              const existingNames = new Set(s.nodes.map((n) => n.name));
              const unique = newNodes.filter((n) => !existingNames.has(n.name));
              return { nodes: [...s.nodes, ...unique] };
            });
            break;
          }

          case "links_discovered": {
            const newLinks: ChainLink[] = parsed.links || [];
            set((s) => ({ links: [...s.links, ...newLinks] }));
            break;
          }

          case "explore_complete":
            if (!isExpand) {
              set({ status: "done" });
            }
            break;

          case "error":
            set({ error: parsed.message || "未知错误" });
            break;
        }
      } catch {
        // JSON 解析失败，跳过
      }
    }
  }
}
```

**Step 3: Commit**

```bash
git add frontend/types/chain.ts frontend/stores/useChainStore.ts
git commit -m "feat(chain): add frontend types and Zustand store with SSE parsing"
```

---

## Task 5: 安装 react-force-graph-2d 依赖

**Step 1: Install dependency**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/frontend && npm install react-force-graph-2d
```

**Step 2: Verify installation**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/frontend && node -e "require('react-force-graph-2d')" 2>&1 || echo "ESM module, checking package..."
ls node_modules/react-force-graph-2d/package.json
```

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "deps: add react-force-graph-2d for chain visualization"
```

---

## Task 6: 前端核心组件 — ChainGraph 力导向图

**Files:**
- Create: `frontend/components/chain/ChainGraph.tsx`

**Step 1: Create the force-directed graph component**

```tsx
// frontend/components/chain/ChainGraph.tsx
"use client";

import { useCallback, useEffect, useRef, useMemo } from "react";
import { useChainStore } from "@/stores/useChainStore";
import { IMPACT_COLORS, NODE_TYPE_ICONS } from "@/types/chain";
import type { ChainNode, ChainLink } from "@/types/chain";
import dynamic from "next/dynamic";

// react-force-graph-2d 依赖 window，需要动态导入
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
      加载图谱引擎...
    </div>
  ),
});

/** 将 ChainLink[] 转为 react-force-graph 需要的 { source, target } 格式 */
function buildGraphData(nodes: ChainNode[], links: ChainLink[]) {
  const nodeMap = new Map(nodes.map((n) => [n.name, n]));

  const graphLinks = links
    .filter((l) => nodeMap.has(l.source) && nodeMap.has(l.target))
    .map((l) => ({
      source: `n_${l.source}`,
      target: `n_${l.target}`,
      ...l,
    }));

  const graphNodes = nodes.map((n) => ({
    ...n,
    id: `n_${n.name}`,
  }));

  return { nodes: graphNodes, links: graphLinks };
}

export default function ChainGraph() {
  const { nodes, links, status, selectedNode, selectNode, expandNode } =
    useChainStore();
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const graphData = useMemo(() => buildGraphData(nodes, links), [nodes, links]);

  // 自适应画布大小
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 新节点加入时 zoom to fit
  useEffect(() => {
    if (graphRef.current && nodes.length > 0) {
      setTimeout(() => graphRef.current?.zoomToFit(400, 60), 300);
    }
  }, [nodes.length]);

  // ── 节点绘制 ──
  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.name || "";
      const impact = node.impact || "neutral";
      const nodeType = node.node_type || "industry";
      const isSelected = selectedNode?.name === node.name;
      const size = isSelected ? 8 : 6;

      // 节点圆
      ctx.beginPath();
      ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
      ctx.fillStyle = IMPACT_COLORS[impact] || IMPACT_COLORS.neutral;
      ctx.fill();

      // 选中高亮环
      if (isSelected) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // 标签（缩放到足够大时才显示）
      if (globalScale > 0.6) {
        const icon = NODE_TYPE_ICONS[nodeType] || "";
        const fontSize = Math.max(12 / globalScale, 3);
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "rgba(226, 232, 240, 0.9)";
        ctx.fillText(`${icon} ${label}`, node.x, node.y + size + 2);
      }
    },
    [selectedNode],
  );

  // ── 边绘制 ──
  const paintLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const impact = link.impact || "neutral";
      const strength = link.transmission_strength || "";

      // 颜色
      const color =
        impact === "negative"
          ? "rgba(239, 68, 68, 0.4)"
          : impact === "positive"
            ? "rgba(34, 197, 94, 0.4)"
            : "rgba(148, 163, 184, 0.3)";

      // 线宽：强刚性粗、弱弹性细
      const width = strength.includes("强") ? 2.5 : strength.includes("弱") ? 0.8 : 1.5;

      const source = link.source;
      const target = link.target;
      if (!source.x || !target.x) return;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.strokeStyle = color;
      ctx.lineWidth = width / globalScale;

      // 虚线表示替代关系
      if (link.relation === "substitute" || link.relation === "competes") {
        ctx.setLineDash([4 / globalScale, 4 / globalScale]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // 箭头
      const angle = Math.atan2(target.y - source.y, target.x - source.x);
      const arrowLen = 6 / globalScale;
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2;
      ctx.beginPath();
      ctx.moveTo(midX, midY);
      ctx.lineTo(
        midX - arrowLen * Math.cos(angle - Math.PI / 6),
        midY - arrowLen * Math.sin(angle - Math.PI / 6),
      );
      ctx.moveTo(midX, midY);
      ctx.lineTo(
        midX - arrowLen * Math.cos(angle + Math.PI / 6),
        midY - arrowLen * Math.sin(angle + Math.PI / 6),
      );
      ctx.strokeStyle = color;
      ctx.stroke();
    },
    [],
  );

  // ── 事件处理 ──
  const handleNodeClick = useCallback(
    (node: any) => {
      const chainNode = nodes.find((n) => n.name === node.name);
      selectNode(chainNode || null);
    },
    [nodes, selectNode],
  );

  const handleNodeDoubleClick = useCallback(
    (node: any) => {
      expandNode(node.name);
    },
    [expandNode],
  );

  return (
    <div ref={containerRef} className="relative w-full h-full">
      {graphData.nodes.length > 0 ? (
        <ForceGraph2D
          ref={graphRef}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          nodeCanvasObject={paintNode}
          linkCanvasObject={paintLink}
          onNodeClick={handleNodeClick}
          onNodeDragEnd={(node: any) => {
            node.fx = node.x;
            node.fy = node.y;
          }}
          onNodeRightClick={(node: any) => {
            node.fx = undefined;
            node.fy = undefined;
          }}
          cooldownTicks={100}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          backgroundColor="transparent"
        />
      ) : (
        <div className="flex items-center justify-center h-full text-[var(--text-secondary)]">
          {status === "idle"
            ? "输入事件开始探索产业链"
            : status === "exploring"
              ? "正在推演..."
              : "暂无数据"}
        </div>
      )}

      {/* 双击提示 */}
      {nodes.length > 0 && (
        <div className="absolute bottom-4 left-4 text-xs text-[var(--text-secondary)] opacity-60">
          💡 单击节点查看详情 · 双击继续展开 · 右键取消固定
        </div>
      )}
    </div>
  );
}
```

注意：文件中需要额外加上 `import { useState } from "react";` 在顶部 import 列表中（与 useCallback, useEffect, useRef, useMemo 并列）。

**Step 2: Commit**

```bash
git add frontend/components/chain/ChainGraph.tsx
git commit -m "feat(chain): add ChainGraph force-directed visualization component"
```

---

## Task 7: 前端辅助组件 — 搜索栏 + 详情面板 + 状态指示

**Files:**
- Create: `frontend/components/chain/ChainToolbar.tsx`
- Create: `frontend/components/chain/NodeDetail.tsx`
- Create: `frontend/components/chain/ChainStatusBar.tsx`

**Step 1: Create ChainToolbar (search + controls)**

```tsx
// frontend/components/chain/ChainToolbar.tsx
"use client";

import { useState, useCallback } from "react";
import { Search, Play, RotateCcw } from "lucide-react";
import { useChainStore } from "@/stores/useChainStore";

export default function ChainToolbar() {
  const { explore, reset, status, maxDepth, setMaxDepth } = useChainStore();
  const [input, setInput] = useState("");

  const handleExplore = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) return;
    explore(trimmed, maxDepth);
  }, [input, explore, maxDepth]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleExplore();
      }
    },
    [handleExplore],
  );

  const isLoading = status === "exploring" || status === "expanding";

  return (
    <div
      className="flex items-center gap-3 px-5 py-3 border-b border-[var(--border)]"
      style={{ background: "var(--bg-secondary)" }}
    >
      {/* 搜索输入 */}
      <div className="flex items-center flex-1 gap-2 px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
        <Search size={16} className="text-[var(--text-secondary)] shrink-0" />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入事件（如：石油涨价、美联储加息、台风登陆）"
          className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] outline-none"
          disabled={isLoading}
        />
      </div>

      {/* 深度选择 */}
      <div className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
        <span>深度:</span>
        {[2, 3, 4].map((d) => (
          <button
            key={d}
            onClick={() => setMaxDepth(d)}
            className={`w-7 h-7 rounded-md text-center transition-colors
              ${maxDepth === d
                ? "bg-[var(--accent)] text-white"
                : "bg-[var(--bg-primary)] hover:bg-[var(--border)]"
              }`}
            disabled={isLoading}
          >
            {d}
          </button>
        ))}
      </div>

      {/* 探索按钮 */}
      <button
        onClick={handleExplore}
        disabled={isLoading || !input.trim()}
        className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium
                   bg-[var(--accent)] text-white hover:opacity-90
                   disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
      >
        <Play size={14} />
        {isLoading ? "推演中..." : "探索"}
      </button>

      {/* 重置按钮 */}
      <button
        onClick={reset}
        className="p-2 rounded-lg hover:bg-[var(--bg-primary)] text-[var(--text-secondary)] transition-colors"
        title="重置"
      >
        <RotateCcw size={16} />
      </button>
    </div>
  );
}
```

**Step 2: Create NodeDetail panel**

```tsx
// frontend/components/chain/NodeDetail.tsx
"use client";

import { X, ArrowUpRight, ArrowDownRight, Truck, Factory, Clock, Package, Globe } from "lucide-react";
import { useChainStore } from "@/stores/useChainStore";
import { IMPACT_COLORS, NODE_TYPE_ICONS } from "@/types/chain";

export default function NodeDetail() {
  const { selectedNode, selectNode, links } = useChainStore();

  if (!selectedNode) return null;

  const constraint = selectedNode.constraint;
  const relatedLinks = links.filter(
    (l) => l.source === selectedNode.name || l.target === selectedNode.name,
  );

  return (
    <div
      className="absolute right-0 top-0 h-full w-[380px] border-l border-[var(--border)]
                 overflow-y-auto z-10"
      style={{ background: "var(--bg-secondary)" }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <span className="text-lg">
            {NODE_TYPE_ICONS[selectedNode.node_type] || "📍"}
          </span>
          <span className="text-base font-semibold text-[var(--text-primary)]">
            {selectedNode.name}
          </span>
          <span
            className="px-2 py-0.5 rounded-full text-xs font-medium"
            style={{
              background: `${IMPACT_COLORS[selectedNode.impact]}20`,
              color: IMPACT_COLORS[selectedNode.impact],
            }}
          >
            {selectedNode.impact === "benefit"
              ? "利好"
              : selectedNode.impact === "hurt"
                ? "利空"
                : selectedNode.impact === "source"
                  ? "事件源"
                  : "中性"}
          </span>
        </div>
        <button
          onClick={() => selectNode(null)}
          className="p-1 rounded hover:bg-[var(--bg-primary)] text-[var(--text-secondary)]"
        >
          <X size={16} />
        </button>
      </div>

      {/* 摘要 */}
      {selectedNode.summary && (
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <p className="text-sm text-[var(--text-primary)] leading-relaxed">
            {selectedNode.summary}
          </p>
        </div>
      )}

      {/* 代表性股票 */}
      {selectedNode.representative_stocks.length > 0 && (
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <h4 className="text-xs font-semibold text-[var(--text-secondary)] mb-2">
            📈 代表性A股
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {selectedNode.representative_stocks.map((code) => (
              <span
                key={code}
                className="px-2 py-0.5 rounded bg-[var(--bg-primary)] text-xs text-[var(--accent)] font-mono"
              >
                {code}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 物理约束（核心！） */}
      {constraint && (
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <h4 className="text-xs font-semibold text-[var(--text-secondary)] mb-3">
            🔬 物理约束
          </h4>
          <div className="space-y-2.5">
            <ConstraintItem
              icon={<Clock size={13} />}
              label="停产恢复"
              value={constraint.shutdown_recovery_time}
            />
            <ConstraintItem
              icon={<Factory size={13} />}
              label="产能天花板"
              value={constraint.capacity_ceiling}
            />
            <ConstraintItem
              icon={<Factory size={13} />}
              label="扩产周期"
              value={constraint.expansion_lead_time}
            />
            <ConstraintItem
              icon={<Truck size={13} />}
              label="运输方式"
              value={constraint.logistics_mode}
            />
            <ConstraintItem
              icon={<Truck size={13} />}
              label="物流瓶颈"
              value={constraint.logistics_bottleneck}
            />
            <ConstraintItem
              icon={<Package size={13} />}
              label="库存缓冲"
              value={constraint.inventory_buffer_days}
            />
            <ConstraintItem
              icon={<Globe size={13} />}
              label="进口依存度"
              value={constraint.import_dependency}
            />
            <ConstraintItem
              icon={<Globe size={13} />}
              label="关键贸易路线"
              value={constraint.key_trade_routes}
            />
            <ConstraintItem
              icon={<ArrowUpRight size={13} />}
              label="替代路径"
              value={constraint.substitution_path}
            />
            <ConstraintItem
              icon={<ArrowDownRight size={13} />}
              label="切换成本"
              value={constraint.switching_cost}
            />
          </div>
        </div>
      )}

      {/* 传导关系 */}
      {relatedLinks.length > 0 && (
        <div className="px-4 py-3">
          <h4 className="text-xs font-semibold text-[var(--text-secondary)] mb-3">
            🔗 传导关系
          </h4>
          <div className="space-y-2">
            {relatedLinks.map((link, i) => (
              <div
                key={i}
                className="p-2.5 rounded-lg bg-[var(--bg-primary)] text-xs"
              >
                <div className="flex items-center gap-1 mb-1">
                  <span className="text-[var(--text-primary)] font-medium">
                    {link.source}
                  </span>
                  <span className="text-[var(--text-secondary)]">→</span>
                  <span className="text-[var(--text-primary)] font-medium">
                    {link.target}
                  </span>
                  <span
                    className="ml-auto px-1.5 py-0.5 rounded text-[10px]"
                    style={{
                      background:
                        link.impact === "negative"
                          ? "rgba(239,68,68,0.15)"
                          : link.impact === "positive"
                            ? "rgba(34,197,94,0.15)"
                            : "rgba(148,163,184,0.15)",
                      color:
                        link.impact === "negative"
                          ? "#ef4444"
                          : link.impact === "positive"
                            ? "#22c55e"
                            : "#94a3b8",
                    }}
                  >
                    {link.transmission_strength || link.relation}
                  </span>
                </div>
                <p className="text-[var(--text-secondary)] leading-relaxed">
                  {link.impact_reason}
                </p>
                {link.transmission_speed && (
                  <div className="mt-1.5 flex gap-2 text-[10px] text-[var(--text-secondary)]">
                    <span>⏱ {link.transmission_speed}</span>
                    <span>📡 {link.transmission_mechanism}</span>
                  </div>
                )}
                {(link.dampening_factors.length > 0 ||
                  link.amplifying_factors.length > 0) && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {link.dampening_factors.map((f, j) => (
                      <span
                        key={`d${j}`}
                        className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[10px]"
                      >
                        🛡 {f}
                      </span>
                    ))}
                    {link.amplifying_factors.map((f, j) => (
                      <span
                        key={`a${j}`}
                        className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 text-[10px]"
                      >
                        🔥 {f}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 约束条目组件 */
function ConstraintItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 text-[var(--text-secondary)]">{icon}</span>
      <div>
        <span className="text-[10px] text-[var(--text-secondary)]">{label}</span>
        <p className="text-xs text-[var(--text-primary)] leading-relaxed">{value}</p>
      </div>
    </div>
  );
}
```

**Step 3: Create ChainStatusBar**

```tsx
// frontend/components/chain/ChainStatusBar.tsx
"use client";

import { useChainStore } from "@/stores/useChainStore";
import { Loader2 } from "lucide-react";

export default function ChainStatusBar() {
  const { status, nodes, links, currentDepth, maxDepth, currentEvent, error } =
    useChainStore();

  if (status === "idle") return null;

  return (
    <div
      className="flex items-center gap-3 px-5 py-2 text-xs border-t border-[var(--border)]"
      style={{ background: "var(--bg-secondary)" }}
    >
      {(status === "exploring" || status === "expanding") && (
        <Loader2 size={12} className="animate-spin text-[var(--accent)]" />
      )}

      <span className="text-[var(--text-secondary)]">
        {status === "exploring"
          ? `🔄 正在推演「${currentEvent}」第 ${currentDepth}/${maxDepth} 层...`
          : status === "expanding"
            ? "🔄 正在展开节点..."
            : status === "done"
              ? `✅ 推演完成`
              : status === "error"
                ? `❌ 出错`
                : ""}
      </span>

      <span className="text-[var(--text-secondary)]">
        {nodes.length} 个节点 · {links.length} 条传导边
      </span>

      {error && (
        <span className="text-red-400 ml-auto">{error}</span>
      )}
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add frontend/components/chain/ChainToolbar.tsx frontend/components/chain/NodeDetail.tsx frontend/components/chain/ChainStatusBar.tsx
git commit -m "feat(chain): add toolbar, node detail panel, and status bar"
```

---

## Task 8: 前端页面路由 + 导航注册

**Files:**
- Create: `frontend/app/chain/page.tsx`
- Modify: `frontend/components/ui/NavSidebar.tsx` (添加导航项)

**Step 1: Create the chain page**

```tsx
// frontend/app/chain/page.tsx
"use client";

import NavSidebar from "@/components/ui/NavSidebar";
import ChainToolbar from "@/components/chain/ChainToolbar";
import ChainStatusBar from "@/components/chain/ChainStatusBar";
import NodeDetail from "@/components/chain/NodeDetail";
import dynamic from "next/dynamic";

const ChainGraph = dynamic(() => import("@/components/chain/ChainGraph"), {
  ssr: false,
});

export default function ChainPageRoute() {
  return (
    <main
      className="debate-dark relative h-screen flex flex-col overflow-hidden"
      style={{
        marginLeft: 48,
        width: "calc(100vw - 48px)",
        background: "var(--bg-primary)",
      }}
    >
      <NavSidebar />

      {/* 顶部搜索栏 */}
      <ChainToolbar />

      {/* 图谱区域 + 详情面板 */}
      <div className="flex-1 relative overflow-hidden">
        <ChainGraph />
        <NodeDetail />
      </div>

      {/* 底部状态栏 */}
      <ChainStatusBar />
    </main>
  );
}
```

**Step 2: Add navigation item to NavSidebar**

在 `frontend/components/ui/NavSidebar.tsx` 的 `NAV_ITEMS` 数组中，在最后一项 `sector` 之后添加：

```tsx
// 在 import 列表中添加 GitBranch（或 Network）图标
import { Mountain, Scale, BrainCircuit, TrendingUp, ClipboardList, GitBranch } from "lucide-react";

// 在 NAV_ITEMS 数组末尾添加：
{ href: "/chain", icon: GitBranch, label: "产业链图谱" },
```

**Step 3: Verify the page renders**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/frontend && npm run dev`
Open: `http://localhost:3000/chain`
Expected: 暗色页面，顶部有搜索栏和深度选择，中间显示"输入事件开始探索产业链"，左侧导航栏有新的"产业链图谱"入口。

**Step 4: Commit**

```bash
git add frontend/app/chain/page.tsx frontend/components/ui/NavSidebar.tsx
git commit -m "feat(chain): add /chain page route with navigation"
```

---

## Task 9: 端到端集成测试

**Files:**
- Test: `tests/test_chain_integration.py`

**Step 1: Write integration test**

```python
# tests/test_chain_integration.py
"""产业链推演端到端集成测试"""
import json
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

# Mock LLM 响应
MOCK_RESPONSE = json.dumps({
    "nodes": [
        {"name": "石油", "node_type": "material", "impact": "source", "impact_score": 0.0,
         "summary": "事件源", "representative_stocks": [],
         "constraint": {"node": "石油", "import_dependency": "中国原油对外依存度72%"}},
        {"name": "乙烯", "node_type": "material", "impact": "hurt", "impact_score": -0.7,
         "summary": "成本上升", "representative_stocks": ["600028"],
         "constraint": {"node": "乙烯裂解", "shutdown_recovery_time": "2-4周"}},
    ],
    "links": [
        {"source": "石油", "target": "乙烯", "relation": "upstream", "impact": "negative",
         "impact_reason": "石油是乙烯核心原料", "confidence": 0.9,
         "transmission_speed": "即时", "transmission_strength": "强刚性",
         "transmission_mechanism": "成本推动",
         "dampening_factors": ["期货套保"], "amplifying_factors": ["集中度高"]},
    ],
    "expand_candidates": ["乙烯"],
}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_chain_explore_sse_flow():
    """验证 SSE 事件流完整性"""
    # Mock LLM
    mock_llm = MagicMock()
    async def fake_stream(messages):
        for char in MOCK_RESPONSE:
            yield char
    mock_llm.chat_stream = fake_stream

    # Mock get_industry_engine
    mock_engine = MagicMock()
    mock_engine._llm = mock_llm

    with patch("engine.industry.routes.get_industry_engine", return_value=mock_engine):
        with patch("engine.industry.chain_agent.ChainAgent.__init__", return_value=None):
            with patch.object(
                __import__("engine.industry.chain_agent", fromlist=["ChainAgent"]).ChainAgent,
                "explore",
            ) as mock_explore:
                # 设置 explore 返回预定义事件
                async def fake_explore(req):
                    yield {"event": "explore_start", "data": {"event": req.event, "max_depth": req.max_depth}}
                    yield {"event": "nodes_discovered", "data": {"depth": 1, "nodes": [{"name": "石油"}]}}
                    yield {"event": "explore_complete", "data": {"event": req.event, "nodes": [], "links": [], "depth_reached": 1}}
                mock_explore.side_effect = fake_explore

                from main import app
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/v1/industry/chain/explore",
                        json={"event": "石油涨价", "max_depth": 2},
                    )
                    assert resp.status_code == 200
                    assert "text/event-stream" in resp.headers.get("content-type", "")
```

**Step 2: Run integration test**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_chain_integration.py
git commit -m "test(chain): add end-to-end integration test"
```

---

## Task 10: 图例组件 + 视觉优化

**Files:**
- Create: `frontend/components/chain/ChainLegend.tsx`
- Modify: `frontend/app/chain/page.tsx` (添加图例)

**Step 1: Create legend component**

```tsx
// frontend/components/chain/ChainLegend.tsx
"use client";

import { IMPACT_COLORS } from "@/types/chain";

const LEGEND_ITEMS = [
  { color: IMPACT_COLORS.source, label: "事件源", shape: "circle" },
  { color: IMPACT_COLORS.benefit, label: "利好", shape: "circle" },
  { color: IMPACT_COLORS.hurt, label: "利空", shape: "circle" },
  { color: IMPACT_COLORS.neutral, label: "中性", shape: "circle" },
];

const EDGE_LEGEND = [
  { style: "solid", width: 2.5, label: "强刚性传导" },
  { style: "solid", width: 1, label: "中等传导" },
  { style: "dashed", width: 1, label: "替代/竞争" },
];

export default function ChainLegend() {
  return (
    <div
      className="absolute top-4 left-4 p-3 rounded-xl border border-[var(--border)] z-10
                 backdrop-blur-md text-xs"
      style={{ background: "rgba(15, 23, 42, 0.8)" }}
    >
      <div className="text-[10px] font-semibold text-[var(--text-secondary)] mb-2">
        图例
      </div>
      <div className="space-y-1.5">
        {LEGEND_ITEMS.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className="w-3 h-3 rounded-full shrink-0"
              style={{ background: color }}
            />
            <span className="text-[var(--text-secondary)]">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 pt-2 border-t border-[var(--border)] space-y-1.5">
        {EDGE_LEGEND.map(({ style, width, label }) => (
          <div key={label} className="flex items-center gap-2">
            <svg width="20" height="8" className="shrink-0">
              <line
                x1="0" y1="4" x2="20" y2="4"
                stroke="rgba(148,163,184,0.6)"
                strokeWidth={width}
                strokeDasharray={style === "dashed" ? "3,3" : "none"}
              />
            </svg>
            <span className="text-[var(--text-secondary)]">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Add legend to chain page**

在 `frontend/app/chain/page.tsx` 中，在图谱区域内添加 `<ChainLegend />`：

```tsx
import ChainLegend from "@/components/chain/ChainLegend";

// 在 <div className="flex-1 relative overflow-hidden"> 内添加：
<ChainLegend />
```

**Step 3: Commit**

```bash
git add frontend/components/chain/ChainLegend.tsx frontend/app/chain/page.tsx
git commit -m "feat(chain): add graph legend and visual polish"
```

---

## 文件清单汇总

### 新建文件（10个）

| 文件 | 用途 |
|------|------|
| `backend/engine/industry/chain_schemas.py` | 物理约束数据结构 |
| `backend/engine/industry/chain_agent.py` | 产业物理学家 LLM 推演引擎 |
| `frontend/types/chain.ts` | 前端类型定义 |
| `frontend/stores/useChainStore.ts` | Zustand 状态管理 + SSE 解析 |
| `frontend/app/chain/page.tsx` | 产业链图谱页面路由 |
| `frontend/components/chain/ChainGraph.tsx` | 力导向图核心组件 |
| `frontend/components/chain/ChainToolbar.tsx` | 搜索栏 + 控制面板 |
| `frontend/components/chain/NodeDetail.tsx` | 节点详情面板（含物理约束） |
| `frontend/components/chain/ChainStatusBar.tsx` | 底部状态指示 |
| `frontend/components/chain/ChainLegend.tsx` | 图例组件 |

### 修改文件（1个）

| 文件 | 改动 |
|------|------|
| `frontend/components/ui/NavSidebar.tsx` | 添加 `/chain` 导航项 |
| `backend/engine/industry/routes.py` | 追加 2 个 SSE 端点 |

### 测试文件（3个）

| 文件 | 覆盖 |
|------|------|
| `tests/test_chain_schemas.py` | Schema 结构 + 验证 |
| `tests/test_chain_agent.py` | Agent 推演 + 去重 |
| `tests/test_chain_integration.py` | SSE 端到端流 |
