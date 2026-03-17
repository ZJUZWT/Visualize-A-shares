# engine/rag/store.py
"""RAGStore — 历史分析报告向量存储与检索（ChromaDB）"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import chromadb
from loguru import logger

from .schemas import ReportRecord


class RAGStore:
    """历史分析报告向量存储与检索

    ChromaDB collection: "analysis_reports"
    存储: ReportRecord.summary 全文
    检索: 语义相似度（ChromaDB 内置 all-MiniLM-L6-v2 嵌入）
    与 AgentMemory 完全隔离（不同 persist_dir，不同 collection）

    去重策略: report_id 以 {code}_{YYYYMMDD}_{report_type} 格式生成，
    同一天同代码同类型的报告自动覆盖（upsert）。
    """

    COLLECTION_NAME = "analysis_reports"

    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(self.COLLECTION_NAME)
        logger.info(f"RAGStore 初始化: {persist_dir}, 已有 {self._collection.count()} 条报告")

    @staticmethod
    def make_report_id(code: str, report_type: str, dt: datetime | None = None) -> str:
        """生成去重友好的 report_id — 同天同代码同类型自动覆盖

        格式: {code}_{YYYYMMDD}_{report_type}
        """
        if dt is None:
            dt = datetime.now(tz=ZoneInfo("UTC"))
        return f"{code}_{dt.strftime('%Y%m%d')}_{report_type}"

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

    def cleanup_expired(self, retention_days: int = 90) -> int:
        """清理过期报告，返回删除数量"""
        total = self._collection.count()
        if total == 0:
            return 0
        cutoff = (datetime.now(tz=ZoneInfo("UTC")) - timedelta(days=retention_days)).isoformat()
        # ChromaDB where 过滤: created_at < cutoff
        try:
            results = self._collection.get(
                where={"created_at": {"$lt": cutoff}},
            )
            if results and results["ids"]:
                self._collection.delete(ids=results["ids"])
                deleted = len(results["ids"])
                logger.info(f"RAGStore 清理过期报告: 删除 {deleted} 条（>{retention_days}天）")
                return deleted
        except Exception as e:
            logger.warning(f"RAGStore 清理过期报告失败: {e}")
        return 0

    def dedup_by_code(self) -> int:
        """对已有数据进行去重：同 code + 同 report_type 只保留最新一条

        返回删除的重复数量。
        """
        total = self._collection.count()
        if total == 0:
            return 0
        # 获取所有记录
        all_data = self._collection.get(include=["metadatas", "documents"])
        if not all_data or not all_data["ids"]:
            return 0

        # 按 (code, report_type) 分组，保留 created_at 最新的
        groups: dict[tuple[str, str], list[tuple[str, str, str]]] = {}  # key → [(id, created_at, doc)]
        for i, rid in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i]
            code = meta.get("code", "")
            rtype = meta.get("report_type", "")
            created = meta.get("created_at", "")
            key = (code, rtype)
            if key not in groups:
                groups[key] = []
            groups[key].append((rid, created, all_data["documents"][i] if all_data["documents"] else ""))

        ids_to_delete = []
        for key, items in groups.items():
            if len(items) <= 1:
                continue
            # 按 created_at 降序排序，保留第一个，删除其余
            items.sort(key=lambda x: x[1], reverse=True)
            for rid, _, _ in items[1:]:
                ids_to_delete.append(rid)

        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
            logger.info(f"RAGStore 去重: 删除 {len(ids_to_delete)} 条重复报告")
        return len(ids_to_delete)
