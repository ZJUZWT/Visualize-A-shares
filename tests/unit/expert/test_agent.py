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
    assert result["check_failed"] is False
    mock_tools.execute.assert_not_awaited()


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
    assert result["check_failed"] is False
    mock_tools.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_completion_check_marks_failed_when_provider_returns_invalid_json(tmp_path):
    from engine.expert.agent import ExpertAgent

    class _MockLLM:
        async def chat_stream(self, messages):
            _ = messages
            yield "这不是合法 JSON"

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
    assert result["check_failed"] is True
    assert "完整性检查失败" in result["reason"]
    mock_tools.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_completion_check_marks_failed_when_llm_missing(tmp_path):
    from engine.expert.agent import ExpertAgent

    mock_tools = Mock()
    mock_tools.llm_engine = None
    mock_tools.execute = AsyncMock(return_value="tool result")
    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    result = await agent.check_resume_completion(
        user_message="这段话是不是中断了？",
        partial_content="建议重点关注量价配合，若",
        history=[{"role": "user", "content": "短线怎么看"}],
        persona="rag",
    )

    assert result["is_complete"] is False
    assert result["check_failed"] is True
    assert "LLM 未配置" in result["reason"]
    mock_tools.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_completion_check_marks_failed_when_provider_exception(tmp_path):
    from engine.expert.agent import ExpertAgent

    class _MockLLM:
        async def chat_stream(self, messages):
            _ = messages
            raise RuntimeError("provider load failed")
            yield ""  # pragma: no cover

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
    assert result["check_failed"] is True
    assert "provider load failed" in result["reason"]
    mock_tools.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_reply_stream_preserves_user_images_after_context_guard(expert_agent):
    captured_messages = []

    class _MockLLM:
        async def chat_stream(self, messages):
            captured_messages.append(messages)
            if len(captured_messages) == 1:
                yield (
                    '{"image_kind":"other","detected_entities":[],"user_focus":"图像理解",'
                    '"summary":"这是用户上传的一张走势图截图。"}'
                )
                return
            yield "图像分析已收到"

    expert_agent._model_router = None
    expert_agent._llm = _MockLLM()

    chunks = []
    async for token, full_text in expert_agent.generate_reply_stream(
        "帮我看看这张K线图",
        nodes=[],
        memories=[],
        tool_results=[],
        history=[],
        persona="rag",
        images=["data:image/png;base64,abc123"],
    ):
        chunks.append((token, full_text))

    assert chunks[-1][1] == "图像分析已收到"
    assert len(captured_messages) == 2
    user_message = captured_messages[-1][-1]
    assert user_message.role == "user"
    assert user_message.images == ["data:image/png;base64,abc123"]


@pytest.mark.asyncio
async def test_direct_reply_preserves_user_images_after_context_guard(expert_agent):
    captured_messages = []

    class _MockLLM:
        async def chat_stream(self, messages):
            captured_messages.append(messages)
            if len(captured_messages) == 1:
                yield (
                    '{"image_kind":"other","detected_entities":[],"user_focus":"图像理解",'
                    '"summary":"这是用户上传的一张图表截图。"}'
                )
                return
            yield "这是图表解读"

    expert_agent._model_router = None
    expert_agent._llm = _MockLLM()

    events = []
    async for event in expert_agent.direct_reply(
        "这张图怎么看？",
        history=[],
        persona="rag",
        images=["data:image/png;base64,xyz456"],
    ):
        events.append(event)

    assert events[-1]["data"]["full_text"] == "这是图表解读"
    assert len(captured_messages) == 2
    user_message = captured_messages[-1][-1]
    assert user_message.role == "user"
    assert user_message.images == ["data:image/png;base64,xyz456"]


@pytest.mark.asyncio
async def test_generate_reply_stream_injects_image_summary_when_images_exist(expert_agent):
    captured_messages = []

    class _MockLLM:
        async def chat_stream(self, messages):
            captured_messages.append(messages)
            if len(captured_messages) == 1:
                yield (
                    '{"image_kind":"kline_chart","detected_entities":["宁德时代(300750)","日线"],'
                    '"user_focus":"支撑阻力","summary":"这是一张宁德时代日线K线图，用户想看支撑位和阻力位。"}'
                )
                return
            yield "结合图片来看，趋势仍在震荡。"

    expert_agent._model_router = None
    expert_agent._llm = _MockLLM()

    chunks = []
    async for token, full_text in expert_agent.generate_reply_stream(
        "帮我看看这张图的支撑位",
        nodes=[],
        memories=[],
        tool_results=[],
        history=[],
        persona="rag",
        images=["data:image/png;base64,summary001"],
    ):
        chunks.append((token, full_text))

    assert chunks[-1][1] == "结合图片来看，趋势仍在震荡。"
    assert len(captured_messages) == 2
    final_user_message = captured_messages[1][-1]
    assert final_user_message.role == "user"
    assert final_user_message.images == ["data:image/png;base64,summary001"]
    assert "这是一张宁德时代日线K线图" in final_user_message.content


@pytest.mark.asyncio
async def test_clarify_true_without_options_falls_back_to_safe_options(tmp_path):
    from engine.expert.agent import ExpertAgent

    class _MockLLM:
        async def chat_stream(self, messages):
            _ = messages
            yield (
                '{"should_clarify": true, "question_summary": "还需要进一步聚焦", '
                '"multi_select": false, "options": [], "reasoning": "需要继续确认重点", '
                '"needs_more": true}'
            )

    mock_tools = Mock()
    mock_tools.llm_engine = _MockLLM()
    mock_tools.execute = AsyncMock(return_value="tool result")
    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    result = await agent.clarify(
        "继续帮我细化分析角度",
        history=[{"role": "user", "content": "先看估值和行业逻辑"}],
        persona="rag",
        previous_selections=[
            {
                "round": 1,
                "selections": [
                    {
                        "option_id": "valuation",
                        "label": "A",
                        "title": "先看估值",
                        "focus": "估值、安全边际",
                        "skip": False,
                    }
                ],
            }
        ],
    )

    assert result.should_clarify is True
    assert result.round == 2
    assert len(result.options) >= 3
    assert result.skip_option.id == "skip"
    assert result.multi_select is True
    assert result.options[0].id == "valuation"


@pytest.mark.asyncio
async def test_clarify_with_images_passes_images_and_grounding_note_to_llm(tmp_path):
    from engine.expert.agent import ExpertAgent

    captured_messages = []

    class _MockLLM:
        async def chat_stream(self, messages):
            captured_messages.append(messages)
            if len(captured_messages) == 1:
                yield (
                    '{"image_kind":"kline_chart","detected_entities":["中泰化学","日K"],'
                    '"user_focus":"下跌原因","summary":"这是中泰化学的K线截图，用户想知道为什么一直跌。"}'
                )
                return
            yield (
                '{"should_clarify": false, "question_summary": "图片里的股票走势已经很明确，直接进入分析",'
                '"multi_select": false, "options": [], "reasoning": "图片已经补足上下文", "needs_more": false}'
            )

    mock_tools = Mock()
    mock_tools.llm_engine = _MockLLM()
    mock_tools.execute = AsyncMock(return_value="tool result")
    agent = ExpertAgent(mock_tools, kg_path=str(tmp_path / "kg.json"))

    result = await agent.clarify(
        "我这个怎么办",
        history=[],
        persona="rag",
        previous_selections=[],
        images=["data:image/png;base64,abc123"],
    )

    assert result.should_clarify is False
    assert len(captured_messages) == 2
    grounding_prompt = captured_messages[1][-1]
    assert grounding_prompt.images == ["data:image/png;base64,abc123"]
    assert "用户上传图片的结构化说明" in grounding_prompt.content
    assert "中泰化学" in grounding_prompt.content


def test_fallback_think_parse_batches_multi_stock_comprehensive_by_expert(expert_agent, monkeypatch):
    """多股票综合分析应按专家批量提问，而不是按股票逐只扇出"""
    monkeypatch.setattr(
        expert_agent,
        "_get_stock_name_map",
        lambda: {
            "贵州茅台": "600519",
            "宁德时代": "300750",
            "比亚迪": "002594",
            "招商银行": "600036",
            "美的集团": "000333",
        },
    )

    result = expert_agent._fallback_think_parse(
        text="",
        user_message="帮我看看贵州茅台、宁德时代、比亚迪、招商银行、美的集团怎么样",
    )

    expected_stock_hints = [
        "贵州茅台(600519)",
        "宁德时代(300750)",
        "比亚迪(002594)",
        "招商银行(600036)",
        "美的集团(000333)",
    ]

    assert result.needs_data is True
    assert [call.action for call in result.tool_calls] == ["data", "quant", "info", "industry"]
    assert len(result.tool_calls) == 4
    for call in result.tool_calls:
        question = call.params["question"]
        for stock_hint in expected_stock_hints:
            assert stock_hint in question


def test_fallback_think_parse_batches_multi_stock_detected_experts_by_expert(expert_agent, monkeypatch):
    """多股票定向专家分析应只按检测到的专家数生成调用"""
    monkeypatch.setattr(
        expert_agent,
        "_get_stock_name_map",
        lambda: {
            "贵州茅台": "600519",
            "宁德时代": "300750",
            "比亚迪": "002594",
        },
    )

    result = expert_agent._fallback_think_parse(
        text="量化专家和资讯专家都需要参与",
        user_message="贵州茅台、宁德时代、比亚迪的技术指标、新闻公告和为什么跌分别是什么原因",
    )

    expected_stock_hints = [
        "贵州茅台(600519)",
        "宁德时代(300750)",
        "比亚迪(002594)",
    ]

    assert result.needs_data is True
    assert sorted(call.action for call in result.tool_calls) == ["info", "quant"]
    assert len(result.tool_calls) == 2

    questions_by_action = {call.action: call.params["question"] for call in result.tool_calls}
    assert "技术指标" in questions_by_action["quant"]
    assert "新闻" in questions_by_action["info"]
    for question in questions_by_action.values():
        for stock_hint in expected_stock_hints:
            assert stock_hint in question


async def _async_gen(items):
    for item in items:
        yield item


async def _reply_stream_gen(*args, **kwargs):
    yield "最终", "最终"
    yield "回复", "最终回复"
