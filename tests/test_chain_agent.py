# tests/test_chain_agent.py
"""ChainAgent 推演引擎测试（使用 mock LLM）"""
import json
import pytest
from unittest.mock import MagicMock

from engine.industry.chain_agent import ChainAgent, _normalize_name
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

    # "石油" 会被归一化为 "原油"，不管几层只应出现一次
    complete_event = [e for e in events if e["event"] == "explore_complete"][0]
    node_names = [n["name"] for n in complete_event["data"]["nodes"]]
    normalized = _normalize_name("石油")  # → "原油"
    assert node_names.count(normalized) == 1, f"'{normalized}' 应只出现 1 次，但出现了 {node_names.count(normalized)} 次。所有节点: {node_names}"


@pytest.mark.asyncio
async def test_chain_agent_normalize_dedup():
    """验证名称归一化能正确去重：PVC vs PVC（聚氯乙烯）"""
    mock_response = json.dumps({
        "nodes": [
            {"name": "PVC", "node_type": "material", "impact": "neutral", "impact_score": 0.0, "summary": "A"},
            {"name": "PVC（聚氯乙烯）", "node_type": "material", "impact": "neutral", "impact_score": 0.0, "summary": "B"},
            {"name": "聚氯乙烯", "node_type": "material", "impact": "neutral", "impact_score": 0.0, "summary": "C"},
            {"name": "电石", "node_type": "material", "impact": "neutral", "impact_score": 0.0, "summary": "D"},
        ],
        "links": [
            {"source": "电石", "target": "PVC", "relation": "upstream"},
            {"source": "电石", "target": "PVC（聚氯乙烯）", "relation": "upstream"},  # 重复边（归一化后相同）
        ],
        "expand_candidates": [],
    }, ensure_ascii=False)

    llm = _make_mock_llm([mock_response])
    agent = ChainAgent(llm)

    req = ChainExploreRequest(event="PVC涨价", max_depth=1)
    events = []
    async for event in agent.explore(req):
        events.append(event)

    complete_event = [e for e in events if e["event"] == "explore_complete"][0]
    node_names = [n["name"] for n in complete_event["data"]["nodes"]]

    # PVC / PVC（聚氯乙烯）/ 聚氯乙烯 应该全部归一化为 "PVC"，只出现一次
    assert node_names.count("PVC") == 1, f"PVC 应只出现 1 次，实际: {node_names}"
    assert "PVC（聚氯乙烯）" not in node_names, f"不应出现括号别名: {node_names}"
    assert "聚氯乙烯" not in node_names, f"不应出现中文别名: {node_names}"

    # 边也应该去重：电石→PVC 只有一条
    links = complete_event["data"]["links"]
    link_keys = [(l["source"], l["target"]) for l in links]
    assert link_keys.count(("电石", "PVC")) == 1, f"电石→PVC 应只有 1 条边，实际: {link_keys}"
