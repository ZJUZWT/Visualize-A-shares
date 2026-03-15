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
