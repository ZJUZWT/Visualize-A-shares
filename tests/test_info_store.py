"""InfoEngine DuckDB schema 测试"""
import pytest
from pathlib import Path
from data_engine.store import DuckDBStore


@pytest.fixture
def tmp_store(tmp_path):
    """使用临时路径的 DuckDBStore"""
    db_path = tmp_path / "test.duckdb"
    return DuckDBStore(db_path)


class TestInfoSchema:
    def test_info_schema_exists(self, tmp_store):
        result = tmp_store._conn.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'info'"
        ).fetchall()
        assert len(result) == 1

    def test_news_articles_table_exists(self, tmp_store):
        result = tmp_store._conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'info' AND table_name = 'news_articles'"
        ).fetchall()
        assert len(result) == 1

    def test_announcements_table_exists(self, tmp_store):
        result = tmp_store._conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'info' AND table_name = 'announcements'"
        ).fetchall()
        assert len(result) == 1

    def test_event_impacts_table_exists(self, tmp_store):
        result = tmp_store._conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'info' AND table_name = 'event_impacts'"
        ).fetchall()
        assert len(result) == 1

    def test_insert_and_query_news(self, tmp_store):
        tmp_store._conn.execute("""
            INSERT INTO info.news_articles (id, code, title, source, publish_time, sentiment, sentiment_score)
            VALUES (1, '600519', '茅台业绩大增', '东方财富', '2026-03-14 10:00', 'positive', 0.8)
        """)
        rows = tmp_store._conn.execute(
            "SELECT * FROM info.news_articles WHERE code = '600519'"
        ).fetchall()
        assert len(rows) == 1


class TestInfoConfig:
    def test_info_config_defaults(self):
        from config import settings
        assert hasattr(settings, 'info')
        assert settings.info.news_cache_hours == 24
        assert settings.info.announcement_cache_hours == 48
        assert settings.info.sentiment_mode == "auto"
