# tests/test_data_news.py
"""DataEngine 新闻/公告数据源测试"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


class TestBaseDataSourceDefaults:
    """BaseDataSource 默认方法应 raise NotImplementedError"""

    def test_get_stock_news_not_implemented(self):
        from data_engine.sources.base import BaseDataSource

        class MinimalSource(BaseDataSource):
            name = "test"
            priority = 99
            def get_realtime_quotes(self): return pd.DataFrame()
            def get_daily_history(self, code, start, end): return pd.DataFrame()
            def get_financial_data(self, code, year, quarter): return pd.DataFrame()

        source = MinimalSource()
        with pytest.raises(NotImplementedError):
            source.get_stock_news("600519")

    def test_get_announcements_not_implemented(self):
        from data_engine.sources.base import BaseDataSource

        class MinimalSource(BaseDataSource):
            name = "test"
            priority = 99
            def get_realtime_quotes(self): return pd.DataFrame()
            def get_daily_history(self, code, start, end): return pd.DataFrame()
            def get_financial_data(self, code, year, quarter): return pd.DataFrame()

        source = MinimalSource()
        with pytest.raises(NotImplementedError):
            source.get_announcements("600519")


class TestAKShareNewsSource:
    """AKShareSource 新闻/公告方法测试（mock akshare）"""

    def test_get_stock_news_returns_dataframe(self):
        mock_ak = MagicMock()
        mock_ak.stock_news_em.return_value = pd.DataFrame({
            "新闻标题": ["茅台业绩大增", "白酒板块走强"],
            "新闻内容": ["内容A", "内容B"],
            "发布时间": ["2026-03-14 10:00", "2026-03-14 11:00"],
            "文章来源": ["东方财富", "同花顺"],
            "新闻链接": ["http://a.com", "http://b.com"],
        })

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            from data_engine.sources.akshare_source import AKShareSource
            source = AKShareSource.__new__(AKShareSource)
            source._ak = mock_ak

            df = source.get_stock_news("600519", limit=10)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
            assert "title" in df.columns
            assert "source" in df.columns

    def test_get_stock_news_empty_on_failure(self):
        mock_ak = MagicMock()
        mock_ak.stock_news_em.side_effect = Exception("API error")

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            from data_engine.sources.akshare_source import AKShareSource
            source = AKShareSource.__new__(AKShareSource)
            source._ak = mock_ak

            df = source.get_stock_news("600519")
            assert isinstance(df, pd.DataFrame)
            assert df.empty

    def test_get_announcements_returns_dataframe(self):
        mock_ak = MagicMock()
        mock_ak.stock_notice_report_em.return_value = pd.DataFrame({
            "公告标题": ["关于回购股份的公告"],
            "公告类型": ["股份变动"],
            "公告日期": ["2026-03-14"],
            "公告链接": ["http://a.com"],
        })

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            from data_engine.sources.akshare_source import AKShareSource
            source = AKShareSource.__new__(AKShareSource)
            source._ak = mock_ak

            df = source.get_announcements("600519", limit=10)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 1
            assert "title" in df.columns
            assert "type" in df.columns


class TestDataCollectorNews:
    """DataCollector 新闻降级编排测试"""

    def test_get_stock_news_delegates_to_source(self):
        from data_engine.collector import DataCollector

        collector = DataCollector.__new__(DataCollector)
        mock_source = MagicMock()
        mock_source.get_stock_news.return_value = pd.DataFrame({"title": ["test"]})
        mock_source.priority = 0
        mock_source.name = "mock"
        collector._sources = [mock_source]

        df = collector.get_stock_news("600519", limit=10)
        assert len(df) == 1
        mock_source.get_stock_news.assert_called_once_with("600519", 10)

    def test_get_stock_news_fallback_on_not_implemented(self):
        from data_engine.collector import DataCollector

        collector = DataCollector.__new__(DataCollector)
        source1 = MagicMock()
        source1.get_stock_news.side_effect = NotImplementedError
        source1.name = "source1"
        source2 = MagicMock()
        source2.get_stock_news.return_value = pd.DataFrame({"title": ["from source2"]})
        source2.name = "source2"
        collector._sources = [source1, source2]

        df = collector.get_stock_news("600519")
        assert len(df) == 1

    def test_get_stock_news_all_fail_returns_empty(self):
        from data_engine.collector import DataCollector

        collector = DataCollector.__new__(DataCollector)
        source1 = MagicMock()
        source1.get_stock_news.side_effect = Exception("fail")
        source1.name = "source1"
        collector._sources = [source1]

        df = collector.get_stock_news("600519")
        assert df.empty


class TestDataEngineNews:
    """DataEngine 门面新闻方法测试"""

    def test_get_news_delegates_to_collector(self):
        from data_engine.engine import DataEngine

        engine = DataEngine.__new__(DataEngine)
        engine._collector = MagicMock()
        engine._collector.get_stock_news.return_value = pd.DataFrame({"title": ["test"]})

        df = engine.get_news("600519", limit=20)
        assert len(df) == 1
        engine._collector.get_stock_news.assert_called_once_with("600519", 20)

    def test_get_announcements_delegates_to_collector(self):
        from data_engine.engine import DataEngine

        engine = DataEngine.__new__(DataEngine)
        engine._collector = MagicMock()
        engine._collector.get_announcements.return_value = pd.DataFrame({"title": ["公告"]})

        df = engine.get_announcements("600519", limit=10)
        assert len(df) == 1
        engine._collector.get_announcements.assert_called_once_with("600519", 10)
