# 产业链沙盘 v2 — 完整实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将产业链沙盘从"固定深度一次构建"升级为"一切皆节点、按需拓展、冲击瞬间传播、宏观万物皆可建模"的交互体验。

**Architecture:** 前端以纯算法实现冲击传播（<50ms 响应），后端新增智能拆解/按需拓展/添加节点等接口。输入框支持自由文本，后端用 LLM 拆解为节点列表后逐个加入图中并发拓展。节点类型扩展支持 macro（宏观因素）和 commodity（大宗商品）。

**Tech Stack:** Python/FastAPI（后端）, TypeScript/Next.js/Zustand（前端）, react-force-graph-2d（图可视化）, SSE（流式推送）

---

## 改造概览

| # | 改造 | 核心变化 |
|---|------|---------|
| 1 | 按需拓展 | 去掉固定深度选择器，初始只建1层，双击展开，全局扩展，手动添加节点 |
| 2 | 冲击瞬间传播 | 前端纯算法 BFS 传播（<50ms），保留 LLM 深度解读作为可选 |
| 3 | 万物皆节点 | 输入任何文本 → LLM 拆解为节点列表 → 逐个加入图并发拓展 → 自动发现关系 |
| 4 | 拓展视觉反馈 | 环形进度条动画、展开完成闪光、新节点弹出效果 |

---

## Task 1: 后端 — 智能文本拆解接口

**Files:**
- Create: `backend/engine/industry/chain_parser.py`
- Test: `tests/test_chain_parser.py`

### 核心设计

用户输入任何文本（"黄金与石油的关系"、"美联储加息对新兴市场的影响"、"宁德时代"），后端用 LLM 拆解为结构化节点列表。

```python
# chain_parser.py
PARSE_INPUT_PROMPT = """你是一个产业链分析助手。用户输入了一段文本，请拆解为独立的分析节点。

## 用户输入
{user_input}

## 规则
1. 将输入拆解为 1~5 个独立的分析节点
2. 每个节点是一个可以独立存在于产业链图中的实体
3. 如果输入就是单个实体（如"宁德时代"），返回 1 个节点
4. 如果输入包含关系描述（如"黄金与石油的关系"），拆解为多个独立实体节点
5. 如果输入是宏观事件（如"美联储加息"），把它当作一个事件节点
6. 每个节点判断类型：company/material/industry/macro/commodity/event

## 示例
输入："黄金与石油的关系"
输出：{{"nodes": [{{"name": "黄金", "type": "commodity"}}, {{"name": "石油", "type": "commodity"}}]}}

输入："美联储加息对新兴市场的影响"
输出：{{"nodes": [{{"name": "美联储加息", "type": "macro"}}, {{"name": "新兴市场", "type": "industry"}}]}}

输入："宁德时代"
输出：{{"nodes": [{{"name": "宁德时代", "type": "company"}}]}}

输入："战争频繁 vs 和平时期"
输出：{{"nodes": [{{"name": "地缘冲突", "type": "macro"}}, {{"name": "和平红利", "type": "macro"}}]}}

## 输出格式
直接输出 JSON：
{{"nodes": [{{"name": "...", "type": "company|material|industry|macro|commodity|event"}}]}}
"""
```

### Step 1: Write the failing test

```python
# tests/test_chain_parser.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_parse_single_entity():
    """单实体输入 → 返回1个节点"""
    from engine.industry.chain_parser import ChainInputParser
    
    mock_llm = MagicMock()
    mock_llm.chat_stream = AsyncMock(return_value=_async_iter(
        '{"nodes": [{"name": "宁德时代", "type": "company"}]}'
    ))
    
    parser = ChainInputParser(mock_llm)
    result = await parser.parse("宁德时代")
    
    assert len(result) == 1
    assert result[0]["name"] == "宁德时代"
    assert result[0]["type"] == "company"

@pytest.mark.asyncio
async def test_parse_relationship_input():
    """关系型输入 → 拆解为多个节点"""
    from engine.industry.chain_parser import ChainInputParser
    
    mock_llm = MagicMock()
    mock_llm.chat_stream = AsyncMock(return_value=_async_iter(
        '{"nodes": [{"name": "黄金", "type": "commodity"}, {"name": "石油", "type": "commodity"}]}'
    ))
    
    parser = ChainInputParser(mock_llm)
    result = await parser.parse("黄金与石油的关系")
    
    assert len(result) == 2
    names = {n["name"] for n in result}
    assert "黄金" in names
    assert "石油" in names

@pytest.mark.asyncio  
async def test_parse_macro_event():
    """宏观事件输入"""
    from engine.industry.chain_parser import ChainInputParser
    
    mock_llm = MagicMock()
    mock_llm.chat_stream = AsyncMock(return_value=_async_iter(
        '{"nodes": [{"name": "美联储加息", "type": "macro"}, {"name": "新兴市场", "type": "industry"}]}'
    ))
    
    parser = ChainInputParser(mock_llm)
    result = await parser.parse("美联储加息对新兴市场的影响")
    
    assert len(result) == 2

@pytest.mark.asyncio
async def test_fast_path_skips_llm():
    """简单输入（存在于关键词表中）跳过 LLM，直接返回"""
    from engine.industry.chain_parser import ChainInputParser
    
    mock_llm = MagicMock()
    mock_llm.chat_stream = AsyncMock()  # 不应该被调用
    
    parser = ChainInputParser(mock_llm)
    result = await parser.parse("石油")
    
    assert len(result) == 1
    assert result[0]["name"] == "石油"
    assert result[0]["type"] == "material"
    mock_llm.chat_stream.assert_not_called()

async def _async_iter(text: str):
    for ch in text:
        yield ch
```

### Step 2: Run test to verify it fails

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_parser.py -v`
Expected: FAIL (module not found)

### Step 3: Implement chain_parser.py

```python
# backend/engine/industry/chain_parser.py
"""智能输入拆解 — 将任意文本拆解为产业链图节点列表

快速路径：如果输入是已知的单实体（关键词表命中），直接返回，不调 LLM。
慢速路径：多实体 / 关系型 / 宏观事件 → 调 LLM 拆解。
"""

from __future__ import annotations

import json
import re
from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage

# 复用 chain_agent 中的关键词表
from .chain_agent import _MATERIAL_KEYWORDS, _INDUSTRY_KEYWORDS, _guess_subject_type

PARSE_INPUT_PROMPT = """...(上面的完整 prompt)..."""

# 关系型/宏观型关键词 — 触发 LLM 拆解
_RELATION_TRIGGERS = {"与", "和", "对", "vs", "VS", "关系", "影响", "冲击", "导致"}
_MACRO_KEYWORDS = {
    "加息", "降息", "利率", "汇率", "通胀", "通缩", "衰退", "萧条",
    "战争", "冲突", "制裁", "封锁", "关税", "贸易战", "选举", "政策",
    "QE", "缩表", "美联储", "央行", "美元", "人民币", "日元",
    "地震", "台风", "洪水", "干旱", "疫情", "瘟疫",
}
_COMMODITY_KEYWORDS = {
    "黄金", "白银", "原油", "石油", "天然气", "铜", "铁矿石", "铝",
    "锂", "镍", "钴", "稀土", "大豆", "玉米", "小麦", "棉花",
    "螺纹钢", "焦炭", "焦煤", "棕榈油", "豆粕", "白糖", "橡胶",
    "美元指数", "比特币",
}


class ChainInputParser:
    """将任意文本拆解为节点列表"""

    def __init__(self, llm: BaseLLMProvider):
        self._llm = llm

    async def parse(self, user_input: str) -> list[dict]:
        """返回 [{"name": "xxx", "type": "company|material|..."}]"""
        s = user_input.strip()
        if not s:
            return []

        # ── 快速路径：单实体命中关键词表 ──
        if not self._needs_llm_parse(s):
            t = _guess_subject_type_extended(s)
            return [{"name": s, "type": t}]

        # ── 慢速路径：LLM 拆解 ──
        try:
            prompt = PARSE_INPUT_PROMPT.format(user_input=s)
            chunks = []
            async for token in self._llm.chat_stream(
                [ChatMessage(role="user", content=prompt)]
            ):
                chunks.append(token)
            raw = "".join(chunks)
            # 复用 chain_agent 的 JSON 解析
            from .chain_agent import _lenient_json_loads
            parsed = _lenient_json_loads(raw)
            nodes = parsed.get("nodes", [])
            if not nodes:
                return [{"name": s, "type": _guess_subject_type_extended(s)}]
            return [{"name": n.get("name", s), "type": n.get("type", "industry")} for n in nodes]
        except Exception as e:
            logger.warning(f"ChainInputParser LLM 拆解失败，回退: {e}")
            return [{"name": s, "type": _guess_subject_type_extended(s)}]

    def _needs_llm_parse(self, s: str) -> bool:
        """判断是否需要 LLM 拆解（包含关系词/多实体暗示）"""
        for trigger in _RELATION_TRIGGERS:
            if trigger in s:
                return True
        # 纯粹的单实体 — 不需要 LLM
        return False


def _guess_subject_type_extended(subject: str) -> str:
    """扩展版类型判断 — 增加 macro/commodity"""
    s = subject.strip()
    
    # 宏观关键词
    for kw in _MACRO_KEYWORDS:
        if kw in s:
            return "macro"
    
    # 大宗商品
    for kw in _COMMODITY_KEYWORDS:
        if kw == s or kw in s:
            return "commodity"
    
    # 回退到原有判断
    return _guess_subject_type(s)
```

### Step 4: Run test to verify it passes

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_parser.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add backend/engine/industry/chain_parser.py tests/test_chain_parser.py
git commit -m "feat(chain): add ChainInputParser for smart text decomposition"
```

---

## Task 2: 后端 — 新增节点类型 macro/commodity + Prompt 升级

**Files:**
- Modify: `backend/engine/industry/chain_schemas.py` (ChainNode.node_type 注释更新)
- Modify: `backend/engine/industry/chain_agent.py` (CHAIN_BUILD_PROMPT 升级 + `_guess_subject_type` 扩展 + 导出 `_MATERIAL_KEYWORDS`/`_INDUSTRY_KEYWORDS`)
- Test: `tests/test_chain_parser.py` (已在 Task 1 覆盖类型判断)

### Step 1: Modify chain_schemas.py

在 `ChainNode` 类中更新 `node_type` 注释：

```python
# chain_schemas.py line 63
node_type: str = "industry"  # industry | material | company | event | logistics | macro | commodity
```

### Step 2: Modify chain_agent.py — CHAIN_BUILD_PROMPT

在 `CHAIN_BUILD_PROMPT` 的 `## ⚠️ 输入类型智能识别` 部分增加宏观和大宗商品类型：

```
- **宏观因素**（如"美联储加息"、"地缘冲突"、"汇率贬值"）→ 作为 node_type="macro" 的事件驱动节点，分析它对各行业/商品的传导路径。
- **大宗商品**（如"黄金"、"原油"、"铜"）→ 作为 node_type="commodity" 的核心节点，构建其定价因子、供需链条、相关资产。
```

在 `node_type` 输出格式中增加 `macro` 和 `commodity`：

```
"node_type": "material|industry|company|event|logistics|macro|commodity",
```

### Step 3: Extend `_guess_subject_type` 

添加 macro/commodity 识别逻辑（与 Task 1 的 `_guess_subject_type_extended` 合并）。直接在原函数中增加判断分支，在现有 "原材料/商品" 和 "行业" 判断之前插入 macro 和 commodity 判断。

### Step 4: Run tests

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_chain_parser.py tests/test_chain_schemas.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add backend/engine/industry/chain_schemas.py backend/engine/industry/chain_agent.py
git commit -m "feat(chain): extend node types with macro/commodity + upgrade prompts"
```

---

## Task 3: 后端 — 新增 API 路由（parse/add-node/expand-all）

**Files:**
- Modify: `backend/engine/industry/routes.py`
- Test: `tests/test_chain_routes.py` (新建)

### 新增 3 个接口

#### 3a. `POST /chain/parse` — 解析用户输入

```python
class _ChainParseRequest(BaseModel):
    text: str

@router.post("/chain/parse")
async def chain_parse_input(req: _ChainParseRequest):
    """将任意文本解析为节点列表（不调图，只拆解）"""
    from . import get_industry_engine
    ie = get_industry_engine()
    if not ie._llm:
        return {"error": "LLM 未配置"}
    from .chain_parser import ChainInputParser
    parser = ChainInputParser(ie._llm)
    nodes = await parser.parse(req.text)
    return {"nodes": nodes}
```

#### 3b. `POST /chain/add-node` — 添加节点并发现与已有网络的关系

```python
class _ChainAddNodeRequest(BaseModel):
    node_name: str
    node_type: str = "industry"
    existing_nodes: list[str] = []
    existing_links: list[dict] = []

@router.post("/chain/add-node")
async def chain_add_node(req: _ChainAddNodeRequest):
    """添加一个新节点，LLM 发现它和已有网络的关系（SSE）"""
    # 后端逻辑：
    # 1. 先创建这个节点（如果不存在）
    # 2. 用 LLM 分析它与 existing_nodes 的关系，生成边
    # 3. SSE 流式推送
```

#### 3c. `POST /chain/expand-all` — 批量展开所有叶子节点

```python
class _ChainExpandAllRequest(BaseModel):
    subject: str
    leaf_nodes: list[str]
    existing_nodes: list[str] = []

@router.post("/chain/expand-all")
async def chain_expand_all(req: _ChainExpandAllRequest):
    """并发展开所有叶子节点（SSE）"""
    # 后端逻辑：
    # 对每个 leaf_node 并发调 build(subject=leaf_node, max_depth=1)
    # 合并结果，去重，SSE 推送
```

### Step 1: Write failing test

```python
# tests/test_chain_routes.py
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_parse_endpoint():
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/industry/chain/parse", json={"text": "石油"})
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data
        assert len(data["nodes"]) >= 1
```

### Step 2-5: Implement, test, commit

```bash
git add backend/engine/industry/routes.py tests/test_chain_routes.py
git commit -m "feat(chain): add parse/add-node/expand-all API endpoints"
```

---

## Task 4: 后端 — ChainAgent.build 改造（默认深度1 + add_node + expand_all）

**Files:**
- Modify: `backend/engine/industry/chain_agent.py`
- Test: `tests/test_chain_agent.py`

### 改动

1. **`build()` 的 `max_depth` 默认改为 1**（在 `ChainBuildRequest` schema 中改 default=1）
2. **新增 `add_node()` 方法**：

```python
async def add_node(self, node_name: str, node_type: str, existing_nodes: list[str]):
    """添加一个新节点并用 LLM 发现它与已有节点的关系
    
    Prompt 策略：告诉 LLM 已有的节点列表，让它只输出新节点与已有节点之间的边。
    新节点自身也会被 build(depth=1) 拓展出直接上下游。
    """
    # 1. yield 新节点本身
    # 2. 调 build(subject=node_name, max_depth=1) 获取 1 层上下游
    # 3. 额外用 CHAIN_RELATE_PROMPT 让 LLM 分析 node_name 与 existing_nodes 的关系
```

3. **新增 `expand_all()` 方法**：

```python
async def expand_all(self, leaf_nodes: list[str], existing_nodes: list[str]):
    """并发展开多个节点"""
    import asyncio
    
    async def _expand_one(node_name: str):
        results = []
        async for evt in self.build(ChainBuildRequest(subject=node_name, max_depth=1)):
            results.append(evt)
        return results
    
    tasks = [_expand_one(n) for n in leaf_nodes[:10]]  # 最多并发10个
    all_results = await asyncio.gather(*tasks, return_exceptions=True)
    # 合并去重，yield SSE
```

4. **新增 `CHAIN_RELATE_PROMPT`**：

```python
CHAIN_RELATE_PROMPT = """你是「产业物理学家」。用户在产业链图中新增了节点「{new_node}」。

## 已有节点列表
{existing_nodes}

## 任务
分析「{new_node}」与上述已有节点之间**是否存在**产业链关系。只输出确实存在关系的边。

## 输出格式
{{"links": [
  {{"source": "...", "target": "...", "relation": "upstream|downstream|substitute|...", ...}}
]}}

如果没有任何关系，输出 {{"links": []}}。
"""
```

### Step 1-5: Test, implement, verify, commit

```bash
git add backend/engine/industry/chain_agent.py backend/engine/industry/chain_schemas.py tests/test_chain_agent.py
git commit -m "feat(chain): add add_node/expand_all + default depth=1"
```

---

## Task 5: 前端 — 类型系统升级（macro/commodity 节点类型 + expanding 进度）

**Files:**
- Modify: `frontend/types/chain.ts`

### 改动

```typescript
// chain.ts — 更新 ChainNode.node_type 联合类型
export interface ChainNode {
  // ...
  node_type: "material" | "industry" | "company" | "event" | "logistics" | "macro" | "commodity";
  // ...
}

// 新增节点类型颜色和图标
export const NODE_TYPE_ICONS: Record<string, string> = {
  material: "⚗️",
  industry: "🏭",
  company: "🏢",
  event: "⚡",
  logistics: "🚢",
  macro: "🌍",       // 新增
  commodity: "💰",    // 新增
};

// 新增 ExploreStatus "adding" 状态
export type ExploreStatus =
  | "idle"
  | "building"
  | "ready"
  | "simulating"
  | "exploring"
  | "expanding"
  | "adding"        // 新增：正在添加节点
  | "done"
  | "error";
```

### Step 1-3: Modify, verify TypeScript compiles, commit

```bash
git add frontend/types/chain.ts
git commit -m "feat(chain): extend ChainNode type with macro/commodity"
```

---

## Task 6: 前端 — Store 升级（纯前端冲击传播 + addNode + expandAll + parse）

**Files:**
- Modify: `frontend/stores/useChainStore.ts`

### 核心改动

#### 6a. 新增 `propagateShocks()` — 纯前端 BFS 冲击传播

```typescript
// 衰减规则映射
const STRENGTH_DECAY: Record<string, number> = {
  "强刚性": 0.10,  // 只衰减 10%
  "中等": 0.35,     // 衰减 35%
  "弱弹性": 0.60,   // 衰减 60%
};

// 关系方向翻转规则
function getImpactDirection(
  relation: string, 
  shockDirection: "up" | "down"
): "benefit" | "hurt" {
  // upstream + 涨 → 下游 hurt（成本推升）
  // downstream + 涨 → 上游 benefit（需求拉动）
  // substitute + 涨 → 替代品 benefit
  // competes + 涨 → 竞争对手 hurt
  if (relation === "upstream" || relation === "cost_input") {
    return shockDirection === "up" ? "hurt" : "benefit";
  }
  if (relation === "downstream") {
    return shockDirection === "up" ? "benefit" : "hurt";
  }
  if (relation === "substitute") {
    return shockDirection === "up" ? "benefit" : "hurt";
  }
  if (relation === "competes") {
    return shockDirection === "up" ? "hurt" : "benefit";
  }
  return "neutral" as any;
}

function propagateShocksAlgorithm(
  nodes: ChainNode[],
  links: ChainLink[],
  shocks: Map<string, NodeShock>,
): { nodes: ChainNode[]; links: ChainLink[] } {
  // BFS from each shock source
  // For each reachable node:
  //   1. Calculate decay based on transmission_strength
  //   2. Flip direction based on relation type
  //   3. Apply dampening_factors (extra -15% per factor)
  //   4. Apply amplifying_factors (extra +10% per factor)
  //   5. Multi-path: weighted average
  // Returns updated nodes and links with impact/impact_score set
}
```

#### 6b. `setShock` / `clearShock` 自动触发 `propagateShocks`

```typescript
setShock: (nodeName, shock, label) => {
  set((s) => {
    const next = new Map(s.shocks);
    next.set(nodeName, { node_name: nodeName, shock, shock_label: label || "" });
    // 立即传播冲击
    const { nodes: propagated, links: propagatedLinks } = propagateShocksAlgorithm(
      s.nodes, s.links, next
    );
    return { shocks: next, nodes: propagated, links: propagatedLinks };
  });
},
```

#### 6c. 新增 `addNode(name: string)` 方法

```typescript
addNode: async (nodeName: string) => {
  const { nodes, links } = get();
  set({ status: "adding" });
  
  // 调后端 /chain/add-node
  const res = await fetch(`${API_BASE}/api/v1/industry/chain/add-node`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      node_name: nodeName,
      existing_nodes: nodes.map(n => n.name),
    }),
  });
  
  // 解析 SSE，合并新节点和边
  await _parseSSE(res, set, get, true);
  set({ status: "ready" });
},
```

#### 6d. 新增 `expandAll()` 方法

```typescript
expandAll: async () => {
  const { nodes, links } = get();
  // 找叶子节点（只有入边没有出边，或度数<=1）
  const outDegree = new Map<string, number>();
  const inDegree = new Map<string, number>();
  for (const l of links) {
    outDegree.set(l.source, (outDegree.get(l.source) || 0) + 1);
    inDegree.set(l.target, (inDegree.get(l.target) || 0) + 1);
  }
  const leafNodes = nodes
    .filter(n => !outDegree.has(n.name) || (outDegree.get(n.name) || 0) <= 0)
    .map(n => n.name);

  if (leafNodes.length === 0) return;
  set({ status: "building", expandingNodes: leafNodes });
  
  // 调后端 /chain/expand-all
  // SSE 解析...
},
```

#### 6e. 新增 `parseAndBuild(text: string)` 方法

```typescript
parseAndBuild: async (text: string) => {
  // 1. 调 /chain/parse 拆解文本
  const parseRes = await fetch(`${API_BASE}/api/v1/industry/chain/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const { nodes: parsedNodes } = await parseRes.json();
  
  // 2. 对第一个节点调 build（初始图）
  // 3. 对后续节点调 addNode（加入图中）
  // 4. 所有节点加入后，自动发现它们之间的关系
},
```

#### 6f. `expandingNodes` 改为带进度的 Map

```typescript
expandingNodes: Map<string, { progress: number; phase: string }>;  // 原来是 string[]
```

#### 6g. `simulate()` 改名语义为 "AI 深度解读"

保留 `simulate()` 方法，但它现在是"文字解读"功能，不再负责颜色变化（颜色变化由 `propagateShocks` 瞬间完成）。

### Step 1-5: Implement, test locally, commit

```bash
git add frontend/stores/useChainStore.ts
git commit -m "feat(chain): add propagateShocks algorithm + addNode/expandAll/parseAndBuild"
```

---

## Task 7: 前端 — ChainToolbar 改造（去深度选择器 + 新按钮）

**Files:**
- Modify: `frontend/components/chain/ChainToolbar.tsx`

### 改动

1. **删除深度选择器**（原来的 `[2, 3, 4]` 按钮组）
2. **修改构建逻辑**：输入框提交 → 调 `parseAndBuild(text)` 而非 `build(text, maxDepth)`
3. **新增「🌐 全局扩展」按钮**：网络就绪后显示，调 `expandAll()`
4. **新增「➕ 添加节点」按钮**：弹出小输入框，输入名称后调 `addNode(name)`
5. **「推演冲击」按钮改名**为「🧠 AI 深度解读」

```tsx
// 新增的按钮区域
{hasNetwork && (
  <>
    {/* 全局扩展 */}
    <button onClick={() => expandAll()} disabled={isBuilding}>
      <Globe size={14} />
      全局扩展
    </button>
    
    {/* 添加节点 */}
    <AddNodePopover onAdd={(name) => addNode(name)} disabled={isBuilding} />
    
    {/* AI 深度解读（原推演冲击）*/}
    <button onClick={() => simulate()} disabled={isSimulating || !hasShocks}>
      <Brain size={14} />
      {isSimulating ? "解读中..." : hasShocks ? `AI 深度解读 (${shocks.size})` : "设置冲击后解读"}
    </button>
  </>
)}
```

### Placeholder 提示更新

```
"输入任意主体或关系（如：中泰化学、黄金与石油的关系、美联储加息对新兴市场的影响）"
```

### Step 1-5: Modify, verify UI, commit

```bash
git add frontend/components/chain/ChainToolbar.tsx
git commit -m "feat(chain): revamp toolbar — remove depth selector, add expand-all & add-node"
```

---

## Task 8: 前端 — ChainGraph 升级（环形进度条 + 新节点类型颜色）

**Files:**
- Modify: `frontend/components/chain/ChainGraph.tsx`

### 改动

#### 8a. `paintNode` 增加环形进度条

```typescript
// 在 paintNode 中，检查是否正在拓展
const expandingState = expandingNodes.get(node.name);
if (expandingState) {
  const { progress } = expandingState;
  const startAngle = -Math.PI / 2;
  const endAngle = startAngle + progress * 2 * Math.PI;
  
  ctx.beginPath();
  ctx.arc(node.x, node.y, baseSize + 3, startAngle, endAngle);
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.stroke();
  
  // 背景轨道
  ctx.beginPath();
  ctx.arc(node.x, node.y, baseSize + 3, endAngle, startAngle + 2 * Math.PI);
  ctx.strokeStyle = "rgba(59, 130, 246, 0.15)";
  ctx.lineWidth = 2.5;
  ctx.stroke();
}
```

#### 8b. 新节点类型渐变色

为 macro 和 commodity 类型节点增加特殊颜色：

```typescript
// 节点类型的底色（neutral 状态下，用类型底色区分）
const NODE_TYPE_BASE_COLORS: Record<string, string> = {
  material: "#64748b",
  industry: "#64748b",
  company: "#6366f1",   // 紫色调区分
  event: "#f59e0b",
  logistics: "#06b6d4",
  macro: "#8b5cf6",     // 紫色 — 宏观因素
  commodity: "#d97706",  // 金色 — 大宗商品
};
```

当 `impact === "neutral"` 时，用 `NODE_TYPE_BASE_COLORS[nodeType]` 代替统一灰色，让不同类型节点在未冲击时也有视觉区分。

#### 8c. idle 状态提示文案更新

```tsx
<div className="text-xs opacity-60">
  公司：中泰化学、宁德时代 · 原材料：石油、锂电池 · 
  宏观：美联储加息 · 自由组合：黄金与石油的关系
</div>
```

### Step 1-5: Modify, verify visuals, commit

```bash
git add frontend/components/chain/ChainGraph.tsx
git commit -m "feat(chain): add expanding progress ring + node type colors for macro/commodity"
```

---

## Task 9: 前端 — ChainLegend / ChainStatusBar / NodeDetail 适配

**Files:**
- Modify: `frontend/components/chain/ChainLegend.tsx`
- Modify: `frontend/components/chain/ChainStatusBar.tsx`
- Modify: `frontend/components/chain/NodeDetail.tsx`

### ChainLegend 改动

增加新节点类型图例：

```typescript
// 新增类型图例
const TYPE_LEGEND = [
  { icon: "⚗️", label: "原材料", color: "#64748b" },
  { icon: "🏭", label: "行业", color: "#64748b" },
  { icon: "🏢", label: "公司", color: "#6366f1" },
  { icon: "🌍", label: "宏观因素", color: "#8b5cf6" },
  { icon: "💰", label: "大宗商品", color: "#d97706" },
  { icon: "🚢", label: "物流", color: "#06b6d4" },
];
```

### ChainStatusBar 改动

- 处理 `status === "adding"` 状态的显示
- 删除深度进度显示（不再有固定层级）
- 增加 "expanding X nodes" 进度

### NodeDetail 改动

- 在标签中正确显示 macro/commodity 类型图标
- 添加一个「🔍 展开此节点」按钮（快捷双击替代）

### Step 1-5: Modify, verify, commit

```bash
git add frontend/components/chain/ChainLegend.tsx frontend/components/chain/ChainStatusBar.tsx frontend/components/chain/NodeDetail.tsx
git commit -m "feat(chain): update legend/statusbar/detail for macro/commodity + expanding state"
```

---

## Task 10: 集成测试 + 边界场景

**Files:**
- Create: `tests/test_chain_integration.py`

### 测试场景

1. **单实体构建**：输入"石油" → 快速路径 → build(depth=1) → 返回节点+边
2. **关系型输入**：输入"黄金与石油的关系" → LLM parse → 拆解为2节点 → 分别 build → addNode 关联
3. **宏观事件**：输入"美联储加息对新兴市场的影响" → parse → build + addNode
4. **双击展开**：对已有节点调 expandNode → 新增子网络
5. **全局扩展**：expandAll → 叶子节点并发展开
6. **冲击传播算法**：设置冲击 → propagateShocks → 验证衰减/方向翻转/多路径叠加
7. **冲击传播边界**：空冲击/无边网络/环形网络
8. **添加孤立节点**：addNode + 无已有网络 → 只创建节点
9. **LLM 返回截断**：parse 接口 LLM 失败 → 回退到直接当作单节点

### Step 1-5: Write tests, run, fix, commit

```bash
git add tests/test_chain_integration.py
git commit -m "test(chain): add integration tests for v2 features"
```

---

## Task 11: 前端冲击传播算法单元测试

**Files:**
- Create: `frontend/__tests__/propagateShocks.test.ts` (或在 store 测试中)

### 测试场景

由于前端传播算法是核心新功能，需要独立测试：

1. **线性链条**：A → B → C, A涨 → B hurt → C hurt（逐级衰减）
2. **替代关系**：A ←substitute→ B, A涨 → B benefit
3. **多路径叠加**：A→C, B→C（两个冲击源同时影响C）
4. **环检测**：A→B→C→A，不应无限循环
5. **dampening/amplifying**：有衰减因素时额外减弱，有放大因素时额外增强
6. **空冲击**：无冲击源 → 所有节点保持 neutral

这里不强制用特定测试框架，可以用 vitest / jest，或者直接在 Node 环境中运行。关键是逻辑正确性。

### Step 1-5: Write, run, commit

```bash
git add frontend/__tests__/propagateShocks.test.ts
git commit -m "test(chain): unit tests for frontend shock propagation algorithm"
```

---

## 执行顺序总结

```
Task 1 (chain_parser.py)     ← 最底层，无依赖
Task 2 (types + prompts)     ← 依赖 Task 1
Task 3 (routes)              ← 依赖 Task 1, 2
Task 4 (agent methods)       ← 依赖 Task 2
Task 5 (frontend types)      ← 独立
Task 6 (store)               ← 依赖 Task 5, 后端 Task 3/4
Task 7 (toolbar)             ← 依赖 Task 6
Task 8 (graph)               ← 依赖 Task 5, 6
Task 9 (legend/status/detail)← 依赖 Task 5
Task 10 (integration tests)  ← 依赖 Task 1-4
Task 11 (frontend tests)     ← 依赖 Task 6
```

**并行可能性：**
- Task 1+5 可并行（后端 parser + 前端 types）
- Task 7+8+9 可并行（都只依赖 Task 5+6）
- Task 10+11 可并行（后端测试 + 前端测试）

---

## 交互流程示意

### 场景1：输入"石油"
```
用户输入 "石油" → Enter
  → 前端调 parseAndBuild("石油")
  → 后端 /chain/parse → 快速路径 → [{"name":"石油","type":"material"}]
  → 前端调 build("石油", 1)
  → 后端 build SSE → 1层上下游（原油→石油→石脑油→...）
  → 图显示 ~10 个节点
  → 用户双击 "石脑油" → expandNode → 又展开 1 层
  → 用户点 "🌐 全局扩展" → 所有叶子节点并发展开
```

### 场景2：输入"黄金与石油的关系"
```
用户输入 "黄金与石油的关系" → Enter
  → 前端调 parseAndBuild("黄金与石油的关系")
  → 后端 /chain/parse → LLM 拆解 → [{"name":"黄金","type":"commodity"},{"name":"石油","type":"commodity"}]
  → 前端对"黄金" 调 build("黄金", 1) → 黄金的 1 层上下游
  → 前端对"石油" 调 addNode("石油", existing_nodes=[黄金的节点...])
    → 后端 build("石油", 1) + CHAIN_RELATE_PROMPT → 发现石油和黄金的关系边
  → 图中同时显示黄金和石油两个子网络，并有关系边连接
```

### 场景3：设置冲击
```
用户在"石油"节点上设置 +50% → setShock
  → 瞬间(<50ms) propagateShocks BFS
  → 全图变色：上游涨→下游 hurt，替代品 benefit
  → 用户可选点 "🧠 AI 深度解读" → LLM 生成文字解释
```
