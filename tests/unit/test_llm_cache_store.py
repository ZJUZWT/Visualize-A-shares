# engine/tests/test_llm_cache_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import pytest
import duckdb
from unittest.mock import patch
from engine.data.store import DuckDBStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.duckdb"
    s = DuckDBStore(db_path=db_path)
    yield s
    s.close()


def test_llm_cache_miss(store):
    """未命中时返回 None"""
    result = store.get_llm_cache("nonexistent_key")
    assert result is None


def test_llm_cache_set_get(store):
    """写入后能读出"""
    store.set_llm_cache("abc123", "hash_abc", '{"label":"positive"}', model="gpt-4o-mini")
    result = store.get_llm_cache("abc123")
    assert result == '{"label":"positive"}'


def test_llm_cache_replace(store):
    """相同 key 覆盖写入"""
    store.set_llm_cache("key1", "h1", '{"a":1}')
    store.set_llm_cache("key1", "h1", '{"a":2}')
    assert store.get_llm_cache("key1") == '{"a":2}'


def test_chat_history_append_get(store):
    """追加消息后能按 session 读出"""
    store.append_chat_history("sess1", "user", "你好")
    store.append_chat_history("sess1", "assistant", "你好！")
    history = store.get_chat_history("sess1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "你好"
    assert history[1]["role"] == "assistant"


def test_chat_history_session_isolation(store):
    """不同 session 互不干扰"""
    store.append_chat_history("sessA", "user", "A消息")
    store.append_chat_history("sessB", "user", "B消息")
    assert len(store.get_chat_history("sessA")) == 1
    assert len(store.get_chat_history("sessB")) == 1


def test_chat_history_limit(store):
    """limit 参数有效"""
    for i in range(5):
        store.append_chat_history("sess2", "user", f"msg{i}")
    history = store.get_chat_history("sess2", limit=3)
    assert len(history) == 3
