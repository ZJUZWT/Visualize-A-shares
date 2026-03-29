# engine/tests/test_info_refactor.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
import pandas as pd


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_sentiment_analyzer_accepts_llm_capability():
    """SentimentAnalyzer 接受 LLMCapability，不接受 BaseLLMProvider"""
    from llm.capability import LLMCapability
    from engine.info.sentiment import SentimentAnalyzer
    cap = LLMCapability()  # disabled
    sa = SentimentAnalyzer(llm_capability=cap)
    # 规则模式仍工作
    result = run(sa.analyze("增持！业绩大增"))
    assert result.sentiment in ("positive", "negative", "neutral")


def test_sentiment_analyzer_uses_classify():
    """LLM 模式下调用 llm_capability.classify()"""
    from llm.capability import LLMCapability
    from engine.info.sentiment import SentimentAnalyzer
    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = True
    mock_cap.classify = AsyncMock(return_value={"label": "positive", "score": 0.9, "reason": "利好"})
    sa = SentimentAnalyzer(llm_capability=mock_cap)
    result = run(sa.analyze("大涨利好", "股价创新高"))
    assert result.sentiment == "positive"
    assert result.score == 0.9
    mock_cap.classify.assert_called_once()


def test_event_assessor_accepts_llm_capability():
    """EventAssessor 接受 LLMCapability"""
    from llm.capability import LLMCapability
    from engine.info.event_assessor import EventAssessor
    cap = LLMCapability()  # disabled
    ea = EventAssessor(llm_capability=cap)
    result = run(ea.assess("600519", "大幅增持"))
    assert result.impact in ("positive", "negative", "neutral")
    assert result.reasoning == "LLM 未配置，无法评估"


def test_event_assessor_uses_extract():
    """LLM 模式下调用 llm_capability.extract()"""
    from llm.capability import LLMCapability
    from engine.info.event_assessor import EventAssessor
    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = True
    mock_cap.extract = AsyncMock(return_value={
        "impact": "positive", "magnitude": "high",
        "reasoning": "重大利好", "affected_factors": ["盈利预期"],
    })
    ea = EventAssessor(llm_capability=mock_cap)
    result = run(ea.assess("600519", "大幅增持"))
    assert result.impact == "positive"
    assert result.magnitude == "high"
    mock_cap.extract.assert_called_once()


def test_info_engine_init_accepts_llm_capability():
    """InfoEngine.__init__ 接受 llm_capability 参数"""
    from llm.capability import LLMCapability
    from engine.info.engine import InfoEngine
    from unittest.mock import MagicMock
    mock_de = MagicMock()
    mock_de.store = MagicMock()
    cap = LLMCapability()
    engine = InfoEngine(data_engine=mock_de, llm_capability=cap)
    assert engine is not None


def test_info_engine_health_check_uses_enabled():
    """health_check 使用 llm_capability.enabled 判断模式"""
    from llm.capability import LLMCapability
    from engine.info.engine import InfoEngine
    from unittest.mock import MagicMock
    mock_de = MagicMock()
    mock_de.store = MagicMock()
    # disabled
    engine = InfoEngine(data_engine=mock_de, llm_capability=LLMCapability())
    h = engine.health_check()
    assert h["llm_available"] is False
    assert h["sentiment_mode"] == "rules"


def test_info_engine_get_news_fetches_source_via_to_thread(monkeypatch):
    from engine.info.engine import InfoEngine

    called = []

    async def fake_to_thread(func, *args, **kwargs):
        called.append(func.__name__)
        return func(*args, **kwargs)

    class FakeDataEngine:
        def __init__(self):
            self.store = MagicMock()

        def get_news(self, code: str, limit: int = 50):
            return pd.DataFrame(
                [
                    {
                        "title": "业绩增长",
                        "content": "利润提升",
                        "source": "unit-test",
                        "publish_time": "2026-03-27 09:30:00",
                        "url": None,
                    }
                ]
            )

    monkeypatch.setattr("engine.info.engine.asyncio.to_thread", fake_to_thread)

    engine = InfoEngine(data_engine=FakeDataEngine(), llm_capability=None)
    articles = run(engine.get_news("600519", limit=1))

    assert len(articles) == 1
    assert called == ["get_news"]


def test_info_engine_get_announcements_fetches_source_via_to_thread(monkeypatch):
    from engine.info.engine import InfoEngine

    called = []

    async def fake_to_thread(func, *args, **kwargs):
        called.append(func.__name__)
        return func(*args, **kwargs)

    class FakeDataEngine:
        def __init__(self):
            self.store = MagicMock()

        def get_announcements(self, code: str, limit: int = 20):
            return pd.DataFrame(
                [
                    {
                        "title": "年度报告",
                        "type": "report",
                        "date": "2026-03-27",
                        "url": None,
                    }
                ]
            )

    monkeypatch.setattr("engine.info.engine.asyncio.to_thread", fake_to_thread)

    engine = InfoEngine(data_engine=FakeDataEngine(), llm_capability=None)
    announcements = run(engine.get_announcements("600519", limit=1))

    assert len(announcements) == 1
    assert called == ["get_announcements"]
