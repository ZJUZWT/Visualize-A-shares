"""专家辩论数据模型测试"""

import pytest
from datetime import datetime
from agent.schemas import (
    Blackboard, DebateEntry, DataRequest, JudgeVerdict, AgentVerdict
)


def make_verdict(role="fundamental"):
    return AgentVerdict(
        agent_role=role, signal="bullish", score=0.5,
        confidence=0.7, evidence=[], risk_flags=[]
    )


class TestBlackboard:
    def test_default_values(self):
        bb = Blackboard(target="600519", debate_id="600519_20260314100000")
        assert bb.round == 0
        assert bb.max_rounds == 3
        assert bb.status == "debating"
        assert bb.bull_conceded is False
        assert bb.bear_conceded is False
        assert bb.termination_reason is None
        assert bb.transcript == []
        assert bb.data_requests == []

    def test_accepts_worker_verdicts(self):
        bb = Blackboard(
            target="600519", debate_id="600519_20260314100000",
            worker_verdicts=[make_verdict(), make_verdict("quant")],
            conflicts=["基本面 vs 量化分歧"],
        )
        assert len(bb.worker_verdicts) == 2
        assert len(bb.conflicts) == 1


class TestDebateEntry:
    def test_debater_entry(self):
        entry = DebateEntry(
            role="bull_expert", round=1,
            stance="insist", speak=True,
            argument="估值合理，上涨可期",
            challenges=["空头的PE论据有误"],
            confidence=0.8,
        )
        assert entry.stance == "insist"
        assert entry.retail_sentiment_score is None

    def test_observer_silent_entry(self):
        entry = DebateEntry(role="retail_investor", round=1, speak=False)
        assert entry.speak is False
        assert entry.argument == ""
        assert entry.stance is None

    def test_retail_sentiment_score(self):
        entry = DebateEntry(
            role="retail_investor", round=1, speak=True,
            argument="论坛上都在喊冲", retail_sentiment_score=0.9
        )
        assert entry.retail_sentiment_score == 0.9


class TestDataRequest:
    def test_default_pending(self):
        req = DataRequest(
            requested_by="bull_expert", engine="quant",
            action="get_factor_scores", params={"code": "600519"}, round=1
        )
        assert req.status == "pending"
        assert req.result is None


class TestJudgeVerdict:
    def test_optional_signal(self):
        v = JudgeVerdict(
            target="600519", debate_id="600519_20260314100000",
            summary="综合来看...", signal=None, score=None,
            key_arguments=["多头：估值合理", "空头：增长放缓"],
            bull_core_thesis="估值合理，成长确定",
            bear_core_thesis="宏观压力，增速下行",
            retail_sentiment_note="散户偏乐观，需警惕反转",
            smart_money_note="资金流向中性",
            risk_warnings=["行业政策风险", "汇率波动"],
            debate_quality="strong_disagreement",
            termination_reason="max_rounds",
            timestamp=datetime.now(),
        )
        assert v.signal is None
        assert v.score is None
        assert len(v.risk_warnings) == 2
