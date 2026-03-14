# InfoEngine 消息面引擎 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the InfoEngine (消息面引擎) — news/announcement data fetching via DataEngine + sentiment analysis + event impact assessment, completing Phase 3 of the multi-engine roadmap.

**Architecture:** DataEngine's AKShare source layer is extended with news/announcement fetching methods. A new `info_engine/` module consumes raw data from DataEngine, applies sentiment analysis (LLM-first with rule-based fallback), caches results in DuckDB `info.*` schema, and exposes REST API + MCP tools. The Agent layer's `DataFetcher.get_info_data()` stub is replaced with real InfoEngine calls.

**Tech Stack:** Python 3.12, FastAPI, AKShare, DuckDB, Pydantic, pytest, loguru. Optional: LLM provider (OpenAI-compatible or Anthropic) for sentiment analysis.

**Spec:** `docs/superpowers/specs/2026-03-14-info-engine-design.md`

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `engine/info_engine/__init__.py` | `get_info_engine()` singleton factory |
| `engine/info_engine/schemas.py` | `NewsArticle`, `Announcement`, `SentimentResult`, `EventImpact` Pydantic models |
| `engine/info_engine/sentiment.py` | `SentimentAnalyzer` — LLM-first, rule-based fallback |
| `engine/info_engine/event_assessor.py` | `EventAssessor` — LLM-driven event impact assessment |
| `engine/info_engine/engine.py` | `InfoEngine` facade — orchestrates fetching + analysis + caching |
| `engine/info_engine/routes.py` | REST API `/api/v1/info/*` |
| `tests/test_info_schemas.py` | Schema validation tests |
| `tests/test_sentiment.py` | Sentiment analysis tests (rules + mock LLM) |
| `tests/test_event_assessor.py` | Event assessor tests |
| `tests/test_info_engine.py` | InfoEngine integration tests |
| `tests/test_info_api.py` | Route registration + API tests |

### Modified files
| File | Change |
|------|--------|
| `engine/data_engine/sources/base.py` | Add `get_stock_news()`, `get_announcements()` default methods |
| `engine/data_engine/sources/akshare_source.py` | Implement news/announcement fetching via AKShare |
| `engine/data_engine/collector.py` | Add `get_stock_news()`, `get_announcements()` with fallback |
| `engine/data_engine/engine.py` | Add `get_news()`, `get_announcements()` facade methods |
| `engine/data_engine/store.py` | Add `info` schema + 3 tables initialization |
| `engine/config.py` | Add `InfoConfig` to `AppConfig` |
| `engine/main.py` | Register `info_router`, add startup log, add endpoints |
| `engine/agent/data_fetcher.py` | Replace `get_info_data()` stub with real InfoEngine calls |
| `engine/mcpserver/tools.py` | Add 3 InfoEngine tool implementations |
| `engine/mcpserver/server.py` | Register 3 new MCP tools (15 → 18) |

---

## Chunk 1: DataEngine Extension + InfoEngine Schemas

### Task 1: InfoEngine Schemas

**Files:**
- Create: `engine/info_engine/__init__.py` (empty placeholder)
- Create: `engine/info_engine/schemas.py`
- Test: `tests/test_info_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_info_schemas.py
"""InfoEngine schema 验证测试"""
import pytest
from info_engine.schemas import NewsArticle, Announcement, SentimentResult, EventImpact


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
```

- [ ] **Step 2: Create placeholder `__init__.py` and run test to verify it fails**

```python
# engine/info_engine/__init__.py
"""信息引擎模块 — 新闻/公告/情感分析/事件评估"""
```

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'info_engine.schemas'`

- [ ] **Step 3: Implement schemas**

```python
# engine/info_engine/schemas.py
"""InfoEngine 数据模型"""

from typing import Literal
from pydantic import BaseModel


class NewsArticle(BaseModel):
    """新闻文章 — 带可选情感标注"""
    title: str
    content: str | None = None
    source: str
    publish_time: str
    url: str | None = None
    sentiment: Literal["positive", "negative", "neutral"] | None = None
    sentiment_score: float | None = None  # -1.0 ~ 1.0


class Announcement(BaseModel):
    """公司公告 — 带可选情感标注"""
    title: str
    type: str
    date: str
    url: str | None = None
    sentiment: Literal["positive", "negative", "neutral"] | None = None


class SentimentResult(BaseModel):
    """情感分析结果"""
    sentiment: Literal["positive", "negative", "neutral"]
    score: float  # -1.0 ~ 1.0
    reason: str | None = None


class EventImpact(BaseModel):
    """事件影响评估结果"""
    event_desc: str
    impact: Literal["positive", "negative", "neutral"]
    magnitude: Literal["high", "medium", "low"]
    reasoning: str
    affected_factors: list[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_schemas.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add engine/info_engine/__init__.py engine/info_engine/schemas.py tests/test_info_schemas.py
git commit -m "feat(info-engine): schemas — NewsArticle, Announcement, SentimentResult, EventImpact"
```

---

### Task 2: DataEngine Source Extension — BaseDataSource + AKShareSource

**Files:**
- Modify: `engine/data_engine/sources/base.py`
- Modify: `engine/data_engine/sources/akshare_source.py`
- Test: `tests/test_data_news.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_news.py
"""DataEngine 新闻/公告数据源测试"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


class TestBaseDataSourceDefaults:
    """BaseDataSource 默认方法应 raise NotImplementedError"""

    def test_get_stock_news_not_implemented(self):
        from data_engine.sources.base import BaseDataSource
        # BaseDataSource 是 ABC，不能直接实例化
        # 创建一个只实现必需方法的子类来测试默认方法
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_data_news.py -v`
Expected: FAIL — `AttributeError: 'MinimalSource' object has no attribute 'get_stock_news'`

- [ ] **Step 3: Implement BaseDataSource default methods**

Add to `engine/data_engine/sources/base.py` after `health_check()` method (before `UNIFIED_QUOTE_COLUMNS`):

```python
    # ─── 新闻/公告（可选实现）────────────────────────────
    def get_stock_news(self, code: str, limit: int = 50) -> pd.DataFrame:
        """获取个股新闻 — 子类可选实现"""
        raise NotImplementedError

    def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
        """获取公司公告 — 子类可选实现"""
        raise NotImplementedError
```

- [ ] **Step 4: Implement AKShareSource news/announcement methods**

Add to `engine/data_engine/sources/akshare_source.py` after `get_stock_list()`:

```python
    def get_stock_news(self, code: str, limit: int = 50) -> pd.DataFrame:
        """获取个股新闻（东方财富）
        底层接口: ak.stock_news_em(symbol=code)
        注意: AKShare API 名称可能随版本变动
        """
        try:
            df = self._ak.stock_news_em(symbol=code)
            if df is None or df.empty:
                return pd.DataFrame()

            column_map = {
                "新闻标题": "title",
                "新闻内容": "content",
                "发布时间": "publish_time",
                "文章来源": "source",
                "新闻链接": "url",
            }
            df = df.rename(columns=column_map)
            available = [c for c in ["title", "content", "publish_time", "source", "url"] if c in df.columns]
            df = df[available].head(limit)
            return df
        except Exception as e:
            logger.warning(f"[AKShare] 个股新闻获取失败 {code}: {e}")
            return pd.DataFrame()

    def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
        """获取公司公告（东方财富）
        底层接口: ak.stock_notice_report_em(symbol=code)
        注意: AKShare API 名称可能随版本变动
        """
        try:
            df = self._ak.stock_notice_report_em(symbol=code)
            if df is None or df.empty:
                return pd.DataFrame()

            column_map = {
                "公告标题": "title",
                "公告类型": "type",
                "公告日期": "date",
                "公告链接": "url",
            }
            df = df.rename(columns=column_map)
            available = [c for c in ["title", "type", "date", "url"] if c in df.columns]
            df = df[available].head(limit)
            return df
        except Exception as e:
            logger.warning(f"[AKShare] 公司公告获取失败 {code}: {e}")
            return pd.DataFrame()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_data_news.py -v`
Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/data_engine/sources/base.py engine/data_engine/sources/akshare_source.py tests/test_data_news.py
git commit -m "feat(data-engine): add news/announcement methods to BaseDataSource + AKShareSource"
```

---

### Task 3: DataCollector + DataEngine Facade Extension

**Files:**
- Modify: `engine/data_engine/collector.py`
- Modify: `engine/data_engine/engine.py`
- Test: `tests/test_data_news.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data_news.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_data_news.py::TestDataCollectorNews -v`
Expected: FAIL — `AttributeError: 'DataCollector' object has no attribute 'get_stock_news'`

- [ ] **Step 3: Implement DataCollector methods**

Add to `engine/data_engine/collector.py` after `health_check()` (before `available_sources` property):

```python
    def get_stock_news(self, code: str, limit: int = 50) -> pd.DataFrame:
        """获取个股新闻 — 逐级降级"""
        for source in self._sources:
            try:
                df = source.get_stock_news(code, limit)
                if df is not None and not df.empty:
                    logger.debug(f"✅ {code} 新闻: {source.name} ({len(df)} 条)")
                    return df
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"⚠️ {source.name} {code} 新闻获取失败: {e}")
        return pd.DataFrame()

    def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
        """获取公司公告 — 逐级降级"""
        for source in self._sources:
            try:
                df = source.get_announcements(code, limit)
                if df is not None and not df.empty:
                    logger.debug(f"✅ {code} 公告: {source.name} ({len(df)} 条)")
                    return df
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"⚠️ {source.name} {code} 公告获取失败: {e}")
        return pd.DataFrame()
```

- [ ] **Step 4: Implement DataEngine facade methods**

Add to `engine/data_engine/engine.py` after `get_financial_data()` (before `# ── 快照历史`):

```python
    # ── 新闻/公告 ──

    def get_news(self, code: str, limit: int = 50) -> pd.DataFrame:
        """获取个股新闻（原始数据，不含情感分析）"""
        return self._collector.get_stock_news(code, limit)

    def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
        """获取公司公告（原始数据）"""
        return self._collector.get_announcements(code, limit)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_data_news.py -v`
Expected: 10 tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/data_engine/collector.py engine/data_engine/engine.py tests/test_data_news.py
git commit -m "feat(data-engine): news/announcement collection with fallback in DataCollector + DataEngine"
```

---

### Task 4: DuckDB Schema + Config

**Files:**
- Modify: `engine/data_engine/store.py`
- Modify: `engine/config.py`
- Test: `tests/test_info_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_info_store.py
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
            INSERT INTO info.news_articles (code, title, source, publish_time, sentiment, sentiment_score)
            VALUES ('600519', '茅台业绩大增', '东方财富', '2026-03-14 10:00', 'positive', 0.8)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_store.py -v`
Expected: FAIL — `info` schema doesn't exist / `settings.info` doesn't exist

- [ ] **Step 3: Add `info` schema to DuckDB**

Add to `engine/data_engine/store.py` `_init_tables()` method (at the end of the method):

```python
        # ── InfoEngine schema ──
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS info")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS info.news_articles (
                id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                code            VARCHAR NOT NULL,
                title           VARCHAR NOT NULL,
                content         VARCHAR,
                source          VARCHAR,
                publish_time    VARCHAR,
                url             VARCHAR,
                sentiment       VARCHAR,
                sentiment_score DOUBLE,
                analyzed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, title)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS info.announcements (
                id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                code            VARCHAR NOT NULL,
                title           VARCHAR NOT NULL,
                type            VARCHAR,
                date            VARCHAR,
                url             VARCHAR,
                sentiment       VARCHAR,
                analyzed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, title)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS info.event_impacts (
                id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                code            VARCHAR NOT NULL,
                event_desc      VARCHAR NOT NULL,
                impact          VARCHAR,
                magnitude       VARCHAR,
                reasoning       VARCHAR,
                affected_factors VARCHAR,
                assessed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, event_desc)
            )
        """)
```

- [ ] **Step 4: Add `InfoConfig` to `config.py`**

Add to `engine/config.py` after `ChromaDBConfig`:

```python
# ─── 信息引擎配置 ─────────────────────────────────────
class InfoConfig(BaseModel):
    """信息引擎配置"""
    news_cache_hours: int = 24
    announcement_cache_hours: int = 48
    default_news_limit: int = 50
    default_announcement_limit: int = 20
    sentiment_mode: str = "auto"  # "auto" | "llm" | "rules"
```

And add `info: InfoConfig = InfoConfig()` to `AppConfig`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_store.py -v`
Expected: 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/data_engine/store.py engine/config.py tests/test_info_store.py
git commit -m "feat: DuckDB info schema (3 tables) + InfoConfig"
```

---

## Chunk 2: InfoEngine Core — Sentiment + EventAssessor + Engine Facade

### Task 5: Sentiment Analyzer

**Files:**
- Create: `engine/info_engine/sentiment.py`
- Test: `tests/test_sentiment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sentiment.py
"""情感分析测试 — 规则模式 + mock LLM 模式"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock


class TestRuleSentiment:
    """规则模式情感分析测试"""

    def test_positive_title(self):
        from info_engine.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        result = asyncio.run(analyzer.analyze("贵州茅台业绩大增超预期"))
        assert result.sentiment == "positive"
        assert result.score > 0

    def test_negative_title(self):
        from info_engine.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        result = asyncio.run(analyzer.analyze("某公司财务造假被处罚"))
        assert result.sentiment == "negative"
        assert result.score < 0

    def test_neutral_title(self):
        from info_engine.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        result = asyncio.run(analyzer.analyze("某公司召开年度股东大会"))
        assert result.sentiment == "neutral"
        assert result.score == 0.0

    def test_content_contributes_to_score(self):
        from info_engine.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer(llm_provider=None)
        # 标题中性但内容利好
        result = asyncio.run(analyzer.analyze("公司发布年报", "净利润同比增长50%，业绩大增"))
        assert result.score > 0


class TestLLMSentiment:
    """LLM 模式情感分析测试（mock）"""

    def test_llm_sentiment_positive(self):
        from info_engine.sentiment import SentimentAnalyzer

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
        from info_engine.sentiment import SentimentAnalyzer

        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "这不是一个有效的JSON"

        analyzer = SentimentAnalyzer(llm_provider=mock_llm)
        # 应退化为规则模式而非抛异常
        result = asyncio.run(analyzer.analyze("某公司被处罚"))
        assert result.sentiment in ("positive", "negative", "neutral")

    def test_llm_fallback_on_exception(self):
        from info_engine.sentiment import SentimentAnalyzer

        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("LLM API timeout")

        analyzer = SentimentAnalyzer(llm_provider=mock_llm)
        result = asyncio.run(analyzer.analyze("某公司被处罚"))
        assert result.sentiment in ("positive", "negative", "neutral")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_sentiment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'info_engine.sentiment'`

- [ ] **Step 3: Implement sentiment analyzer**

```python
# engine/info_engine/sentiment.py
"""情感分析器 — LLM 优先，规则退化"""

import json

from loguru import logger

from .schemas import SentimentResult

# ── 关键词词典 ──────────────────────────────────────────
POSITIVE_KEYWORDS = [
    "大增", "超预期", "增持", "回购", "中标", "突破", "创新高",
    "业绩预增", "扭亏", "净利润增长", "营收增长", "签约", "合作",
    "获批", "战略投资", "分红", "派息", "利好", "上调",
    "获得", "中标", "发明专利", "技术突破", "产能扩张",
    "并购", "重组成功", "解禁利好", "股权激励", "员工持股",
    "翻倍", "暴涨", "涨停", "新高", "强势", "爆发",
    "盈利", "景气", "高增长", "加速", "提升", "改善",
    "龙头", "行业第一", "市占率提升", "订单", "产销两旺",
]

NEGATIVE_KEYWORDS = [
    "减持", "亏损", "处罚", "退市", "暴雷", "违规", "下修",
    "破位", "跌停", "预亏", "业绩下滑", "净利润下降", "营收下降",
    "被调查", "立案", "警示", "ST", "造假", "诉讼", "仲裁",
    "解禁", "质押", "爆仓", "清仓", "减值", "商誉减值",
    "下调评级", "利空", "风险", "暴跌", "腰斩", "崩盘",
    "停产", "召回", "事故", "泄漏", "污染", "罚款",
    "终止", "失败", "流产", "取消", "延期", "推迟",
    "离职", "高管变动", "内斗", "举报", "实名举报",
]


class SentimentAnalyzer:
    """情感分析器 — LLM 优先，规则退化

    Args:
        llm_provider: BaseLLMProvider 实例。None 时使用纯规则模式。
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    async def analyze(self, title: str, content: str | None = None) -> SentimentResult:
        """分析新闻/公告的情感倾向"""
        if self._llm:
            try:
                return await self._analyze_llm(title, content)
            except Exception as e:
                logger.warning(f"LLM 情感分析失败，退化为规则: {e}")
        return self._analyze_rules(title, content)

    def _analyze_rules(self, title: str, content: str | None) -> SentimentResult:
        """规则模式 — 关键词词典匹配"""
        text = title + ((" " + content) if content else "")

        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)

        total = pos_count + neg_count
        if total == 0:
            return SentimentResult(sentiment="neutral", score=0.0)

        score = (pos_count - neg_count) / total  # -1.0 ~ 1.0
        if score > 0.1:
            sentiment = "positive"
        elif score < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        return SentimentResult(sentiment=sentiment, score=round(score, 2))

    async def _analyze_llm(self, title: str, content: str | None) -> SentimentResult:
        """LLM 模式 — 无状态单次调用"""
        from llm.providers import ChatMessage

        text = f"标题: {title}"
        if content:
            text += f"\n内容: {content[:500]}"

        messages = [
            ChatMessage("system",
                "你是一个金融新闻情感分析专家。分析以下新闻的情感倾向。"
                "仅返回 JSON（不要 markdown 代码块），格式："
                '{"sentiment": "positive|negative|neutral", "score": -1.0到1.0的浮点数, "reason": "简短原因"}'
            ),
            ChatMessage("user", text),
        ]

        raw = await self._llm.chat(messages)
        data = json.loads(raw.strip())
        return SentimentResult(
            sentiment=data["sentiment"],
            score=float(data["score"]),
            reason=data.get("reason"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_sentiment.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add engine/info_engine/sentiment.py tests/test_sentiment.py
git commit -m "feat(info-engine): SentimentAnalyzer with LLM-first + rule-based fallback"
```

---

### Task 6: Event Assessor

**Files:**
- Create: `engine/info_engine/event_assessor.py`
- Test: `tests/test_event_assessor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_event_assessor.py
"""事件影响评估测试"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock


class TestEventAssessorNoLLM:
    """无 LLM 时的降级行为"""

    def test_no_llm_returns_neutral(self):
        from info_engine.event_assessor import EventAssessor
        assessor = EventAssessor(llm_provider=None)
        result = asyncio.run(assessor.assess("600519", "控股股东增持5%"))
        assert result.impact == "neutral"
        assert result.magnitude == "low"
        assert "未配置" in result.reasoning

    def test_no_llm_with_context(self):
        from info_engine.event_assessor import EventAssessor
        assessor = EventAssessor(llm_provider=None)
        result = asyncio.run(assessor.assess(
            "600519", "公司发布业绩预增公告",
            stock_context={"industry": "白酒", "total_mv": 20000}
        ))
        assert result.impact == "neutral"


class TestEventAssessorWithLLM:
    """LLM 模式测试（mock）"""

    def test_llm_assess_positive(self):
        from info_engine.event_assessor import EventAssessor

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
        from info_engine.event_assessor import EventAssessor

        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("timeout")

        assessor = EventAssessor(llm_provider=mock_llm)
        result = asyncio.run(assessor.assess("600519", "某事件"))
        assert result.impact == "neutral"
        assert result.magnitude == "low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_event_assessor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement event assessor**

```python
# engine/info_engine/event_assessor.py
"""事件影响评估器 — LLM 驱动"""

import json

from loguru import logger

from .schemas import EventImpact


class EventAssessor:
    """事件影响评估 — LLM 驱动，无 LLM 时退化为中性

    Args:
        llm_provider: BaseLLMProvider 实例。None 时返回 neutral。
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    async def assess(
        self,
        code: str,
        event_desc: str,
        stock_context: dict | None = None,
    ) -> EventImpact:
        """评估事件对个股的影响"""
        if not self._llm:
            return EventImpact(
                event_desc=event_desc,
                impact="neutral",
                magnitude="low",
                reasoning="LLM 未配置，无法评估事件影响",
                affected_factors=[],
            )

        try:
            return await self._assess_llm(code, event_desc, stock_context)
        except Exception as e:
            logger.warning(f"LLM 事件评估失败 [{code}]: {e}")
            return EventImpact(
                event_desc=event_desc,
                impact="neutral",
                magnitude="low",
                reasoning=f"LLM 评估失败: {e}",
                affected_factors=[],
            )

    async def _assess_llm(
        self,
        code: str,
        event_desc: str,
        stock_context: dict | None,
    ) -> EventImpact:
        """LLM 驱动的事件评估"""
        from llm.providers import ChatMessage

        context_text = ""
        if stock_context:
            context_text = f"\n\n个股背景: {json.dumps(stock_context, ensure_ascii=False)}"

        messages = [
            ChatMessage("system",
                "你是一个金融事件影响评估专家。分析以下事件对指定股票的潜在影响。"
                "仅返回 JSON（不要 markdown 代码块），格式："
                '{"impact": "positive|negative|neutral", '
                '"magnitude": "high|medium|low", '
                '"reasoning": "推理过程", '
                '"affected_factors": ["因素1", "因素2"]}'
            ),
            ChatMessage("user",
                f"股票代码: {code}\n事件: {event_desc}{context_text}"
            ),
        ]

        raw = await self._llm.chat(messages)
        data = json.loads(raw.strip())
        return EventImpact(
            event_desc=event_desc,
            impact=data["impact"],
            magnitude=data["magnitude"],
            reasoning=data["reasoning"],
            affected_factors=data.get("affected_factors", []),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_event_assessor.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add engine/info_engine/event_assessor.py tests/test_event_assessor.py
git commit -m "feat(info-engine): EventAssessor with LLM-driven assessment + fallback"
```

---

### Task 7: InfoEngine Facade

**Files:**
- Create: `engine/info_engine/engine.py`
- Update: `engine/info_engine/__init__.py`
- Test: `tests/test_info_engine.py`

- [ ] **Step 1: Write the failing test**

```python
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
        from info_engine.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        news = asyncio.run(ie.get_news("600519", limit=10))
        assert len(news) == 2
        assert news[0].title == "茅台业绩大增"
        assert news[0].sentiment is not None  # 规则模式应填充

    def test_returns_empty_on_no_data(self, mock_data_engine):
        mock_data_engine.get_news.return_value = pd.DataFrame()
        from info_engine.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        news = asyncio.run(ie.get_news("999999", limit=10))
        assert news == []


class TestInfoEngineGetAnnouncements:
    def test_returns_announcements_with_sentiment(self, mock_data_engine):
        from info_engine.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        anns = asyncio.run(ie.get_announcements("600519", limit=10))
        assert len(anns) == 1
        assert anns[0].type == "股份变动"


class TestInfoEngineAssessEvent:
    def test_assess_without_llm(self, mock_data_engine):
        from info_engine.engine import InfoEngine
        ie = InfoEngine(data_engine=mock_data_engine, llm_provider=None)
        impact = asyncio.run(ie.assess_event_impact("600519", "控股股东增持"))
        assert impact.impact == "neutral"
        assert "未配置" in impact.reasoning


class TestInfoEngineFactory:
    def test_get_info_engine_returns_singleton(self):
        import info_engine
        info_engine._info_engine = None  # reset

        with patch("info_engine.get_data_engine") as mock_gde:
            mock_gde.return_value = MagicMock()
            mock_gde.return_value.store = MagicMock()
            ie1 = info_engine.get_info_engine()
            ie2 = info_engine.get_info_engine()
            assert ie1 is ie2

        info_engine._info_engine = None  # cleanup
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'info_engine.engine'`

- [ ] **Step 3: Implement InfoEngine facade**

```python
# engine/info_engine/engine.py
"""InfoEngine — 消息面引擎门面类

统一管理新闻采集、情感分析、事件评估、DuckDB 缓存。
数据源通过 DataEngine，分析结果缓存在 DataEngine 的 DuckDB info.* schema。
"""

import datetime
import json

import pandas as pd
from loguru import logger

from .schemas import NewsArticle, Announcement, EventImpact
from .sentiment import SentimentAnalyzer
from .event_assessor import EventAssessor


class InfoEngine:
    """消息面引擎 — 新闻/公告/事件评估的门面"""

    def __init__(self, data_engine, llm_provider=None):
        """
        Args:
            data_engine: DataEngine 实例
            llm_provider: BaseLLMProvider 实例（可选，None 时退化为规则模式）
        """
        from config import settings

        self._data = data_engine
        self._sentiment = SentimentAnalyzer(llm_provider)
        self._assessor = EventAssessor(llm_provider)
        self._store = data_engine.store
        self._config = settings.info
        self._llm = llm_provider

    # ── 新闻 ──

    async def get_news(self, code: str, limit: int = 50) -> list[NewsArticle]:
        """获取个股新闻 + 情感分析

        1. 检查 DuckDB 缓存
        2. 缓存未命中 → DataEngine 拉取
        3. 情感分析
        4. 写入缓存
        """
        # 尝试缓存
        cached = self._get_cached_news(code, limit)
        if cached:
            return cached

        # 从 DataEngine 拉取原始数据
        raw_df = self._data.get_news(code, limit)
        if raw_df.empty:
            return []

        articles = []
        for _, row in raw_df.iterrows():
            title = str(row.get("title", ""))
            content = str(row.get("content", "")) if pd.notna(row.get("content")) else None

            sentiment_result = await self._sentiment.analyze(title, content)

            article = NewsArticle(
                title=title,
                content=content,
                source=str(row.get("source", "")),
                publish_time=str(row.get("publish_time", "")),
                url=str(row.get("url", "")) if pd.notna(row.get("url")) else None,
                sentiment=sentiment_result.sentiment,
                sentiment_score=sentiment_result.score,
            )
            articles.append(article)

        # 写入缓存
        self._cache_news(code, articles)
        return articles

    # ── 公告 ──

    async def get_announcements(self, code: str, limit: int = 20) -> list[Announcement]:
        """获取公司公告 + 情感分析"""
        cached = self._get_cached_announcements(code, limit)
        if cached:
            return cached

        raw_df = self._data.get_announcements(code, limit)
        if raw_df.empty:
            return []

        announcements = []
        for _, row in raw_df.iterrows():
            title = str(row.get("title", ""))

            sentiment_result = await self._sentiment.analyze(title)

            ann = Announcement(
                title=title,
                type=str(row.get("type", "")),
                date=str(row.get("date", "")),
                url=str(row.get("url", "")) if pd.notna(row.get("url")) else None,
                sentiment=sentiment_result.sentiment,
            )
            announcements.append(ann)

        self._cache_announcements(code, announcements)
        return announcements

    # ── 事件评估 ──

    async def assess_event_impact(self, code: str, event_desc: str) -> EventImpact:
        """评估事件对个股的影响"""
        # 检查缓存
        cached = self._get_cached_event_impact(code, event_desc)
        if cached:
            return cached

        # 获取个股上下文
        stock_context = None
        try:
            profile = self._data.get_profile(code)
            if profile:
                stock_context = {
                    k: v for k, v in profile.items()
                    if k in ("name", "industry", "total_mv", "circ_mv")
                }
        except Exception:
            pass

        result = await self._assessor.assess(code, event_desc, stock_context)

        # 缓存结果
        self._cache_event_impact(code, result)
        return result

    # ── 健康检查 ──

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "sentiment_mode": "llm" if self._llm else "rules",
            "llm_available": self._llm is not None,
        }

    # ── 缓存操作（私有方法）──

    def _get_cached_news(self, code: str, limit: int) -> list[NewsArticle] | None:
        """检查新闻缓存（cache_hours 内有效）"""
        try:
            cutoff = (
                datetime.datetime.now() - datetime.timedelta(hours=self._config.news_cache_hours)
            ).strftime("%Y-%m-%d %H:%M:%S")
            rows = self._store._conn.execute(
                "SELECT title, content, source, publish_time, url, sentiment, sentiment_score "
                "FROM info.news_articles WHERE code = ? AND analyzed_at > ? LIMIT ?",
                [code, cutoff, limit],
            ).fetchall()
            if not rows:
                return None
            return [
                NewsArticle(
                    title=r[0], content=r[1], source=r[2] or "",
                    publish_time=r[3] or "", url=r[4],
                    sentiment=r[5], sentiment_score=r[6],
                )
                for r in rows
            ]
        except Exception as e:
            logger.debug(f"新闻缓存读取失败: {e}")
            return None

    def _cache_news(self, code: str, articles: list[NewsArticle]):
        """写入新闻缓存"""
        for a in articles:
            try:
                self._store._conn.execute(
                    "INSERT OR IGNORE INTO info.news_articles "
                    "(code, title, content, source, publish_time, url, sentiment, sentiment_score) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [code, a.title, a.content, a.source, a.publish_time,
                     a.url, a.sentiment, a.sentiment_score],
                )
            except Exception as e:
                logger.debug(f"新闻缓存写入跳过: {e}")

    def _get_cached_announcements(self, code: str, limit: int) -> list[Announcement] | None:
        try:
            cutoff = (
                datetime.datetime.now() - datetime.timedelta(hours=self._config.announcement_cache_hours)
            ).strftime("%Y-%m-%d %H:%M:%S")
            rows = self._store._conn.execute(
                "SELECT title, type, date, url, sentiment "
                "FROM info.announcements WHERE code = ? AND analyzed_at > ? LIMIT ?",
                [code, cutoff, limit],
            ).fetchall()
            if not rows:
                return None
            return [
                Announcement(title=r[0], type=r[1] or "", date=r[2] or "", url=r[3], sentiment=r[4])
                for r in rows
            ]
        except Exception as e:
            logger.debug(f"公告缓存读取失败: {e}")
            return None

    def _cache_announcements(self, code: str, announcements: list[Announcement]):
        for a in announcements:
            try:
                self._store._conn.execute(
                    "INSERT OR IGNORE INTO info.announcements "
                    "(code, title, type, date, url, sentiment) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [code, a.title, a.type, a.date, a.url, a.sentiment],
                )
            except Exception as e:
                logger.debug(f"公告缓存写入跳过: {e}")

    def _get_cached_event_impact(self, code: str, event_desc: str) -> EventImpact | None:
        try:
            rows = self._store._conn.execute(
                "SELECT event_desc, impact, magnitude, reasoning, affected_factors "
                "FROM info.event_impacts WHERE code = ? AND event_desc = ?",
                [code, event_desc],
            ).fetchall()
            if not rows:
                return None
            r = rows[0]
            factors = json.loads(r[4]) if r[4] else []
            return EventImpact(
                event_desc=r[0], impact=r[1], magnitude=r[2],
                reasoning=r[3], affected_factors=factors,
            )
        except Exception as e:
            logger.debug(f"事件缓存读取失败: {e}")
            return None

    def _cache_event_impact(self, code: str, impact: EventImpact):
        try:
            self._store._conn.execute(
                "INSERT OR IGNORE INTO info.event_impacts "
                "(code, event_desc, impact, magnitude, reasoning, affected_factors) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [code, impact.event_desc, impact.impact, impact.magnitude,
                 impact.reasoning, json.dumps(impact.affected_factors, ensure_ascii=False)],
            )
        except Exception as e:
            logger.debug(f"事件缓存写入跳过: {e}")
```

- [ ] **Step 4: Update `__init__.py` with singleton factory**

```python
# engine/info_engine/__init__.py
"""信息引擎模块 — 新闻/公告/情感分析/事件评估"""

from .engine import InfoEngine

_info_engine: InfoEngine | None = None


def get_info_engine() -> InfoEngine:
    """获取信息引擎全局单例（依赖数据引擎，可选 LLM）"""
    global _info_engine
    if _info_engine is None:
        from data_engine import get_data_engine

        llm_provider = None
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            if llm_settings.api_key:
                llm_provider = LLMProviderFactory.create(llm_settings)
        except Exception:
            pass

        _info_engine = InfoEngine(
            data_engine=get_data_engine(),
            llm_provider=llm_provider,
        )
    return _info_engine


__all__ = ["InfoEngine", "get_info_engine"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_engine.py -v`
Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/info_engine/engine.py engine/info_engine/__init__.py tests/test_info_engine.py
git commit -m "feat(info-engine): InfoEngine facade with caching + get_info_engine() singleton"
```

---

## Chunk 3: REST API + Integration + MCP Tools + E2E

### Task 8: REST API Routes

**Files:**
- Create: `engine/info_engine/routes.py`
- Modify: `engine/main.py`
- Test: `tests/test_info_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_info_api.py
"""InfoEngine REST API 测试"""
import pytest


class TestInfoRoutes:
    def test_info_router_exists(self):
        from info_engine.routes import router
        assert router.prefix == "/api/v1/info"

    def test_info_router_registered_in_app(self):
        from main import app
        paths = [r.path for r in app.routes]
        assert any("/api/v1/info" in p for p in paths)

    def test_health_endpoint_exists(self):
        from info_engine.routes import router
        route_paths = [r.path for r in router.routes]
        assert "/health" in route_paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'info_engine.routes'`

- [ ] **Step 3: Implement routes**

```python
# engine/info_engine/routes.py
"""信息引擎 REST API

路由前缀: /api/v1/info/*
注: 路线图原定 /api/v1/news/*，改为 /api/v1/info/* 因为覆盖新闻+公告+事件评估
"""

import asyncio

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from pydantic import BaseModel
from loguru import logger

from info_engine import get_info_engine

router = APIRouter(prefix="/api/v1/info", tags=["info"])


@router.get("/health")
async def info_health():
    """信息引擎健康检查"""
    ie = get_info_engine()
    return ie.health_check()


@router.get("/news/{code}")
async def get_news(
    code: str = PathParam(..., pattern=r"^\d{6}$"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """获取个股新闻 + 情感分析"""
    ie = get_info_engine()
    news = await ie.get_news(code, limit)

    # 情感统计
    summary = {"positive": 0, "negative": 0, "neutral": 0}
    for n in news:
        if n.sentiment in summary:
            summary[n.sentiment] += 1

    return {
        "code": code,
        "news": [n.model_dump() for n in news],
        "sentiment_summary": summary,
    }


@router.get("/announcements/{code}")
async def get_announcements(
    code: str = PathParam(..., pattern=r"^\d{6}$"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """获取公司公告 + 情感分析"""
    ie = get_info_engine()
    announcements = await ie.get_announcements(code, limit)
    return {
        "code": code,
        "announcements": [a.model_dump() for a in announcements],
    }


class AssessRequest(BaseModel):
    code: str
    event_desc: str


@router.post("/assess")
async def assess_event(req: AssessRequest):
    """事件影响评估"""
    ie = get_info_engine()
    impact = await ie.assess_event_impact(req.code, req.event_desc)
    return impact.model_dump()
```

- [ ] **Step 4: Register router in main.py**

Add import in `engine/main.py` after the analysis_router import:
```python
from info_engine.routes import router as info_router
```

Add router registration after `app.include_router(analysis_router)`:
```python
app.include_router(info_router)
```

Add startup log line after the `量化引擎` log line:
```python
    logger.info(f"   信息引擎: 已加载 (新闻+公告+情感分析)")
```

Add to the endpoints dict in root route:
```python
            "info_health": "GET /api/v1/info/health",
            "info_news": "GET /api/v1/info/news/{code}",
            "info_announcements": "GET /api/v1/info/announcements/{code}",
            "info_assess": "POST /api/v1/info/assess",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/test_info_api.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add engine/info_engine/routes.py engine/main.py tests/test_info_api.py
git commit -m "feat(api): InfoEngine REST API /api/v1/info/* + main.py registration"
```

---

### Task 9: Agent DataFetcher + MCP Tools Integration

**Files:**
- Modify: `engine/agent/data_fetcher.py`
- Modify: `engine/mcpserver/tools.py`
- Modify: `engine/mcpserver/server.py`

- [ ] **Step 1: Replace DataFetcher stub**

Replace the `get_info_data` method in `engine/agent/data_fetcher.py`:

```python
    async def get_info_data(self, target: str) -> dict:
        """获取消息面数据（InfoEngine）"""
        try:
            from info_engine import get_info_engine
            ie = get_info_engine()
            news = await ie.get_news(target, limit=20)
            announcements = await ie.get_announcements(target, limit=10)
            return {
                "news": [n.model_dump() for n in news],
                "announcements": [a.model_dump() for a in announcements],
            }
        except Exception as e:
            logger.warning(f"获取消息面数据失败 [{target}]: {e}")
            return {"news": [], "announcements": [], "error": str(e)}
```

Also update `fetch_all()` — since `get_info_data` is now async, change the gather call:

```python
    async def fetch_all(self, target: str) -> dict[str, dict]:
        """异步获取所有引擎数据"""
        fund_data, info_data, quant_data = await asyncio.gather(
            asyncio.to_thread(self.get_stock_data, target),
            self.get_info_data(target),  # now async, no need for to_thread
            asyncio.to_thread(self.get_quant_data, target),
        )
        return {
            "fundamental": fund_data,
            "info": info_data,
            "quant": quant_data,
        }
```

- [ ] **Step 2: Add 3 InfoEngine MCP tool implementations**

Add to `engine/mcpserver/tools.py` after `get_signal_history` function:

```python
# ─── InfoEngine Tools ──────────────────────────────

def _run_async(coro):
    """安全运行 async 协程 — 处理 MCP server 已有事件循环的情况"""
    import asyncio
    try:
        asyncio.get_running_loop()
        # 已在事件循环中（MCP stdio transport），用新线程运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=60)
    except RuntimeError:
        # 无运行中的事件循环，直接 asyncio.run
        return asyncio.run(coro)


def get_news(da: "DataAccess", code: str, limit: int = 20) -> str:
    """获取个股新闻 + 情感分析"""
    try:
        from info_engine import get_info_engine
        ie = get_info_engine()
        news = _run_async(ie.get_news(code, limit))

        if not news:
            return json.dumps({"code": code, "news": [], "note": "暂无新闻数据"}, ensure_ascii=False)

        summary = {"positive": 0, "negative": 0, "neutral": 0}
        news_list = []
        for n in news:
            if n.sentiment in summary:
                summary[n.sentiment] += 1
            news_list.append(n.model_dump())

        return json.dumps({
            "code": code,
            "news": news_list,
            "sentiment_summary": summary,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"新闻获取失败: {e}"}, ensure_ascii=False)


def get_announcements(da: "DataAccess", code: str, limit: int = 10) -> str:
    """获取公司公告 + 情感分析"""
    try:
        from info_engine import get_info_engine
        ie = get_info_engine()
        anns = _run_async(ie.get_announcements(code, limit))

        if not anns:
            return json.dumps({"code": code, "announcements": [], "note": "暂无公告数据"}, ensure_ascii=False)

        return json.dumps({
            "code": code,
            "announcements": [a.model_dump() for a in anns],
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"公告获取失败: {e}"}, ensure_ascii=False)


def assess_event_impact(da: "DataAccess", code: str, event_desc: str) -> str:
    """评估事件对个股的影响"""
    try:
        from info_engine import get_info_engine
        ie = get_info_engine()
        impact = _run_async(ie.assess_event_impact(code, event_desc))
        return json.dumps(impact.model_dump(), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"事件评估失败: {e}"}, ensure_ascii=False)
```

- [ ] **Step 3: Register 3 MCP tools in server.py**

Add to `engine/mcpserver/server.py` before `# ─── Agent Tools` section:

```python
# ─── InfoEngine Tools ──────────────────────────────

@server.tool()
def get_news(code: str, limit: int = 20) -> str:
    """获取个股新闻 + 情感分析。返回新闻列表（含情感标注 positive/negative/neutral）和情感统计。code 示例: '600519'"""
    return tools.get_news(_da, code, limit)


@server.tool()
def get_announcements(code: str, limit: int = 10) -> str:
    """获取公司公告 + 情感分析。返回公告列表和情感标注。code 示例: '600519'"""
    return tools.get_announcements(_da, code, limit)


@server.tool()
def assess_event_impact(code: str, event_desc: str) -> str:
    """评估事件对个股的影响。需要描述具体事件内容。返回影响方向(positive/negative/neutral)、强度(high/medium/low)和推理过程。"""
    return tools.assess_event_impact(_da, code, event_desc)
```

Update the file header comment from `15 个 Tool` to `18 个 Tool`.

- [ ] **Step 4: Run all tests**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/ -v --tb=short`
Expected: All tests PASS (agent tests may need adjustment for async `get_info_data`)

- [ ] **Step 5: Commit**

```bash
git add engine/agent/data_fetcher.py engine/mcpserver/tools.py engine/mcpserver/server.py
git commit -m "feat: integrate InfoEngine — DataFetcher + 3 MCP tools (15→18)"
```

---

### Task 10: End-to-End Verification

**Files:** No new files — verification only

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python3 -m pytest tests/ -v --tb=short
```
Expected: All tests pass

- [ ] **Step 2: Verify import paths**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python3 -c "
from info_engine import get_info_engine, InfoEngine
from info_engine.schemas import NewsArticle, Announcement, SentimentResult, EventImpact
from info_engine.sentiment import SentimentAnalyzer, POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS
from info_engine.event_assessor import EventAssessor
from info_engine.routes import router
print('✅ All info_engine imports OK')
print(f'  Positive keywords: {len(POSITIVE_KEYWORDS)}')
print(f'  Negative keywords: {len(NEGATIVE_KEYWORDS)}')

from data_engine import get_data_engine
de = get_data_engine.__wrapped__ if hasattr(get_data_engine, '__wrapped__') else get_data_engine
print('✅ DataEngine import OK')

from config import settings
print(f'✅ InfoConfig: news_cache={settings.info.news_cache_hours}h, sentiment_mode={settings.info.sentiment_mode}')
"
```

- [ ] **Step 3: Verify MCP tool count**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python3 -c "
from mcpserver.server import server
tools_list = server.list_tools()
print(f'✅ MCP tools: {len(tools_list)} registered')
for t in tools_list:
    print(f'  - {t.name}')
assert len(tools_list) == 18, f'Expected 18 tools, got {len(tools_list)}'
"
```

- [ ] **Step 4: Verify route count**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python3 -c "
from main import app
routes = [r for r in app.routes if hasattr(r, 'path')]
print(f'✅ Routes: {len(routes)} registered')
info_routes = [r for r in routes if '/info/' in r.path]
print(f'  InfoEngine routes: {len(info_routes)}')
for r in info_routes:
    methods = ','.join(r.methods) if hasattr(r, 'methods') else '?'
    print(f'    {methods} {r.path}')
"
```

- [ ] **Step 5: Verify DuckDB schema**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python3 -c "
from data_engine.store import DuckDBStore
store = DuckDBStore()
schemas = store._conn.execute(
    \"SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'info'\"
).fetchall()
print(f'✅ info schema: {\"exists\" if schemas else \"MISSING\"} ')
tables = store._conn.execute(
    \"SELECT table_name FROM information_schema.tables WHERE table_schema = 'info'\"
).fetchall()
print(f'✅ info tables: {[t[0] for t in tables]}')
assert len(tables) == 3, f'Expected 3 tables, got {len(tables)}'
"
```
