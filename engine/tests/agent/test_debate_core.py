"""专家辩论核心逻辑测试"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from agent.schemas import (
    Blackboard, DebateEntry, DataRequest, JudgeVerdict, AgentVerdict
)
from agent.debate import (
    validate_data_requests,
    _fallback_entry,
    _parse_debate_entry,
    _parse_judge_output,
)


# ── validate_data_requests ────────────────────────────

class TestValidateDataRequests:
    def _make_req(self, role, action):
        return DataRequest(requested_by=role, engine="quant", action=action, round=1)

    def test_filters_out_of_whitelist(self):
        reqs = [self._make_req("bull_expert", "hack_system")]
        result = validate_data_requests("bull_expert", reqs)
        assert result == []

    def test_allows_whitelisted_action(self):
        reqs = [self._make_req("bull_expert", "get_factor_scores")]
        result = validate_data_requests("bull_expert", reqs)
        assert len(result) == 1

    def test_truncates_beyond_max(self):
        reqs = [self._make_req("bull_expert", "get_factor_scores")] * 5
        result = validate_data_requests("bull_expert", reqs)
        assert len(result) == 2  # MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND = 2

    def test_retail_investor_only_gets_news(self):
        reqs = [
            self._make_req("retail_investor", "get_news"),
            self._make_req("retail_investor", "get_factor_scores"),  # 不允许
        ]
        result = validate_data_requests("retail_investor", reqs)
        assert len(result) == 1
        assert result[0].action == "get_news"


# ── _fallback_entry ──────────────────────────────────

class TestFallbackEntry:
    def test_debater_fallback(self):
        entry = _fallback_entry("bull_expert", round=2, reason="timeout")
        assert entry.stance == "insist"
        assert entry.speak is True
        assert entry.round == 2

    def test_observer_fallback(self):
        entry = _fallback_entry("retail_investor", round=1, reason="error")
        assert entry.speak is False
        assert entry.stance is None


# ── _parse_debate_entry ──────────────────────────────

class TestParseDebateEntry:
    def test_parses_valid_debater_json(self):
        raw = "坚持我的观点。PE合理，估值处于历史低位。\n【质疑】空头误判了行业周期"
        entry = _parse_debate_entry("bull_expert", round=1, raw=raw)
        assert entry.stance == "insist"
        assert len(entry.challenges) == 1

    def test_parses_observer_with_speak_false(self):
        raw = "【沉默】"
        entry = _parse_debate_entry("retail_investor", round=1, raw=raw)
        assert entry.speak is False

    def test_falls_back_on_invalid_json(self):
        entry = _parse_debate_entry("bull_expert", round=1, raw="not json at all")
        assert entry.stance == "insist"  # fallback

    def test_handles_markdown_code_block(self):
        raw = "认输，对方论据充分，我承认失败。\n【质疑】"
        entry = _parse_debate_entry("bear_expert", round=2, raw=raw)
        assert entry.stance == "concede"

    def test_parses_data_requests_in_entry(self):
        raw = "坚持观点，需要更多数据支撑。\n【数据请求】\nquant.get_factor_scores({\"code\": \"600519\"})"
        entry = _parse_debate_entry("bull_expert", round=1, raw=raw)
        assert len(entry.data_requests) == 1
        assert entry.data_requests[0].action == "get_factor_scores"
        assert entry.data_requests[0].requested_by == "bull_expert"


# ── _parse_judge_output ──────────────────────────────

class TestParseJudgeOutput:
    def test_injects_metadata(self):
        raw = '''{
            "summary": "综合来看...",
            "signal": "neutral",
            "score": 0.1,
            "key_arguments": ["多头论据"],
            "bull_core_thesis": "估值合理",
            "bear_core_thesis": "增速下行",
            "retail_sentiment_note": "散户偏乐观，反向信号",
            "smart_money_note": "资金流向中性",
            "risk_warnings": ["行业政策风险"],
            "debate_quality": "strong_disagreement"
        }'''
        bb = Blackboard(
            target="600519", debate_id="600519_20260314100000",
            termination_reason="max_rounds",
        )
        verdict = _parse_judge_output(raw=raw, blackboard=bb)
        assert verdict.target == "600519"
        assert verdict.debate_id == "600519_20260314100000"
        assert verdict.termination_reason == "max_rounds"
        assert isinstance(verdict.timestamp, datetime)
