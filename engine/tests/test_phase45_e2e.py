# engine/tests/test_phase45_e2e.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import pytest
from unittest.mock import patch
from datetime import datetime, timezone


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_llm_capability_import():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    assert cap.enabled is False


def test_rag_module_import():
    from rag import RAGStore, ReportRecord, get_rag_store
    assert RAGStore is not None


def test_data_fetcher_action_dispatch_count():
    from agent.data_fetcher import ACTION_DISPATCH
    assert len(ACTION_DISPATCH) == 7


def test_info_engine_init_with_disabled_capability():
    """InfoEngine 使用 disabled LLMCapability 初始化正常"""
    from llm.capability import LLMCapability
    from info_engine.engine import InfoEngine
    from unittest.mock import MagicMock
    mock_de = MagicMock()
    mock_de.store = MagicMock()
    engine = InfoEngine(data_engine=mock_de, llm_capability=LLMCapability())
    h = engine.health_check()
    assert h["status"] == "ok"
    assert h["llm_available"] is False


def test_rag_store_full_cycle(tmp_path):
    """RAGStore 完整存取循环"""
    from rag.store import RAGStore
    from rag.schemas import ReportRecord
    store = RAGStore(persist_dir=str(tmp_path / "rag"))
    record = ReportRecord(
        report_id="test_001",
        code="600519",
        summary="综合来看，茅台当前估值合理，长期价值确定。",
        signal="bullish",
        score=0.7,
        report_type="agent_analysis",
        created_at=datetime.now(tz=timezone.utc),
    )
    store.store(record)
    results = store.search("茅台估值", code_filter="600519")
    assert len(results) >= 1
    assert results[0]["code"] == "600519"


def test_llm_cache_in_classify(tmp_path):
    """classify 相同输入第二次命中缓存，provider 只调一次"""
    from llm.capability import LLMCapability
    from unittest.mock import AsyncMock, MagicMock
    from data_engine.store import DuckDBStore

    db_path = tmp_path / "test.duckdb"
    store = DuckDBStore(db_path=db_path)

    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label":"positive","score":0.9,"reason":"利好"}'
    )
    cap = LLMCapability(provider=mock_provider, cache_store=store)

    run(cap.classify("大涨利好消息", ["positive", "negative", "neutral"]))
    run(cap.classify("大涨利好消息", ["positive", "negative", "neutral"]))

    assert mock_provider.chat.call_count == 1
    store.close()
