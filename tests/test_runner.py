"""Agent Runner — LLM 调用与 JSON 解析测试"""
import pytest
import json
from unittest.mock import AsyncMock, patch


MOCK_VERDICT_JSON = json.dumps({
    "signal": "bullish",
    "score": 0.65,
    "confidence": 0.8,
    "evidence": [
        {"factor": "PE", "value": "12.5", "impact": "positive", "weight": 0.3},
        {"factor": "负债率", "value": "偏高", "impact": "negative", "weight": 0.2},
    ],
    "risk_flags": ["业绩预告未出"],
    "metadata": {},
})


@pytest.mark.asyncio
async def test_run_agent_returns_verdict():
    from agent.runner import run_agent

    mock_provider = AsyncMock()
    mock_provider.chat.return_value = MOCK_VERDICT_JSON

    verdict = await run_agent(
        agent_role="fundamental",
        target="600519",
        data_context={"pe_ttm": 30, "pb": 8},
        memory_context=[],
        calibration_weight=0.8,
        llm_provider=mock_provider,
    )
    assert verdict.signal == "bullish"
    assert verdict.agent_role == "fundamental"
    assert verdict.score == 0.65
    assert len(verdict.evidence) == 2


@pytest.mark.asyncio
async def test_run_agent_handles_malformed_json():
    from agent.runner import run_agent, AgentRunError

    mock_provider = AsyncMock()
    mock_provider.chat.return_value = "这不是 JSON，我来分析一下..."

    with pytest.raises(AgentRunError):
        await run_agent(
            agent_role="quant",
            target="600519",
            data_context={},
            memory_context=[],
            calibration_weight=0.7,
            llm_provider=mock_provider,
        )


@pytest.mark.asyncio
async def test_run_agent_handles_json_in_markdown():
    """LLM 有时会返回 ```json ... ``` 包裹的内容"""
    from agent.runner import run_agent

    mock_provider = AsyncMock()
    mock_provider.chat.return_value = f"```json\n{MOCK_VERDICT_JSON}\n```"

    verdict = await run_agent(
        agent_role="fundamental",
        target="600519",
        data_context={},
        memory_context=[],
        calibration_weight=0.8,
        llm_provider=mock_provider,
    )
    assert verdict.signal == "bullish"
