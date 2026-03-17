# tests/test_event_assessor.py
"""事件影响评估测试"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock


class TestEventAssessorNoLLM:
    """无 LLM 时的降级行为"""

    def test_no_llm_returns_neutral(self):
        from engine.info.event_assessor import EventAssessor
        assessor = EventAssessor(llm_provider=None)
        result = asyncio.run(assessor.assess("600519", "控股股东增持5%"))
        assert result.impact == "neutral"
        assert result.magnitude == "low"
        assert "未配置" in result.reasoning

    def test_no_llm_with_context(self):
        from engine.info.event_assessor import EventAssessor
        assessor = EventAssessor(llm_provider=None)
        result = asyncio.run(assessor.assess(
            "600519", "公司发布业绩预增公告",
            stock_context={"industry": "白酒", "total_mv": 20000}
        ))
        assert result.impact == "neutral"


class TestEventAssessorWithLLM:
    """LLM 模式测试（mock）"""

    def test_llm_assess_positive(self):
        from engine.info.event_assessor import EventAssessor

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = json.dumps({
            "impact": "positive",
            "magnitude": "high",
            "reasoning": "控股股东大比例增持表明对公司前景高度看好",
            "affected_factors": ["市场情绪", "股权结构"]
        })

        assessor = EventAssessor(llm_provider=mock_llm)
        result = asyncio.run(assessor.assess("600519", "控股股东增持5%"))
        assert result.impact == "positive"
        assert result.magnitude == "high"
        assert len(result.affected_factors) == 2

    def test_llm_fallback_on_error(self):
        from engine.info.event_assessor import EventAssessor

        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("timeout")

        assessor = EventAssessor(llm_provider=mock_llm)
        result = asyncio.run(assessor.assess("600519", "某事件"))
        assert result.impact == "neutral"
        assert result.magnitude == "low"
