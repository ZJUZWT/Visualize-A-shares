"""Agent Memory — ChromaDB 向量存储，按角色隔离 collection"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import chromadb
from loguru import logger


class AgentMemory:
    """Agent 推理记忆管理器

    每个 agent_role 拥有独立的 ChromaDB collection，互不可见。
    """

    COLLECTION_PREFIX = "memory_"

    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collections: dict[str, Any] = {}
        logger.info(f"ChromaDB 初始化: {persist_dir}")

    def _get_collection(self, agent_role: str):
        """获取或创建指定角色的 collection"""
        if agent_role not in self._collections:
            name = f"{self.COLLECTION_PREFIX}{agent_role}"
            self._collections[agent_role] = self._client.get_or_create_collection(name)
        return self._collections[agent_role]

    def store(
        self,
        agent_role: str,
        target: str,
        content: str,
        metadata: dict | None = None,
    ) -> str:
        """存储一条推理记忆，返回 ID

        同天同角色同目标会覆盖（upsert），避免无限增长。
        """
        collection = self._get_collection(agent_role)
        # 使用天级精度 ID，同天同角色同目标自动覆盖
        doc_id = f"{agent_role}_{target}_{datetime.now().strftime('%Y%m%d')}"
        meta = {
            "agent_role": agent_role,
            "target": target,
            "timestamp": datetime.now().isoformat(),
            **(metadata or {}),
        }
        # ChromaDB metadata 只支持 str/int/float/bool
        meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                for k, v in meta.items()}
        collection.upsert(documents=[content], metadatas=[meta], ids=[doc_id])
        return doc_id

    def recall(
        self,
        agent_role: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """语义检索指定角色的历史记忆"""
        collection = self._get_collection(agent_role)
        if collection.count() == 0:
            return []
        n_results = min(top_k, collection.count())
        results = collection.query(query_texts=[query], n_results=n_results)
        entries = []
        for i in range(len(results["ids"][0])):
            entries.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
        return entries

    def cleanup_expired(self, retention_days: int = 90) -> int:
        """清理所有角色 collection 中超过 retention_days 天的记忆

        返回总共删除的数量。
        """
        cutoff = (datetime.now(tz=ZoneInfo("UTC")) - timedelta(days=retention_days)).isoformat()
        total_deleted = 0
        # 遍历所有已知的 collection
        for name in self._client.list_collections():
            coll_name = name if isinstance(name, str) else getattr(name, "name", str(name))
            if not coll_name.startswith(self.COLLECTION_PREFIX):
                continue
            try:
                collection = self._client.get_collection(coll_name)
                results = collection.get(
                    where={"timestamp": {"$lt": cutoff}},
                )
                if results and results["ids"]:
                    collection.delete(ids=results["ids"])
                    total_deleted += len(results["ids"])
                    logger.info(f"AgentMemory [{coll_name}] 清理 {len(results['ids'])} 条过期记忆")
            except Exception as e:
                logger.warning(f"AgentMemory [{coll_name}] 清理失败: {e}")
        if total_deleted:
            logger.info(f"AgentMemory 总共清理 {total_deleted} 条过期记忆（>{retention_days}天）")
        return total_deleted
