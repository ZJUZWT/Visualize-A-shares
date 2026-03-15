"""Agent 测试"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def mock_tools():
    tools = Mock()
    tools.llm_engine = None  # 无 LLM，测试降级路径
    tools.execute = AsyncMock(return_value="mock result")
    return tools


@pytest.fixture
def expert_agent(mock_tools, tmp_path):
    from expert.agent import ExpertAgent
    kg_path = str(tmp_path / "kg.json")
    return ExpertAgent(mock_tools, kg_path=kg_path)


def test_agent_initialization(expert_agent):
    """测试 Agent 初始化"""
    assert expert_agent._graph is not None
    # 初始信念已写入图谱
    beliefs = expert_agent.get_beliefs()
    assert len(beliefs) > 0


def test_agent_get_beliefs_returns_dicts(expert_agent):
    """测试 get_beliefs 返回 dict 列表"""
    beliefs = expert_agent.get_beliefs()
    assert len(beliefs) > 0
    for b in beliefs:
        assert isinstance(b, dict)
        assert "content" in b
        assert "confidence" in b
        assert "id" in b


def test_agent_get_stances_returns_list(expert_agent):
    """测试 get_stances 返回列表"""
    stances = expert_agent.get_stances()
    assert isinstance(stances, list)


@pytest.mark.asyncio
async def test_agent_chat_no_llm_yields_events(expert_agent):
    """测试无 LLM 时 chat 仍产出基本事件"""
    events = []
    async for event in expert_agent.chat("宁德时代300750怎么样"):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "thinking_start" in event_types
    assert "graph_recall" in event_types
    assert "reply_complete" in event_types


@pytest.mark.asyncio
async def test_agent_chat_reply_complete_has_full_text(expert_agent):
    """测试 reply_complete 事件包含 full_text"""
    async for event in expert_agent.chat("测试问题"):
        if event["event"] == "reply_complete":
            assert "full_text" in event["data"]
            break


@pytest.mark.asyncio
async def test_agent_chat_graph_recall_has_nodes(expert_agent):
    """测试 graph_recall 事件包含 nodes 列表"""
    async for event in expert_agent.chat("政策对市场的影响"):
        if event["event"] == "graph_recall":
            assert "nodes" in event["data"]
            assert isinstance(event["data"]["nodes"], list)
            break


@pytest.mark.asyncio
async def test_agent_chat_with_llm_calls_think(tmp_path):
    """测试有 LLM 时调用 think 步骤"""
    from expert.agent import ExpertAgent
    from expert.schemas import ThinkOutput

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value='{"needs_data": false, "tool_calls": [], "reasoning": "直接回答"}')
    mock_llm.chat_stream = AsyncMock(return_value=_async_gen(["回复内容"]))

    mock_tools = Mock()
    mock_tools.llm_engine = mock_llm
    mock_tools.execute = AsyncMock(return_value="tool result")

    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    events = []
    async for event in agent.chat("测试问题"):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "thinking_start" in event_types
    assert "reply_complete" in event_types


async def _async_gen(items):
    for item in items:
        yield item
