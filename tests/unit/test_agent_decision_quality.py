"""Agent 决策质量模块测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from engine.agent.decision_quality import (
    build_decision_context,
    build_output_contract,
    build_system_prompt,
    gate_decisions,
    parse_decision_payload,
)


def test_build_system_prompt_includes_information_immunity_principles():
    prompt = build_system_prompt()

    assert "默认态度是怀疑" in prompt
    assert "不要因为单条消息改变策略" in prompt
    assert "Tier 1" in prompt


def test_build_decision_context_includes_digest_signal_and_memory_sections():
    context = build_decision_context(
        analysis_results=[
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "source": "watchlist",
                "daily": {"close": 1750},
                "indicators": {"rsi": 58},
            }
        ],
        portfolio={
            "cash_balance": 1000000.0,
            "total_asset": 1000000.0,
            "positions": [],
        },
        config={"single_position_pct": 0.15, "max_position_count": 10},
        memory_rules=[
            {"rule_text": "盈利单不要轻易补仓", "confidence": 0.8},
        ],
        digests=[
            {
                "stock_code": "600519",
                "summary": "白酒需求回暖，资金关注度提升",
                "impact_assessment": "minor_adjust",
                "key_evidence": ["news_count=3"],
            }
        ],
        signal_hits=[
            {
                "signal_id": "signal-1",
                "stock_code": "600519",
                "matched_keywords": ["白酒", "回暖"],
            }
        ],
    )

    assert "当前账户状态" in context
    assert "候选标的分析" in context
    assert "信息消化摘要" in context
    assert "历史经验" in context
    assert "白酒需求回暖，资金关注度提升" in context
    assert "盈利单不要轻易补仓" in context


def test_build_output_contract_requires_assessment_critique_and_decisions():
    contract = build_output_contract()

    assert '"assessment"' in contract
    assert '"self_critique"' in contract
    assert '"follow_up_questions"' in contract
    assert '"decisions"' in contract


def test_parse_decision_payload_handles_fenced_json_object():
    payload = parse_decision_payload(
        """```json
        {
          "assessment": {"market_posture": "neutral", "evidence_quality": "mixed"},
          "self_critique": ["证据不足，先等量价确认"],
          "follow_up_questions": ["是否已经放量？"],
          "decisions": []
        }
        ```"""
    )

    assert payload["assessment"]["market_posture"] == "neutral"
    assert payload["self_critique"] == ["证据不足，先等量价确认"]
    assert payload["follow_up_questions"] == ["是否已经放量？"]
    assert payload["decisions"] == []


def test_parse_decision_payload_accepts_legacy_array_output():
    payload = parse_decision_payload(
        '[{"stock_code":"600519","stock_name":"贵州茅台","action":"buy","price":1750.0,"quantity":100}]'
    )

    assert payload["assessment"] == {}
    assert payload["self_critique"] == []
    assert payload["follow_up_questions"] == []
    assert len(payload["decisions"]) == 1
    assert payload["decisions"][0]["stock_code"] == "600519"


def test_parse_decision_payload_falls_back_to_empty_payload_for_invalid_json():
    payload = parse_decision_payload("not-json")

    assert payload == {
        "assessment": {},
        "self_critique": [],
        "follow_up_questions": [],
        "decisions": [],
    }


def test_gate_decisions_rejects_all_actions_when_self_critique_requires_wait():
    result = gate_decisions(
        {
            "assessment": {"market_posture": "neutral"},
            "self_critique": ["证据不足，等待确认，不要现在下单"],
            "follow_up_questions": ["是否已经出现放量突破？"],
            "decisions": [
                {
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "action": "buy",
                    "price": 1750.0,
                    "quantity": 100,
                    "take_profit": 1820.0,
                    "stop_loss": 1690.0,
                    "confidence": 0.92,
                }
            ],
        }
    )

    assert result.accepted == []
    assert result.requires_wait is True
    assert result.rejected[0]["reason"] == "self_critique_requires_wait"


def test_gate_decisions_rejects_incomplete_or_low_confidence_actions():
    result = gate_decisions(
        {
            "assessment": {},
            "self_critique": [],
            "follow_up_questions": [],
            "decisions": [
                {
                    "stock_code": "600519",
                    "action": "buy",
                    "price": 1750.0,
                    "quantity": 100,
                    "take_profit": 1820.0,
                    "stop_loss": 1690.0,
                    "confidence": 0.81,
                },
                {
                    "stock_code": "000858",
                    "action": "buy",
                    "price": 132.0,
                    "quantity": 100,
                    "take_profit": 139.0,
                    "confidence": 0.88,
                },
                {
                    "stock_code": "601318",
                    "action": "buy",
                    "price": 45.0,
                    "quantity": 100,
                    "take_profit": 48.0,
                    "stop_loss": 42.0,
                    "confidence": 0.41,
                },
            ],
        },
        min_confidence=0.65,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0]["stock_code"] == "600519"
    assert [item["reason"] for item in result.rejected] == [
        "missing_stop_loss",
        "low_confidence",
    ]
