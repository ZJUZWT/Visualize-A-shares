"""专家辩论 E2E 冒烟测试 — mock LLM，验证完整辩论流程"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from agent.schemas import Blackboard, AgentVerdict
from agent.debate import run_debate
from agent.memory import AgentMemory
from agent.data_fetcher import DataFetcher


def _make_bull_response(round_num: int, concede: bool = False) -> str:
    return json.dumps({
        "stance": "concede" if concede else "insist",
        "argument": f"多头第{round_num}轮论据",
        "challenges": ["空头论据不成立"],
        "confidence": 0.3 if concede else 0.8,
        "data_requests": [],
    })


def _make_bear_response(round_num: int, concede: bool = False) -> str:
    return json.dumps({
        "stance": "concede" if concede else "insist",
        "argument": f"空头第{round_num}轮论据",
        "challenges": ["多头论据不成立"],
        "confidence": 0.3 if concede else 0.75,
        "data_requests": [],
    })


def _make_observer_response(speak: bool = False) -> str:
    return json.dumps({
        "speak": speak,
        "argument": "观察员发言" if speak else "",
        "data_requests": [],
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
def mock_llm():
    """Mock LLM provider，按调用顺序返回不同角色的响应"""
    llm = AsyncMock()
    return llm


@pytest.fixture
def mock_memory():
    memory = MagicMock(spec=AgentMemory)
    memory.recall.return_value = []
    memory.store.return_value = None
    return memory


@pytest.fixture
def mock_data_fetcher():
    return MagicMock(spec=DataFetcher)


class TestDebateE2E:
    """完整辩论流程冒烟测试"""

    @pytest.mark.asyncio
    async def test_full_3_round_debate(self, mock_llm, mock_memory, mock_data_fetcher):
        """3 轮辩论 → 裁判总结，验证 SSE 事件序列"""
        # 每轮 4 次调用: bull, bear, retail, smart_money
        # 最后 1 次: judge
        mock_llm.chat = AsyncMock(side_effect=[
            # Round 1
            _make_bull_response(1), _make_bear_response(1),
            _make_observer_response(), _make_observer_response(),
            # Round 2
            _make_bull_response(2), _make_bear_response(2),
            _make_observer_response(), _make_observer_response(),
            # Round 3 (final)
            _make_bull_response(3), _make_bear_response(3),
            _make_observer_response(), _make_observer_response(),
            # Judge
            _make_judge_response(),
        ])

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
        with patch("agent.debate.persist_debate", new_callable=AsyncMock):
            async for event in run_debate(bb, mock_llm, mock_memory, mock_data_fetcher):
                events.append(event)

        event_types = [e["event"] for e in events]

        # 验证事件序列
        assert event_types[0] == "debate_start"
        assert "debate_round_start" in event_types
        assert "debate_entry" in event_types
        assert "debate_end" in event_types
        assert "judge_verdict" in event_types

        # 验证 debate_start 数据
        start_data = events[0]["data"]
        assert start_data["target"] == "600519"
        assert start_data["max_rounds"] == 3

        # 验证裁判结果
        verdict_event = [e for e in events if e["event"] == "judge_verdict"][0]
        assert verdict_event["data"]["signal"] == "neutral"
        assert verdict_event["data"]["target"] == "600519"

        # 验证 Blackboard 最终状态
        assert bb.status == "completed"
        assert bb.termination_reason == "max_rounds"
        assert bb.round == 3

    @pytest.mark.asyncio
    async def test_early_termination_bull_concedes(self, mock_llm, mock_memory, mock_data_fetcher):
        """多头第 1 轮认输 → 提前终止"""
        mock_llm.chat = AsyncMock(side_effect=[
            # Round 1: bull concedes
            _make_bull_response(1, concede=True), _make_bear_response(1),
            _make_observer_response(), _make_observer_response(),
            # Judge
            _make_judge_response(),
        ])

        bb = Blackboard(
            target="000001",
            debate_id="000001_20260314100000",
            max_rounds=3,
        )

        events = []
        with patch("agent.debate.persist_debate", new_callable=AsyncMock):
            async for event in run_debate(bb, mock_llm, mock_memory, mock_data_fetcher):
                events.append(event)

        assert bb.round == 1
        assert bb.termination_reason == "bull_conceded"
        assert bb.bull_conceded is True

        # 只有 1 轮 + judge
        round_starts = [e for e in events if e["event"] == "debate_round_start"]
        assert len(round_starts) == 1

    @pytest.mark.asyncio
    async def test_llm_failure_uses_fallback(self, mock_llm, mock_memory, mock_data_fetcher):
        """LLM 超时/异常时使用 fallback 发言，辩论不中断"""
        mock_llm.chat = AsyncMock(side_effect=[
            # Round 1: bull fails, bear ok
            Exception("LLM 服务不可用"), _make_bear_response(1),
            _make_observer_response(), _make_observer_response(),
            # Round 2: both ok
            _make_bull_response(2), _make_bear_response(2),
            _make_observer_response(), _make_observer_response(),
            # Round 3
            _make_bull_response(3), _make_bear_response(3),
            _make_observer_response(), _make_observer_response(),
            # Judge
            _make_judge_response(),
        ])

        bb = Blackboard(
            target="600519",
            debate_id="600519_20260314110000",
            max_rounds=3,
        )

        events = []
        with patch("agent.debate.persist_debate", new_callable=AsyncMock):
            async for event in run_debate(bb, mock_llm, mock_memory, mock_data_fetcher):
                events.append(event)

        # 辩论完成，没有中断
        assert bb.status == "completed"
        assert bb.round == 3

        # Round 1 的 bull_expert 使用了 fallback（stance=insist）
        r1_bull = [e for e in bb.transcript if e.role == "bull_expert" and e.round == 1][0]
        assert r1_bull.stance == "insist"
        assert "不可用" in r1_bull.argument
