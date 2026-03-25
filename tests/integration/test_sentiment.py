# tests/test_sentiment.py
"""情感分析测试 — 规则模式 + mock LLM 模式"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock


class TestRuleSentiment:
    """规则模式情感分析测试"""

    def test_positive_title(self):
        from llm.capability import LLMCapability
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_capability=LLMCapability())
        result = asyncio.run(analyzer.analyze("贵州茅台业绩大增超预期"))
        assert result.sentiment == "positive"
        assert result.score > 0

    def test_negative_title(self):
        from llm.capability import LLMCapability
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_capability=LLMCapability())
        result = asyncio.run(analyzer.analyze("某公司财务造假被处罚"))
        assert result.sentiment == "negative"
        assert result.score < 0

    def test_neutral_title(self):
        from llm.capability import LLMCapability
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_capability=LLMCapability())
        result = asyncio.run(analyzer.analyze("某公司召开年度股东大会"))
        assert result.sentiment == "neutral"
        assert result.score == 0.0

    def test_content_contributes_to_score(self):
        from llm.capability import LLMCapability
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_capability=LLMCapability())
        # 标题中性但内容利好
        result = asyncio.run(analyzer.analyze("公司发布年报", "净利润同比增长50%，业绩大增"))
        assert result.score > 0


class TestLLMSentiment:
    """LLM 模式情感分析测试（mock）"""

    def test_llm_sentiment_positive(self):
        from llm.capability import LLMCapability
        from engine.info.sentiment import SentimentAnalyzer

        mock_cap = MagicMock(spec=LLMCapability)
        mock_cap.enabled = True
        mock_cap.classify = AsyncMock(return_value={
            "label": "positive",
            "score": 0.85,
            "reason": "业绩超预期利好",
        })

        analyzer = SentimentAnalyzer(llm_capability=mock_cap)
        result = asyncio.run(analyzer.analyze("茅台净利润增长30%"))
        assert result.sentiment == "positive"
        assert result.score == 0.85
        assert result.reason == "业绩超预期利好"

    def test_llm_fallback_on_parse_error(self):
        from llm.capability import LLMCapability
        from engine.info.sentiment import SentimentAnalyzer

        mock_cap = MagicMock(spec=LLMCapability)
        mock_cap.enabled = True
        mock_cap.classify = AsyncMock(side_effect=ValueError("parse_error"))

        analyzer = SentimentAnalyzer(llm_capability=mock_cap)
        # 应退化为规则模式而非抛异常
        result = asyncio.run(analyzer.analyze("某公司被处罚"))
        assert result.sentiment in ("positive", "negative", "neutral")

    def test_llm_fallback_on_exception(self):
        from llm.capability import LLMCapability
        from engine.info.sentiment import SentimentAnalyzer

        mock_cap = MagicMock(spec=LLMCapability)
        mock_cap.enabled = True
        mock_cap.classify = AsyncMock(side_effect=Exception("LLM API timeout"))

        analyzer = SentimentAnalyzer(llm_capability=mock_cap)
        result = asyncio.run(analyzer.analyze("某公司被处罚"))
        assert result.sentiment in ("positive", "negative", "neutral")
