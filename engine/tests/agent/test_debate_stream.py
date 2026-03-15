"""流式辩论测试: extract_structure, speak_stream, judge_summarize_stream"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def bb():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from agent.schemas import Blackboard
    b = Blackboard(target="600406", debate_id="test", max_rounds=2)
    b.round = 1
    return b


# ── extract_structure ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_structure_success(bb):
    from agent.debate import extract_structure

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=json.dumps({
        "stance": "insist",
        "confidence": 0.78,
        "challenges": ["质疑1", "质疑2"],
        "data_requests": [{"engine": "quant", "action": "get_factor_scores", "params": {"code": "600406"}}],
        "retail_sentiment_score": None,
        "speak": True,
    }))

    result = await extract_structure("这是一段论点...", "bull_expert", bb, mock_llm)

    assert result["stance"] == "insist"
    assert result["confidence"] == 0.78
    assert len(result["challenges"]) == 2
    assert len(result["data_requests"]) == 1
    assert result["data_requests"][0].engine == "quant"
    assert result["speak"] is True


@pytest.mark.asyncio
async def test_extract_structure_fallback_on_timeout(bb):
    import asyncio
    from agent.debate import extract_structure

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=asyncio.TimeoutError())

    result = await extract_structure("论点...", "bull_expert", bb, mock_llm)

    assert result["stance"] == "insist"
    assert result["confidence"] == 0.5
    assert result["challenges"] == []
    assert result["data_requests"] == []
    assert result["speak"] is True


@pytest.mark.asyncio
async def test_extract_structure_fallback_on_invalid_json(bb):
    from agent.debate import extract_structure

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value="这不是JSON")

    result = await extract_structure("论点...", "bull_expert", bb, mock_llm)

    assert result["stance"] == "insist"
    assert result["confidence"] == 0.5


# ── speak_stream ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_speak_stream_yields_tokens_then_complete(bb):
    from agent.debate import speak_stream
    from agent.memory import AgentMemory

    mock_llm = AsyncMock()

    async def fake_stream(messages):
        for char in ["国", "电", "南", "瑞", "是"]:
            yield char

    mock_llm.chat_stream = fake_stream
    mock_llm.chat = AsyncMock(return_value=json.dumps({
        "stance": "insist", "confidence": 0.8,
        "challenges": ["质疑1"], "data_requests": [],
        "retail_sentiment_score": None, "speak": True,
    }))

    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    events = []
    async for event in speak_stream("bull_expert", bb, mock_llm, mock_memory, False):
        events.append(event)

    token_events = [e for e in events if e["event"] == "debate_token"]
    complete_events = [e for e in events if e["event"] == "debate_entry_complete"]

    assert len(token_events) >= 1
    assert len(complete_events) == 1
    assert complete_events[0]["data"]["argument"] == "国电南瑞是"
    assert complete_events[0]["data"]["stance"] == "insist"
    assert len(bb.transcript) == 1


@pytest.mark.asyncio
async def test_speak_stream_handles_llm_interruption(bb):
    from agent.debate import speak_stream
    from agent.memory import AgentMemory

    mock_llm = AsyncMock()

    async def failing_stream(messages):
        yield "部分"
        yield "内容"
        raise ConnectionError("stream broken")

    mock_llm.chat_stream = failing_stream
    mock_llm.chat = AsyncMock(return_value='{"stance":"insist","confidence":0.5,"challenges":[],"data_requests":[],"speak":true}')

    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    events = []
    async for event in speak_stream("bull_expert", bb, mock_llm, mock_memory, False):
        events.append(event)

    complete = [e for e in events if e["event"] == "debate_entry_complete"][0]
    assert "(发言中断)" in complete["data"]["argument"]
    assert "部分内容" in complete["data"]["argument"]


@pytest.mark.asyncio
async def test_speak_stream_token_batching(bb):
    from agent.debate import speak_stream
    from agent.memory import AgentMemory

    mock_llm = AsyncMock()

    async def stream_with_punctuation(messages):
        for t in ["一", "二", "三", "。", "四", "五", "六", "七", "八", "九", "十", "末"]:
            yield t

    mock_llm.chat_stream = stream_with_punctuation
    mock_llm.chat = AsyncMock(return_value='{"stance":"insist","confidence":0.5,"challenges":[],"data_requests":[],"speak":true}')

    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    events = []
    async for event in speak_stream("bull_expert", bb, mock_llm, mock_memory, False):
        events.append(event)

    token_events = [e for e in events if e["event"] == "debate_token"]
    # 批次: ["一二三。"] (遇句号flush) + ["四五六七八"] (满5) + ["九十末"] (剩余flush)
    assert len(token_events) == 3
    assert token_events[0]["data"]["tokens"] == "一二三。"
    assert token_events[1]["data"]["tokens"] == "四五六七八"
    assert token_events[2]["data"]["tokens"] == "九十末"
