# tests/test_sentiment.py
"""情感分析测试 — 规则模式 + mock LLM 模式"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock


class TestRuleSentiment:
    """规则模式情感分析测试"""

    def test_positive_title(self):
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        result = asyncio.run(analyzer.analyze("贵州茅台业绩大增超预期"))
        assert result.sentiment == "positive"
        assert result.score > 0

    def test_negative_title(self):
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        result = asyncio.run(analyzer.analyze("某公司财务造假被处罚"))
        assert result.sentiment == "negative"
        assert result.score < 0

    def test_neutral_title(self):
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        result = asyncio.run(analyzer.analyze("某公司召开年度股东大会"))
        assert result.sentiment == "neutral"
        assert result.score == 0.0

    def test_content_contributes_to_score(self):
        from engine.info.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        # 标题中性但内容利好
        result = asyncio.run(analyzer.analyze("公司发布年报", "净利润同比增长50%，业绩大增"))
        assert result.score > 0


class TestLLMSentiment:
    """LLM 模式情感分析测试（mock）"""

    def test_llm_sentiment_positive(self):
        from engine.info.sentiment import SentimentAnalyzer

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = json.dumps({
            "sentiment": "positive",
            "score": 0.85,
            "reason": "业绩超预期利好"
        })

        analyzer = SentimentAnalyzer(llm_provider=mock_llm)
        result = asyncio.run(analyzer.analyze("茅台净利润增长30%"))
        assert result.sentiment == "positive"
        assert result.score == 0.85
        assert result.reason == "业绩超预期利好"

    def test_llm_fallback_on_parse_error(self):
        from engine.info.sentiment import SentimentAnalyzer

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "这不是一个有效的JSON"

        analyzer = SentimentAnalyzer(llm_provider=mock_llm)
        # 应退化为规则模式而非抛异常
        result = asyncio.run(analyzer.analyze("某公司被处罚"))
        assert result.sentiment in ("positive", "negative", "neutral")

    def test_llm_fallback_on_exception(self):
        from engine.info.sentiment import SentimentAnalyzer

        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("LLM API timeout")

        analyzer = SentimentAnalyzer(llm_provider=mock_llm)
        result = asyncio.run(analyzer.analyze("某公司被处罚"))
        assert result.sentiment in ("positive", "negative", "neutral")
