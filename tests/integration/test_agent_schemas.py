"""Agent schema 序列化和验证测试"""
import pytest
from datetime import datetime


def test_analysis_request_basic():
    from engine.arena.schemas import AnalysisRequest
    req = AnalysisRequest(
        trigger_type="user",
        target="600519",
        target_type="stock",
        depth="standard",
    )
    assert req.trigger_type == "user"
    assert req.target == "600519"
    assert req.user_context is None
    assert req.event_payload is None


def test_analysis_request_rejects_invalid_trigger():
    from engine.arena.schemas import AnalysisRequest
    with pytest.raises(Exception):
        AnalysisRequest(
            trigger_type="invalid",
            target="600519",
            target_type="stock",
            depth="standard",
        )


def test_evidence_model():
    from engine.arena.schemas import Evidence
    e = Evidence(factor="PE", value="12.5", impact="positive", weight=0.3)
    assert e.impact == "positive"


def test_agent_verdict_full():
    from engine.arena.schemas import AgentVerdict, Evidence
    v = AgentVerdict(
        agent_role="fundamental",
        signal="bullish",
        score=0.65,
        confidence=0.8,
        evidence=[
            Evidence(factor="PE", value="12.5 (行业偏低)", impact="positive", weight=0.3),
            Evidence(factor="ROE", value="8% (偏低)", impact="negative", weight=0.2),
        ],
        risk_flags=["业绩预告未出"],
        metadata={},
    )
    assert v.signal == "bullish"
    assert len(v.evidence) == 2
    assert v.evidence[1].impact == "negative"


def test_agent_verdict_rejects_invalid_signal():
    from engine.arena.schemas import AgentVerdict
    with pytest.raises(Exception):
        AgentVerdict(
            agent_role="fundamental",
            signal="very_bullish",
            score=0.5,
            confidence=0.8,
            evidence=[],
            risk_flags=[],
            metadata={},
        )


def test_aggregated_report():
    from engine.arena.schemas import AggregatedReport
    report = AggregatedReport(
        target="600519",
        overall_signal="bullish",
        overall_score=0.45,
        verdicts=[],
        conflicts=[],
        summary="测试摘要",
        risk_level="low",
        timestamp=datetime.now(),
    )
    assert report.overall_signal == "bullish"
    assert report.risk_level == "low"


def test_prescreen_result():
    from engine.arena.schemas import PreScreenResult
    r = PreScreenResult(
        should_continue=True,
        reason=None,
        critical_events=[],
        fast_verdict=None,
    )
    assert r.should_continue is True


def test_prescreen_result_short_circuit():
    from engine.arena.schemas import PreScreenResult, AggregatedReport
    report = AggregatedReport(
        target="600519",
        overall_signal="bearish",
        overall_score=-0.8,
        verdicts=[],
        conflicts=[],
        summary="重大利空：公司被 ST",
        risk_level="high",
        timestamp=datetime.now(),
    )
    r = PreScreenResult(
        should_continue=False,
        reason="重大利空事件",
        critical_events=[{"type": "ST", "detail": "公司被 ST"}],
        fast_verdict=report,
    )
    assert r.should_continue is False
    assert r.fast_verdict.verdicts == []
