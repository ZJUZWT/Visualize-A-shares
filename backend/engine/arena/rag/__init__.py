# engine/rag/__init__.py
"""RAG 模块 — 历史分析报告向量检索"""

from .store import RAGStore
from .schemas import ReportRecord

_rag_store: RAGStore | None = None


def get_rag_store() -> RAGStore:
    """获取 RAGStore 全局单例"""
    global _rag_store
    if _rag_store is None:
        from config import settings
        _rag_store = RAGStore(persist_dir=settings.rag.persist_dir)
    return _rag_store


__all__ = ["RAGStore", "ReportRecord", "get_rag_store"]
