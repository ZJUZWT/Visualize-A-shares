# engine/tests/test_rag_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from datetime import datetime, timezone
from unittest.mock import patch


@pytest.fixture
def rag_store(tmp_path):
    rag_dir = str(tmp_path / "chromadb_rag")
    from rag.store import RAGStore
    store = RAGStore(persist_dir=rag_dir)
    yield store


def test_rag_store_empty_search(rag_store):
    """空集合检索返回空列表"""
    results = rag_store.search("600519")
    assert results == []


def test_rag_store_count_zero(rag_store):
    """初始化后 count=0"""
    assert rag_store.count() == 0


def test_rag_store_store_and_search(rag_store):
    """存储后能检索到"""
    from rag.schemas import ReportRecord
    record = ReportRecord(
        report_id="600519_20260314",
        code="600519",
        summary="茅台基本面分析：白酒龙头，护城河深厚，长期看多。",
        signal="bullish",
        score=0.75,
        report_type="agent_analysis",
        created_at=datetime.now(tz=timezone.utc),
    )
    rag_store.store(record)
    assert rag_store.count() == 1
    results = rag_store.search("600519")
    assert len(results) == 1
    assert results[0]["code"] == "600519"
    assert results[0]["signal"] == "bullish"


def test_rag_store_upsert(rag_store):
    """相同 report_id 覆盖写入，不重复"""
    from rag.schemas import ReportRecord
    record = ReportRecord(
        report_id="id_001", code="000001", summary="旧摘要",
        signal="neutral", score=None, report_type="agent_analysis",
        created_at=datetime.now(tz=timezone.utc),
    )
    rag_store.store(record)
    record2 = record.model_copy(update={"summary": "新摘要", "signal": "bearish"})
    rag_store.store(record2)
    assert rag_store.count() == 1
    results = rag_store.search("000001")
    assert results[0]["summary"] == "新摘要"


def test_rag_store_code_filter(rag_store):
    """code_filter 只返回指定股票"""
    from rag.schemas import ReportRecord
    for code in ["600519", "000001"]:
        rag_store.store(ReportRecord(
            report_id=f"{code}_test", code=code,
            summary=f"{code} 分析摘要",
            signal="neutral", score=None, report_type="agent_analysis",
            created_at=datetime.now(tz=timezone.utc),
        ))
    results = rag_store.search("茅台", code_filter="600519")
    assert all(r["code"] == "600519" for r in results)


def test_get_rag_store_singleton(tmp_path):
    """get_rag_store() 返回单例"""
    import rag as rag_module
    rag_module._rag_store = None  # 重置单例
    rag_dir = str(tmp_path / "chromadb_rag2")
    with patch("config.settings") as mock_settings:
        mock_settings.rag.persist_dir = rag_dir
        from rag import get_rag_store
        s1 = get_rag_store()
        s2 = get_rag_store()
        assert s1 is s2
    rag_module._rag_store = None  # 清理
