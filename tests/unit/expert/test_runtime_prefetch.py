from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest


class FakeDataEngine:
    def __init__(self):
        self.profile_calls = []
        self.history_calls = []

    def get_company_profile(self, code):
        self.profile_calls.append(code)
        return {"code": code, "name": "宁德时代"}

    def get_daily_history(self, code, start, end):
        self.history_calls.append((code, start, end))
        return pd.DataFrame([
            {"date": "2026-03-20", "close": 201.0},
            {"date": "2026-03-23", "close": 205.0},
        ])


@pytest.mark.asyncio
async def test_agent_chat_emits_prefetch_ready_for_stock_code(tmp_path):
    from engine.expert.agent import ExpertAgent

    tools = Mock()
    tools.llm_engine = None
    tools.execute = AsyncMock(return_value="mock result")
    tools.data_engine = FakeDataEngine()

    agent = ExpertAgent(tools, kg_path=str(tmp_path / "kg.json"))

    events = []
    async for event in agent.chat("帮我看看300750现在怎么样"):
        events.append(event)

    prefetch = [e for e in events if e["event"] == "prefetch_ready"]
    assert len(prefetch) == 1
    assert prefetch[0]["data"]["stock_codes"] == ["300750"]
    assert tools.data_engine.profile_calls == ["300750"]
    assert len(tools.data_engine.history_calls) == 1


@pytest.mark.asyncio
async def test_agent_chat_prefetch_by_stock_name(tmp_path):
    from engine.expert.agent import ExpertAgent

    tools = Mock()
    tools.llm_engine = None
    tools.execute = AsyncMock(return_value="mock result")
    tools.data_engine = FakeDataEngine()

    agent = ExpertAgent(tools, kg_path=str(tmp_path / "kg.json"))
    agent._stock_name_map = {"宁德时代": "300750"}

    events = []
    async for event in agent.chat("宁德时代还值得看吗"):
        events.append(event)

    prefetch = [e for e in events if e["event"] == "prefetch_ready"]
    assert len(prefetch) == 1
    assert prefetch[0]["data"]["stock_codes"] == ["300750"]
