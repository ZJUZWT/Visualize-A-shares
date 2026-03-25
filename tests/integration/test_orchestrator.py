"""Orchestrator 端到端编排测试"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock


MOCK_VERDICT = json.dumps({
    "signal": "bullish", "score": 0.5, "confidence": 0.7,
    "evidence": [{"factor": "test", "value": "ok", "impact": "positive", "weight": 0.5}],
    "risk_flags": [], "metadata": {},
})


@pytest.fixture
def mock_deps():
    """Mock 所有外部依赖"""
    from llm.capability import LLMCapability

    llm = MagicMock(spec=LLMCapability)
    llm.enabled = True
    llm.complete = AsyncMock(return_value=MOCK_VERDICT)

    memory = MagicMock()
    memory.recall.return_value = []
    memory.store.return_value = "doc_id"

    data_fetcher = AsyncMock()
    data_fetcher.fetch_all.return_value = {
        "fundamental": {"pe_ttm": 30, "pb": 8, "pct_chg": 1.5},
        "info": {"news": [], "announcements": []},
        "quant": {"rsi_14": 55, "macd": 0.05},
    }

    return llm, memory, data_fetcher


@pytest.mark.asyncio
async def test_orchestrator_full_flow(mock_deps):
    from engine.arena.orchestrator import Orchestrator
    from engine.arena.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps
    orch = Orchestrator(llm_capability=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="standard",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "result" in event_types

    result_event = [e for e in events if e["event"] == "result"][0]
    assert "report" in result_event["data"]
    assert result_event["data"]["report"]["target"] == "600519"


@pytest.mark.asyncio
async def test_orchestrator_handles_agent_failure(mock_deps):
    """某个 Agent 失败时，用剩余结果聚合"""
    from engine.arena.orchestrator import Orchestrator
    from engine.arena.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps

    call_count = 0
    llm.complete.side_effect = [
        MOCK_VERDICT,
        Exception("LLM timeout"),
        MOCK_VERDICT,
    ]
    orch = Orchestrator(llm_capability=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="standard",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    result_event = [e for e in events if e["event"] == "result"][0]
    assert len(result_event["data"]["report"]["verdicts"]) >= 1


@pytest.mark.asyncio
async def test_orchestrator_all_agents_fail(mock_deps):
    """所有 Agent 都失败时应返回 error 事件"""
    from engine.arena.orchestrator import Orchestrator
    from engine.arena.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps
    llm.complete.side_effect = Exception("LLM 全部超时")

    orch = Orchestrator(llm_capability=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="standard",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "error" in event_types
    assert "result" not in event_types


@pytest.mark.asyncio
async def test_orchestrator_quick_depth_skips_prescreen(mock_deps):
    """depth=quick 应跳过 PreScreen"""
    from engine.arena.orchestrator import Orchestrator
    from engine.arena.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps
    orch = Orchestrator(llm_capability=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="quick",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    phase_events = [e for e in events if e["event"] == "phase"]
    steps = [e["data"]["step"] for e in phase_events]
    assert "prescreen" not in steps
