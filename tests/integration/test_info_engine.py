# tests/test_info_engine.py
"""InfoEngine 门面集成测试"""
import pytest
import asyncio
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def mock_data_engine():
    de = MagicMock()
    de.get_news.return_value = pd.DataFrame({
        "title": ["茅台业绩大增", "白酒板块走强"],
        "content": ["净利润增长30%", "多只白酒股涨停"],
        "source": ["东方财富", "同花顺"],
        "publish_time": ["2026-03-14 10:00", "2026-03-14 11:00"],
        "url": ["http://a.com", "http://b.com"],
    })
    de.get_announcements.return_value = pd.DataFrame({
        "title": ["关于回购股份的公告"],
        "type": ["股份变动"],
        "date": ["2026-03-14"],
        "url": ["http://c.com"],
    })
    # mock DuckDB store
    store = MagicMock()
    store._conn = MagicMock()
    store._conn.execute.return_value.fetchall.return_value = []  # 无缓存
    de.store = store
    return de


class TestInfoEngineGetNews:
    def test_returns_news_with_sentiment(self, mock_data_engine):
        from engine.info.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        news = asyncio.run(ie.get_news("600519", limit=10))
        assert len(news) == 2
        assert news[0].title == "茅台业绩大增"
        assert news[0].sentiment is not None  # 规则模式应填充

    def test_returns_empty_on_no_data(self, mock_data_engine):
        mock_data_engine.get_news.return_value = pd.DataFrame()
        from engine.info.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        news = asyncio.run(ie.get_news("999999", limit=10))
        assert news == []


class TestInfoEngineGetAnnouncements:
    def test_returns_announcements_with_sentiment(self, mock_data_engine):
        from engine.info.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        anns = asyncio.run(ie.get_announcements("600519", limit=10))
        assert len(anns) == 1
        assert anns[0].type == "股份变动"


class TestInfoEngineAssessEvent:
    def test_assess_without_llm(self, mock_data_engine):
        from engine.info.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        impact = asyncio.run(ie.assess_event_impact("600519", "控股股东增持"))
        assert impact.impact == "neutral"
        assert "未配置" in impact.reasoning


class TestInfoEngineFactory:
    def test_get_info_engine_returns_singleton(self):
        import engine.info as info_module
        info_module._info_engine = None  # reset

        with patch("engine.info.get_data_engine") as mock_gde:
            mock_gde.return_value = MagicMock()
            mock_gde.return_value.store = MagicMock()
            ie1 = info_module.get_info_engine()
            ie2 = info_module.get_info_engine()
            assert ie1 is ie2

        info_module._info_engine = None  # cleanup
