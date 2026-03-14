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

    def __init__(self, data_engine, llm_capability=None):
        self._data = data_engine
        self._sentiment = SentimentAnalyzer(llm_capability=llm_capability)
        self._assessor = EventAssessor(llm_capability=llm_capability)
        self._store = data_engine.store
        self._config = None

    # ── 新闻 ──

    async def get_news(self, code: str, limit: int = 50) -> list[NewsArticle]:
        """获取个股新闻 + 情感分析"""
        cached = self._get_cached_news(code, limit)
        if cached:
            return cached

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
        cached = self._get_cached_event_impact(code, event_desc)
        if cached:
            return cached

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
        self._cache_event_impact(code, result)
        return result

    # ── 健康检查 ──

    def health_check(self) -> dict:
        llm_available = (
            self._sentiment._llm is not None
            and self._sentiment._llm.enabled
        )
        return {
            "status": "ok",
            "sentiment_mode": "llm" if llm_available else "rules",
            "llm_available": llm_available,
        }

    # ── 缓存操作（私有方法）──

    def _get_cached_news(self, code: str, limit: int) -> list[NewsArticle] | None:
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
