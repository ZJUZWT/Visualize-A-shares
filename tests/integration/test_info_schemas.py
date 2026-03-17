"""InfoEngine schema 验证测试"""
import pytest
from engine.info.schemas import NewsArticle, Announcement, SentimentResult, EventImpact


class TestNewsArticle:
    def test_valid_news(self):
        n = NewsArticle(
            title="贵州茅台2025年报出炉",
            source="东方财富",
            publish_time="2026-03-14 10:30",
        )
        assert n.title == "贵州茅台2025年报出炉"
        assert n.sentiment is None
        assert n.content is None

    def test_news_with_sentiment(self):
        n = NewsArticle(
            title="贵州茅台业绩大增50%",
            source="东方财富",
            publish_time="2026-03-14",
            sentiment="positive",
            sentiment_score=0.8,
        )
        assert n.sentiment == "positive"
        assert n.sentiment_score == 0.8

    def test_invalid_sentiment_value(self):
        with pytest.raises(Exception):
            NewsArticle(
                title="test",
                source="test",
                publish_time="2026-03-14",
                sentiment="very_good",  # invalid
            )


class TestAnnouncement:
    def test_valid_announcement(self):
        a = Announcement(
            title="关于回购股份的公告",
            type="股份变动",
            date="2026-03-14",
        )
        assert a.type == "股份变动"
        assert a.sentiment is None


class TestSentimentResult:
    def test_valid_result(self):
        r = SentimentResult(sentiment="negative", score=-0.6)
        assert r.sentiment == "negative"
        assert r.score == -0.6
        assert r.reason is None

    def test_with_reason(self):
        r = SentimentResult(sentiment="positive", score=0.9, reason="业绩超预期")
        assert r.reason == "业绩超预期"


class TestEventImpact:
    def test_valid_impact(self):
        e = EventImpact(
            event_desc="控股股东增持5%",
            impact="positive",
            magnitude="medium",
            reasoning="增持表明对公司前景有信心",
            affected_factors=["市场情绪", "股权结构"],
        )
        assert e.magnitude == "medium"
        assert len(e.affected_factors) == 2

    def test_invalid_magnitude(self):
        with pytest.raises(Exception):
            EventImpact(
                event_desc="test",
                impact="positive",
                magnitude="extreme",  # invalid
                reasoning="test",
                affected_factors=[],
            )
