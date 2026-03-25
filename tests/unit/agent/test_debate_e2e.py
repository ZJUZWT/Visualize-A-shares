"""专家辩论 E2E 冒烟测试 — mock LLM，验证完整辩论流程"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from engine.arena.schemas import Blackboard, AgentVerdict
from engine.arena.debate import run_debate
from engine.arena.memory import AgentMemory
from engine.arena.data_fetcher import DataFetcher
from engine.industry.schemas import CapitalStructure, IndustryCognition


def _make_debater_response(round_num: int, concede: bool = False) -> str:
    stance = "concede" if concede else "insist"
    return f"{'认输' if concede else '坚持'}我的观点。第{round_num}轮论据充分。\n【质疑】对方论据不成立"


def _make_extract_response(concede: bool = False) -> str:
    return json.dumps({
        "stance": "concede" if concede else "insist",
        "confidence": 0.3 if concede else 0.8,
        "challenges": ["对方论据不成立"],
        "data_requests": [],
        "retail_sentiment_score": None,
        "speak": True,
    })


def _make_observer_response(speak: bool = False) -> str:
    if speak:
        return "观察员发言内容。"
    return "【沉默】"


def _make_observer_extract(speak: bool = False) -> str:
    return json.dumps({
        "stance": "insist", "confidence": 0.5,
        "challenges": [], "data_requests": [],
        "retail_sentiment_score": None, "speak": speak,
    })


def _make_judge_response() -> str:
    return json.dumps({
        "summary": "综合来看，多空双方各有道理",
        "signal": "neutral",
        "score": 0.1,
        "key_arguments": ["多头论据1", "空头论据1"],
        "bull_core_thesis": "估值合理",
        "bear_core_thesis": "增速下行",
        "retail_sentiment_note": "散户偏乐观，反向信号",
        "smart_money_note": "资金流向中性",
        "risk_warnings": ["行业政策风险"],
        "debate_quality": "strong_disagreement",
    })


@pytest.fixture
def mock_memory():
    memory = MagicMock(spec=AgentMemory)
    memory.recall.return_value = []
    memory.store.return_value = None
    return memory


@pytest.fixture
def mock_data_fetcher():
    fetcher = MagicMock(spec=DataFetcher)

    async def _fetch_by_request(req):
        code = req.params.get("code", "600519")
        if req.action == "get_stock_info":
            return {
                "code": code,
                "name": "贵州茅台" if code == "600519" else "平安银行",
                "industry": "白酒" if code == "600519" else "银行",
            }
        if req.action == "get_daily_history":
            return {
                "code": code,
                "days": req.params.get("days", 60),
                "recent": [
                    {
                        "date": "2026-03-13",
                        "open": 1500.0,
                        "high": 1510.0,
                        "low": 1490.0,
                        "close": 1505.0,
                        "pct_chg": 1.2,
                        "turnover_rate": 0.8,
                    }
                ],
            }
        if req.action == "get_news":
            return [{"title": "测试新闻", "sentiment": "neutral"}]
        return {}

    fetcher.fetch_by_request.side_effect = _fetch_by_request
    return fetcher


@pytest.fixture
def mock_industry_engine():
    engine = MagicMock()
    engine.analyze = AsyncMock(return_value=IndustryCognition(
        industry="白酒",
        target="600519",
        upstream=["高粱", "包装"],
        downstream=["经销商", "消费终端"],
        common_traps=["渠道库存误判"],
        cycle_position="高位震荡",
        as_of_date="2026-03-14",
    ))
    engine.get_capital_structure = AsyncMock(return_value=CapitalStructure(
        code="600519",
        as_of_date="2026-03-14",
        turnover_rate=0.8,
        structure_summary="主力资金中性",
    ))
    return engine


def _make_mock_llm(rounds: int, bull_concede_round: int | None = None):
    """构建 mock LLM，chat_stream 返回自然语言，chat 返回结构化提取"""
    llm = AsyncMock()

    # chat_stream: 每次调用返回简短文本
    stream_call_count = [0]

    async def mock_chat_stream(messages):
        stream_call_count[0] += 1
        for char in "测试发言内容。":
            yield char

    llm.chat_stream = mock_chat_stream

    # chat: 用于 extract_structure（每个 debater/observer）+ judge
    chat_responses = []
    for r in range(1, rounds + 1):
        concede = (bull_concede_round == r)
        chat_responses.append(_make_extract_response(concede=concede))   # bull extract
        chat_responses.append(_make_extract_response())                   # bear extract
        chat_responses.append(_make_observer_extract(speak=False))        # retail extract
        chat_responses.append(_make_observer_extract(speak=False))        # smart_money extract
    chat_responses.append(_make_judge_response())                         # judge

    llm.chat = AsyncMock(side_effect=chat_responses)
    return llm


class TestDebateE2E:
    """完整辩论流程冒烟测试"""

    @pytest.mark.asyncio
    async def test_full_3_round_debate(self, mock_memory, mock_data_fetcher, mock_industry_engine):
        """3 轮辩论 → 裁判总结，验证 SSE 事件序列"""
        mock_llm = _make_mock_llm(rounds=3)

        bb = Blackboard(
            target="600519",
            debate_id="600519_20260314100000",
            worker_verdicts=[
                AgentVerdict(
                    agent_role="fundamental", signal="bullish",
                    score=0.6, confidence=0.8,
                    evidence=[], risk_flags=[],
                ),
            ],
            conflicts=["基本面看多 vs 技术面看空"],
            max_rounds=3,
        )

        events = []
        with (
            patch("engine.arena.debate.persist_debate", new_callable=AsyncMock),
            patch("engine.industry.get_industry_engine", return_value=mock_industry_engine),
        ):
            async for event in run_debate(bb, mock_llm, mock_memory, mock_data_fetcher):
                events.append(event)

        event_types = [e["event"] for e in events]

        assert event_types[0] == "debate_start"
        assert "debate_round_start" in event_types
        assert "debate_token" in event_types
        assert "debate_entry_complete" in event_types
        assert "debate_end" in event_types
        assert "judge_verdict" in event_types

        start_data = events[0]["data"]
        assert start_data["target"] == "600519"
        assert start_data["max_rounds"] == 3

        verdict_event = [e for e in events if e["event"] == "judge_verdict"][0]
        assert verdict_event["data"]["signal"] == "neutral"
        assert verdict_event["data"]["target"] == "600519"

        assert bb.status == "completed"
        assert bb.termination_reason == "max_rounds"
        assert bb.round == 3

    @pytest.mark.asyncio
    async def test_early_termination_bull_concedes(self, mock_memory, mock_data_fetcher, mock_industry_engine):
        """多头第 1 轮认输 → 提前终止"""
        mock_llm = _make_mock_llm(rounds=1, bull_concede_round=1)

        bb = Blackboard(
            target="000001",
            debate_id="000001_20260314100000",
            max_rounds=3,
        )

        events = []
        with (
            patch("engine.arena.debate.persist_debate", new_callable=AsyncMock),
            patch("engine.industry.get_industry_engine", return_value=mock_industry_engine),
        ):
            async for event in run_debate(bb, mock_llm, mock_memory, mock_data_fetcher):
                events.append(event)

        assert bb.round == 1
        assert bb.termination_reason == "bull_conceded"
        assert bb.bull_conceded is True

        round_starts = [e for e in events if e["event"] == "debate_round_start"]
        assert len(round_starts) == 1

    @pytest.mark.asyncio
    async def test_llm_stream_failure_uses_fallback(self, mock_memory, mock_data_fetcher, mock_industry_engine):
        """chat_stream 异常时使用 fallback，辩论不中断"""
        llm = AsyncMock()
        call_count = [0]

        async def flaky_stream(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("stream broken")
            for char in "正常发言内容。":
                yield char

        llm.chat_stream = flaky_stream

        # 每轮 4 次 extract + judge
        chat_responses = []
        for _ in range(3):
            chat_responses += [
                _make_extract_response(), _make_extract_response(),
                _make_observer_extract(), _make_observer_extract(),
            ]
        chat_responses.append(_make_judge_response())
        llm.chat = AsyncMock(side_effect=chat_responses)

        bb = Blackboard(
            target="600519",
            debate_id="600519_20260314110000",
            max_rounds=3,
        )

        events = []
        with (
            patch("engine.arena.debate.persist_debate", new_callable=AsyncMock),
            patch("engine.industry.get_industry_engine", return_value=mock_industry_engine),
        ):
            async for event in run_debate(bb, llm, mock_memory, mock_data_fetcher):
                events.append(event)

        assert bb.status == "completed"
        assert bb.round == 3
