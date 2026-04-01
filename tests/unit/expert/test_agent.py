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
    from engine.expert.agent import ExpertAgent
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
    from engine.expert.agent import ExpertAgent

    mock_llm = Mock()
    mock_llm.chat = AsyncMock(return_value='{"needs_data": false, "tool_calls": [], "reasoning": "直接回答"}')

    async def fake_chat_stream(messages):
        yield "回复内容"

    mock_llm.chat_stream = fake_chat_stream

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


@pytest.mark.asyncio
async def test_agent_chat_emits_reasoning_summary_when_think_has_reasoning(expert_agent):
    from engine.expert.schemas import ThinkOutput

    expert_agent.recall_and_think = AsyncMock(return_value=(
        [],
        [],
        ThinkOutput(needs_data=False, reasoning="先确认行业周期，再评估安全边际"),
    ))

    events = []
    async for event in expert_agent.chat("测试问题"):
        events.append(event)

    reasoning_events = [e for e in events if e["event"] == "reasoning_summary"]
    assert len(reasoning_events) == 1
    assert reasoning_events[0]["data"]["summary"] == "先确认行业周期，再评估安全边际"


@pytest.mark.asyncio
async def test_agent_chat_emits_self_critique_before_reply_complete(tmp_path):
    from engine.expert.agent import ExpertAgent
    from engine.expert.schemas import ThinkOutput

    mock_tools = Mock()
    mock_tools.llm_engine = object()
    mock_tools.execute = AsyncMock(return_value="tool result")
    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    agent.recall_and_think = AsyncMock(return_value=(
        [],
        [],
        ThinkOutput(needs_data=False, reasoning="先看赔率"),
    ))
    agent.generate_reply_stream = _reply_stream_gen
    agent.belief_update = AsyncMock(return_value=[])
    agent._self_critique = AsyncMock(return_value={
        "summary": "证据基本够用，但仍需提防板块退潮。",
        "risks": ["情绪退潮"],
        "missing_data": [],
        "counterpoints": ["量能确认还不够"],
        "confidence_note": "偏谨慎",
    })

    events = []
    async for event in agent.chat("测试问题"):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "self_critique" in event_types
    assert event_types.index("self_critique") < event_types.index("reply_complete")


@pytest.mark.asyncio
async def test_resume_completion_check_returns_complete_when_llm_says_complete(tmp_path):
    from engine.expert.agent import ExpertAgent

    class _MockLLM:
        async def chat_stream(self, messages):
            _ = messages
            yield '{"is_complete": true, "reason": "回复已完整", "confidence": 0.91}'

    mock_tools = Mock()
    mock_tools.llm_engine = _MockLLM()
    mock_tools.execute = AsyncMock(return_value="tool result")
    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    result = await agent.check_resume_completion(
        user_message="帮我看看这段回复是否完整",
        partial_content="结论：当前估值合理，建议持有。",
        history=[{"role": "user", "content": "怎么看这只票"}],
        persona="rag",
    )

    assert result["is_complete"] is True
    assert result["reason"] == "回复已完整"
    assert result["confidence"] == pytest.approx(0.91, rel=1e-6)


@pytest.mark.asyncio
async def test_resume_completion_check_returns_incomplete_when_llm_says_incomplete(tmp_path):
    from engine.expert.agent import ExpertAgent

    class _MockLLM:
        async def chat_stream(self, messages):
            _ = messages
            yield '{"is_complete": false, "reason": "句子未结束", "confidence": 0.95}'

    mock_tools = Mock()
    mock_tools.llm_engine = _MockLLM()
    mock_tools.execute = AsyncMock(return_value="tool result")
    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    result = await agent.check_resume_completion(
        user_message="这段话是不是中断了？",
        partial_content="建议重点关注量价配合，若",
        history=[{"role": "user", "content": "短线怎么看"}],
        persona="rag",
    )

    assert result["is_complete"] is False
    assert result["reason"] == "句子未结束"
    assert result["confidence"] == pytest.approx(0.95, rel=1e-6)


async def _async_gen(items):
    for item in items:
        yield item


async def _reply_stream_gen(*args, **kwargs):
    yield "最终", "最终"
    yield "回复", "最终回复"
