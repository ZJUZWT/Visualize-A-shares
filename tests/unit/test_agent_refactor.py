# engine/tests/test_agent_refactor.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_run_agent_accepts_llm_capability():
    """run_agent() 接受 llm_capability 参数"""
    from llm.capability import LLMCapability
    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = True
    mock_cap.complete = AsyncMock(return_value='{"signal":"bullish","score":0.6,"confidence":0.8,"reasoning":"test","key_factors":["PE低"],"evidence":[],"risk_flags":[]}')
    from engine.arena.runner import run_agent
    result = run(run_agent(
        agent_role="fundamental",
        target="600519",
        data_context={"name": "茅台"},
        memory_context=[],
        calibration_weight=0.5,
        llm_capability=mock_cap,
    ))
    assert result.agent_role == "fundamental"
    assert result.signal == "bullish"
    mock_cap.complete.assert_called_once()


def test_orchestrator_accepts_llm_capability():
    """Orchestrator.__init__ 接受 llm_capability"""
    from llm.capability import LLMCapability
    from engine.arena.orchestrator import Orchestrator
    from engine.arena.memory import AgentMemory
    mock_cap = MagicMock(spec=LLMCapability)
    mock_memory = MagicMock(spec=AgentMemory)
    orch = Orchestrator(llm_capability=mock_cap, memory=mock_memory)
    assert orch is not None


def test_orchestrator_injects_rag(tmp_path):
    """Orchestrator 有 rag_store 时注入 historical_reports"""
    from llm.capability import LLMCapability
    from engine.arena.orchestrator import Orchestrator
    from engine.arena.memory import AgentMemory

    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = False
    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    mock_rag = MagicMock()
    mock_rag.search = MagicMock(return_value=[{"summary": "历史报告", "code": "600519", "signal": "bullish"}])

    mock_fetcher = MagicMock()
    mock_fetcher.fetch_all = AsyncMock(return_value={
        "fundamental": {}, "info": {}, "quant": {}
    })

    orch = Orchestrator(llm_capability=mock_cap, memory=mock_memory, data_fetcher=mock_fetcher, rag_store=mock_rag)

    events = []
    async def collect():
        async for event in orch.analyze(MagicMock(target="600519", depth="quick")):
            events.append(event)
    run(collect())

    mock_rag.search.assert_called_once()
    assert any(e.get("event") in ("phase", "result", "error") for e in events)
    fetch_call_count = mock_fetcher.fetch_all.call_count
    assert fetch_call_count == 1
    search_call_count = mock_rag.search.call_count
    assert search_call_count == 1


def test_data_fetcher_fetch_by_request_unknown_action():
    """未知 action 抛出 ValueError"""
    from engine.arena.data_fetcher import DataFetcher
    fetcher = DataFetcher()

    class FakeReq:
        action = "nonexistent_action"
        params = {}

    with pytest.raises(ValueError, match="不支持的 action"):
        run(fetcher.fetch_by_request(FakeReq()))


def test_data_fetcher_action_dispatch_has_expected_keys():
    """ACTION_DISPATCH 包含 spec 定义的全部 7 个 action"""
    from engine.arena.data_fetcher import ACTION_DISPATCH
    expected = {
        "get_stock_info", "get_daily_history", "get_technical_indicators",
        "get_factor_scores", "get_news", "get_announcements", "get_cluster_for_stock",
    }
    assert expected.issubset(set(ACTION_DISPATCH.keys()))


def test_data_fetcher_fetch_by_request_sync_action():
    """sync action 通过 asyncio.to_thread 调用"""
    from engine.arena.data_fetcher import DataFetcher, ACTION_DISPATCH
    fetcher = DataFetcher()

    class FakeReq:
        action = "get_stock_info"
        params = {"target": "600519"}

    mock_engine = MagicMock()
    mock_engine.get_profile = MagicMock(return_value={"name": "茅台"})

    with patch("engine.data.get_data_engine", return_value=mock_engine):
        result = run(fetcher.fetch_by_request(FakeReq()))
    assert result == {"name": "茅台"}
