# engine/tests/test_llm_capability.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 辅助 ──────────────────────────────────────────────────
def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── enabled=False 降级测试 ────────────────────────────────
def test_disabled_complete():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    assert cap.enabled is False
    result = run(cap.complete("hello"))
    assert result == ""


def test_disabled_classify():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    result = run(cap.classify("文本", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"
    assert result["score"] == 0.0
    assert result["reason"] == "llm_disabled"


def test_disabled_extract():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    result = run(cap.extract("文本", {"key": "value"}))
    assert result == {}


# ── enabled=True + mock provider ─────────────────────────
def test_complete_calls_provider():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value="LLM回复")
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.complete("test prompt", system="sys"))
    assert result == "LLM回复"
    mock_provider.chat.assert_called_once()


def test_classify_parses_json():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label": "positive", "score": 0.9, "reason": "利好"}'
    )
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.classify("大涨", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"
    assert result["score"] == 0.9
    assert result["reason"] == "利好"


def test_classify_parse_error_fallback():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value="not json at all")
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.classify("文本", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"
    assert result["reason"] == "parse_error"


def test_classify_invalid_label_fallback():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label": "unknown_label", "score": 0.5, "reason": "test"}'
    )
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.classify("文本", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"  # fallback to categories[0]


def test_extract_parses_json():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"impact": "positive", "magnitude": "high", "reasoning": "利好", "affected_factors": ["盈利"]}'
    )
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.extract("事件", {"impact": "str", "magnitude": "str"}))
    assert result["impact"] == "positive"
    assert result["magnitude"] == "high"


def test_classify_cache_hit_skips_provider():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label": "positive", "score": 0.8, "reason": "ok"}'
    )
    mock_store = MagicMock()
    # 第一次 miss，第二次 hit
    cached_json = '{"label": "negative", "score": 0.6, "reason": "cached"}'
    mock_store.get_llm_cache = MagicMock(side_effect=[None, cached_json])
    mock_store.set_llm_cache = MagicMock()

    cap = LLMCapability(provider=mock_provider, cache_store=mock_store)
    run(cap.classify("文本", ["positive", "negative", "neutral"]))
    run(cap.classify("文本", ["positive", "negative", "neutral"]))

    # provider 只调了一次（第二次命中缓存）
    assert mock_provider.chat.call_count == 1
