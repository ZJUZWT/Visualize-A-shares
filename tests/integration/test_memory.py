"""ChromaDB Agent Memory 隔离测试"""
import pytest
from pathlib import Path


@pytest.fixture
def temp_chromadb(tmp_path):
    """使用临时目录的 ChromaDB"""
    from engine.arena.memory import AgentMemory
    return AgentMemory(persist_dir=str(tmp_path / "chromadb"))


def test_memory_store_and_retrieve(temp_chromadb):
    mem = temp_chromadb
    mem.store(
        agent_role="fundamental",
        target="600519",
        content="贵州茅台 PE 偏高，但 ROE 持续强劲，看多",
        metadata={"signal": "bullish", "confidence": 0.75},
    )
    results = mem.recall(agent_role="fundamental", query="茅台估值", top_k=1)
    assert len(results) == 1
    assert "600519" in results[0]["metadata"]["target"]


def test_memory_isolation_between_roles(temp_chromadb):
    """不同 agent_role 的记忆互不可见"""
    mem = temp_chromadb
    mem.store("fundamental", "600519", "基本面分析内容", {"signal": "bullish"})
    mem.store("quant", "600519", "量化分析内容", {"signal": "bearish"})

    fund_results = mem.recall("fundamental", "分析", top_k=10)
    quant_results = mem.recall("quant", "分析", top_k=10)

    assert all(r["metadata"]["agent_role"] == "fundamental" for r in fund_results)
    assert all(r["metadata"]["agent_role"] == "quant" for r in quant_results)


def test_memory_empty_recall(temp_chromadb):
    results = temp_chromadb.recall("fundamental", "不存在的内容", top_k=5)
    assert results == []
