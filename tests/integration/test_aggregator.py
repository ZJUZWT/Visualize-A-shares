"""聚合逻辑测试 — 加权公式 + 冲突检测 + 信号判定"""
import pytest
from datetime import datetime


def _make_verdict(role, signal, score, confidence):
    from engine.arena.schemas import AgentVerdict
    return AgentVerdict(
        agent_role=role, signal=signal, score=score,
        confidence=confidence, evidence=[], risk_flags=[], metadata={},
    )


def test_aggregate_all_bullish():
    from engine.arena.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.6, 0.8),
        _make_verdict("info", "bullish", 0.5, 0.7),
        _make_verdict("quant", "bullish", 0.7, 0.9),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert report.overall_signal == "bullish"
    assert report.overall_score > 0.2
    assert report.conflicts == []


def test_aggregate_mixed_signals_detects_conflict():
    from engine.arena.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.7, 0.8),
        _make_verdict("info", "bearish", -0.6, 0.7),
        _make_verdict("quant", "neutral", 0.1, 0.5),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert len(report.conflicts) > 0


def test_aggregate_formula_correctness():
    """验证加权公式: weighted = score * confidence * calibration"""
    from engine.arena.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.5, 1.0),
        _make_verdict("info", "bearish", -0.5, 1.0),
        _make_verdict("quant", "neutral", 0.0, 1.0),
    ]
    calibrations = {"fundamental": 1.0, "info": 1.0, "quant": 1.0}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert abs(report.overall_score) < 0.01
    assert report.overall_signal == "neutral"


def test_aggregate_risk_level():
    from engine.arena.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bearish", -0.8, 0.9),
        _make_verdict("info", "bearish", -0.9, 0.8),
        _make_verdict("quant", "bearish", -0.7, 0.7),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert report.risk_level == "high"


def test_aggregate_partial_verdicts():
    """只有部分 Agent 成功时也能聚合"""
    from engine.arena.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.6, 0.8),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert report.overall_signal in ("bullish", "bearish", "neutral")
    assert len(report.verdicts) == 1
