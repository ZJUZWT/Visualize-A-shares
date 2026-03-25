# tests/test_event_assessor.py
"""事件影响评估测试"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock


class TestEventAssessorNoLLM:
    """无 LLM 时的降级行为"""

    def test_no_llm_returns_neutral(self):
        from llm.capability import LLMCapability
        from engine.info.event_assessor import EventAssessor
        assessor = EventAssessor(llm_capability=LLMCapability())
        result = asyncio.run(assessor.assess("600519", "控股股东增持5%"))
        assert result.impact == "neutral"
        assert result.magnitude == "low"
        assert "未配置" in result.reasoning

    def test_no_llm_with_context(self):
        from llm.capability import LLMCapability
        from engine.info.event_assessor import EventAssessor
        assessor = EventAssessor(llm_capability=LLMCapability())
        result = asyncio.run(assessor.assess(
            "600519", "公司发布业绩预增公告",
            stock_context={"industry": "白酒", "total_mv": 20000}
        ))
        assert result.impact == "neutral"


class TestEventAssessorWithLLM:
    """LLM 模式测试（mock）"""

    def test_llm_assess_positive(self):
        from llm.capability import LLMCapability
        from engine.info.event_assessor import EventAssessor

        mock_cap = MagicMock(spec=LLMCapability)
        mock_cap.enabled = True
        mock_cap.extract = AsyncMock(return_value={
            "impact": "positive",
            "magnitude": "high",
            "reasoning": "控股股东大比例增持表明对公司前景高度看好",
            "affected_factors": ["市场情绪", "股权结构"],
        })

        assessor = EventAssessor(llm_capability=mock_cap)
        result = asyncio.run(assessor.assess("600519", "控股股东增持5%"))
        assert result.impact == "positive"
        assert result.magnitude == "high"
        assert len(result.affected_factors) == 2

    def test_llm_fallback_on_error(self):
        from llm.capability import LLMCapability
        from engine.info.event_assessor import EventAssessor

        mock_cap = MagicMock(spec=LLMCapability)
        mock_cap.enabled = True
        mock_cap.extract = AsyncMock(side_effect=Exception("timeout"))

        assessor = EventAssessor(llm_capability=mock_cap)
        result = asyncio.run(assessor.assess("600519", "某事件"))
        assert result.impact == "neutral"
        assert result.magnitude == "low"
