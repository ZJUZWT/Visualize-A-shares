"""测试 simulate 方法：LLM 遗漏的节点/边会自动补全 neutral"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
from unittest.mock import AsyncMock
from engine.industry.chain_agent import ChainAgent
from engine.industry.chain_schemas import ChainSimulateRequest, NodeShock


class MockLLM:
    """模拟 LLM — 只返回部分节点和边（模拟 LLM 遗漏的情况）"""

    async def chat_stream(self, messages):
        # 只返回 2 个 node_impacts 和 1 条 link_impact（实际网络有 5 个节点 4 条边）
        response = """{
  "node_impacts": [
    {
      "name": "PVC",
      "impact": "hurt",
      "impact_score": -0.6,
      "impact_reason": "原盐涨价 → PVC 成本上升",
      "transmission_path": "原盐 → PVC"
    },
    {
      "name": "烧碱",
      "impact": "hurt",
      "impact_score": -0.4,
      "impact_reason": "原盐涨价 → 烧碱成本上升",
      "transmission_path": "原盐 → 烧碱"
    }
  ],
  "link_impacts": [
    {
      "source": "原盐",
      "target": "PVC",
      "impact": "negative",
      "impact_reason": "成本推升"
    }
  ],
  "summary": "原盐涨价导致下游PVC和烧碱成本上升"
}"""
        for ch in response:
            yield ch

    async def chat(self, messages):
        return ""


@pytest.mark.asyncio(loop_scope="function")
async def test_simulate_fills_missing_nodes_and_links():
    """验证 simulate 会为 LLM 遗漏的节点/边自动补全 neutral"""
    llm = MockLLM()
    agent = ChainAgent(llm)

    req = ChainSimulateRequest(
        subject="中泰化学",
        shocks=[NodeShock(node_name="原盐", shock=0.5, shock_label="涨50%")],
        nodes=[
            {"name": "中泰化学", "node_type": "company", "summary": "中心"},
            {"name": "原盐", "node_type": "material", "summary": "冲击源"},
            {"name": "PVC", "node_type": "material", "summary": "核心产品"},
            {"name": "烧碱", "node_type": "material", "summary": "核心产品"},
            {"name": "建筑管材", "node_type": "industry", "summary": "下游"},
        ],
        links=[
            {"source": "原盐", "target": "PVC", "relation": "upstream"},
            {"source": "原盐", "target": "烧碱", "relation": "upstream"},
            {"source": "PVC", "target": "建筑管材", "relation": "downstream"},
            {"source": "中泰化学", "target": "PVC", "relation": "downstream"},
        ],
    )

    events = []
    async for event in agent.simulate(req):
        events.append(event)

    # 统计各事件类型
    node_impacts = [e for e in events if e["event"] == "node_impact"]
    link_impacts = [e for e in events if e["event"] == "link_impact"]
    simulate_complete = [e for e in events if e["event"] == "simulate_complete"]

    # LLM 只返回了 PVC 和 烧碱 的 impact，但总共应该覆盖 5-1=4 个非冲击源节点
    node_names = [ni["data"]["name"] for ni in node_impacts]
    print(f"节点影响覆盖: {node_names}")
    assert "PVC" in node_names
    assert "烧碱" in node_names
    assert "中泰化学" in node_names, "遗漏的中泰化学应被自动补全为 neutral"
    assert "建筑管材" in node_names, "遗漏的建筑管材应被自动补全为 neutral"
    # 冲击源"原盐"不应出现在 node_impacts 中（它是用户设置的）
    assert "原盐" not in node_names, "冲击源不应被补全"

    # LLM 只返回了 1 条 link_impact，但总共 4 条边应该全部覆盖
    link_keys = [(li["data"]["source"], li["data"]["target"]) for li in link_impacts]
    print(f"边影响覆盖: {link_keys}")
    assert ("原盐", "PVC") in link_keys
    assert ("原盐", "烧碱") in link_keys, "遗漏的边应被自动补全"
    assert ("PVC", "建筑管材") in link_keys, "遗漏的边应被自动补全"
    assert ("中泰化学", "PVC") in link_keys, "遗漏的边应被自动补全"
    assert len(link_keys) == 4

    assert len(simulate_complete) == 1
    print("✅ simulate 补全逻辑测试通过!")


if __name__ == "__main__":
    asyncio.run(test_simulate_fills_missing_nodes_and_links())
