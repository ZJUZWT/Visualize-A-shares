from unittest.mock import AsyncMock, Mock

import pytest


def test_tool_execution_planner_runs_quant_in_parallel_when_code_is_known():
    from engine.expert.schemas import ToolCall
    from engine.runtime.context import ExecutionContext
    from engine.runtime.planner import ToolExecutionPlanner

    planner = ToolExecutionPlanner()
    context = ExecutionContext(message="看看宁德时代", module="expert")
    context.entities.stock_codes = ["300750"]

    phases = planner.plan(
        [
            ToolCall(engine="expert", action="data", params={"question": "看数据"}),
            ToolCall(engine="expert", action="quant", params={"question": "看技术面"}),
        ],
        context=context,
    )

    assert len(phases) == 1
    assert [call.action for call in phases[0]] == ["data", "quant"]


def test_tool_execution_planner_falls_back_to_two_phases_when_dependency_unknown():
    from engine.expert.schemas import ToolCall
    from engine.runtime.context import ExecutionContext
    from engine.runtime.planner import ToolExecutionPlanner

    planner = ToolExecutionPlanner()
    context = ExecutionContext(message="帮我分析这只票", module="expert")

    phases = planner.plan(
        [
            ToolCall(engine="expert", action="data", params={"question": "看数据"}),
            ToolCall(engine="expert", action="quant", params={"question": "看技术面"}),
        ],
        context=context,
    )

    assert len(phases) == 2
    assert [call.action for call in phases[0]] == ["data"]
    assert [call.action for call in phases[1]] == ["quant"]


@pytest.mark.asyncio
async def test_agent_chat_emits_early_insight_before_reply_complete(tmp_path):
    from engine.expert.agent import ExpertAgent
    from engine.expert.schemas import ThinkOutput, ToolCall

    tools = Mock()
    tools.llm_engine = object()
    tools.execute = AsyncMock(return_value="tool result")
    tools.data_engine = None
    agent = ExpertAgent(tools, kg_path=str(tmp_path / "kg.json"))

    agent.recall_and_think = AsyncMock(return_value=(
        [],
        [],
        ThinkOutput(
            needs_data=True,
            tool_calls=[ToolCall(engine="expert", action="data", params={"question": "看看数据"})],
            reasoning="先拿到数据结论",
        ),
    ))

    async def fake_execute_tools_streaming(tool_calls, context=None):
        yield {
            "engine": "expert",
            "action": "data",
            "result": "结论：趋势转强，可以继续跟踪。",
            "is_expert": True,
        }

    async def fake_reply_stream(*args, **kwargs):
        yield "最终", "最终"
        yield "回复", "最终回复"

    agent.execute_tools_streaming = fake_execute_tools_streaming
    agent.generate_reply_stream = fake_reply_stream
    agent.learn_from_context = AsyncMock(return_value=None)
    agent.belief_update = AsyncMock(return_value=[])
    agent._self_critique = AsyncMock(return_value={
        "summary": "仍需确认量能。",
        "risks": [],
        "missing_data": [],
        "counterpoints": [],
        "confidence_note": "",
    })

    events = []
    async for event in agent.chat("测试问题"):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "early_insight" in event_types
    assert event_types.index("early_insight") < event_types.index("reply_complete")
