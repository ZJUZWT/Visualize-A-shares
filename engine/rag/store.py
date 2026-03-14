# engine/rag/store.py
"""RAGStore — 历史分析报告向量存储与检索（ChromaDB）"""

import chromadb
from loguru import logger

from .schemas import ReportRecord


class RAGStore:
    """历史分析报告向量存储与检索

    ChromaDB collection: "analysis_reports"
    存储: ReportRecord.summary 全文
    检索: 语义相似度（ChromaDB 内置 all-MiniLM-L6-v2 嵌入）
    与 AgentMemory 完全隔离（不同 persist_dir，不同 collection）
    """

    COLLECTION_NAME = "analysis_reports"

    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(self.COLLECTION_NAME)
        logger.info(f"RAGStore 初始化: {persist_dir}, 已有 {self._collection.count()} 条报告")

    def store(self, record: ReportRecord) -> None:
        """存储分析报告，report_id 相同时更新（upsert）"""
        metadata = {
            "code": record.code,
            "signal": record.signal or "",
            "score": record.score if record.score is not None else 0.0,
            "report_type": record.report_type,
            "created_at": record.created_at.isoformat(),
        }
        self._collection.upsert(
            documents=[record.summary],
            metadatas=[metadata],
            ids=[record.report_id],
        )

    def search(self, query: str, top_k: int = 3, code_filter: str | None = None) -> list[dict]:
        """语义检索，返回最相关的历史报告"""
        if self._collection.count() == 0:
            return []
        n = min(top_k, self._collection.count())
        where = {"code": code_filter} if code_filter else None
        results = self._collection.query(
            query_texts=[query],
            n_results=n,
            where=where,
        )
        entries = []
        for i in range(len(results["ids"][0])):
            entry = {"summary": results["documents"][0][i]}
            entry.update(results["metadatas"][0][i])
            entries.append(entry)
        return entries

    def count(self) -> int:
        """返回已存储的报告数量"""
        return self._collection.count()
