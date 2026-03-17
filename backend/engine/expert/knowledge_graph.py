"""投资专家 Agent 知识图谱"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import networkx as nx
from loguru import logger

from engine.expert.schemas import (
    BeliefNode,
    EventNode,
    GraphEdge,
    GraphNode,
    MaterialNode,
    RegionNode,
    SectorNode,
    StockNode,
    StanceNode,
    new_id,
)

# 触发信念召回的关键词
BELIEF_KEYWORDS = ["政策", "基本面", "情绪", "估值", "资金", "技术", "分散", "集中"]

# 节点类型优先级（越小越优先）
NODE_PRIORITY = {
    "stock": 0, "sector": 1, "material": 2, "region": 3,
    "belief": 4, "stance": 5, "event": 6,
}


class KnowledgeGraph:
    """知识图谱：NetworkX DiGraph + JSON 持久化（asyncio.Lock 保护写操作）"""

    def __init__(self, persist_path: str | None = None):
        self.graph = nx.DiGraph()
        self.persist_path = persist_path
        self._lock = asyncio.Lock()
        if persist_path and Path(persist_path).exists():
            self.load(persist_path)

    async def add_node(self, node: GraphNode) -> None:
        """添加节点到图谱（加锁）"""
        async with self._lock:
            node_data = node.model_dump()
            self.graph.add_node(node.id, **node_data)
            logger.debug(f"Added node: {node.id} ({node.type})")

    async def add_edge(self, edge: GraphEdge) -> None:
        """添加边到图谱（加锁）"""
        async with self._lock:
            if edge.source_id not in self.graph or edge.target_id not in self.graph:
                logger.warning(
                    f"Edge references missing nodes: {edge.source_id} -> {edge.target_id}"
                )
                return
            edge_data = edge.model_dump()
            self.graph.add_edge(edge.source_id, edge.target_id, **edge_data)
            logger.debug(f"Added edge: {edge.source_id} -> {edge.target_id} ({edge.relation})")

    def add_node_sync(self, node: GraphNode) -> None:
        """同步添加节点（用于初始化，不加锁）"""
        node_data = node.model_dump()
        self.graph.add_node(node.id, **node_data)
        logger.debug(f"Added node (sync): {node.id} ({node.type})")

    def add_edge_sync(self, edge: GraphEdge) -> None:
        """同步添加边（用于初始化，不加锁）"""
        if edge.source_id not in self.graph or edge.target_id not in self.graph:
            logger.warning(
                f"Edge references missing nodes: {edge.source_id} -> {edge.target_id}"
            )
            return
        edge_data = edge.model_dump()
        self.graph.add_edge(edge.source_id, edge.target_id, **edge_data)

    def get_node(self, node_id: str) -> dict | None:
        """获取节点（返回原始 dict，含 id 字段）"""
        if node_id not in self.graph:
            return None
        data = dict(self.graph.nodes[node_id])
        data["id"] = node_id
        return data

    def get_neighbors(self, node_id: str, relation: str | None = None) -> list[str]:
        """获取邻接节点（可选按关系类型过滤）"""
        if node_id not in self.graph:
            return []
        neighbors = []
        for target in self.graph.successors(node_id):
            edge_data = self.graph.edges[node_id, target]
            if relation is None or edge_data.get("relation") == relation:
                neighbors.append(target)
        return neighbors

    def recall(self, message: str) -> list[dict]:
        """5步图谱召回算法，返回最多10个相关节点（含 id 字段）"""
        matched_ids: set[str] = set()

        # Step 1: 正则提取6位股票代码，匹配 stock 节点的 code 字段
        codes = re.findall(r"\d{6}", message)
        for node_id in self.graph.nodes():
            data = self.graph.nodes[node_id]
            if data.get("type") == "stock" and data.get("code") in codes:
                matched_ids.add(node_id)

        # Step 2: 子串匹配 stock.name / sector.name / event.name / material.name / region.name
        for node_id in self.graph.nodes():
            data = self.graph.nodes[node_id]
            node_type = data.get("type")
            if node_type in ("stock", "sector", "event", "material", "region"):
                name = data.get("name", "")
                if name and len(name) >= 2:
                    # 双向匹配：名称在消息中 或 消息中的词在名称中
                    if name in message or (len(name) >= 3 and any(
                        name[i:i+2] in message for i in range(len(name) - 1)
                    )):
                        matched_ids.add(node_id)

        # Step 3: 信念召回 — 始终返回 top 3 belief（投资分析总需要信念锚定）
        #   如果消息包含关键词则返回 top 3，否则返回 top 2
        has_belief_keyword = any(kw in message for kw in BELIEF_KEYWORDS)
        belief_limit = 3 if has_belief_keyword else 2
        belief_nodes = [
            (node_id, self.graph.nodes[node_id])
            for node_id in self.graph.nodes()
            if self.graph.nodes[node_id].get("type") == "belief"
        ]
        belief_nodes.sort(key=lambda x: x[1].get("confidence", 0), reverse=True)
        for node_id, _ in belief_nodes[:belief_limit]:
            matched_ids.add(node_id)

        # Step 4: 1-hop 扩展 — 加入所有匹配节点的直接邻居（successors + predecessors）
        hop_ids: set[str] = set()
        for node_id in list(matched_ids):
            for neighbor in self.graph.successors(node_id):
                hop_ids.add(neighbor)
            for neighbor in self.graph.predecessors(node_id):
                hop_ids.add(neighbor)
        matched_ids.update(hop_ids)

        # Step 5: 按节点类型优先级排序，截取前10个
        def priority(node_id: str) -> int:
            t = self.graph.nodes[node_id].get("type", "")
            return NODE_PRIORITY.get(t, 99)

        sorted_ids = sorted(matched_ids, key=priority)[:10]

        result = []
        for node_id in sorted_ids:
            data = dict(self.graph.nodes[node_id])
            data["id"] = node_id
            result.append(data)
        return result

    def get_all_beliefs(self) -> list[dict]:
        """获取所有 belief 节点（含 id 字段）"""
        beliefs = []
        for node_id in self.graph.nodes():
            data = self.graph.nodes[node_id]
            if data.get("type") == "belief":
                d = dict(data)
                d["id"] = node_id
                beliefs.append(d)
        return beliefs

    async def update_belief(
        self,
        old_belief_id: str,
        new_content: str,
        new_confidence: float,
        reason: str,
    ) -> str:
        """创建新信念节点并加 updated_by 边，返回新节点 id（加锁）"""
        async with self._lock:
            new_node = BeliefNode(
                content=new_content,
                confidence=new_confidence,
            )
            node_data = new_node.model_dump()
            self.graph.add_node(new_node.id, **node_data)

            if old_belief_id in self.graph:
                edge_data = {
                    "source_id": old_belief_id,
                    "target_id": new_node.id,
                    "relation": "updated_by",
                    "reason": reason,
                    "timestamp": datetime.now().isoformat(),
                }
                self.graph.add_edge(old_belief_id, new_node.id, **edge_data)
                logger.info(f"信念更新: {old_belief_id} -> {new_node.id}")

            return new_node.id

    async def save(self, path: str | None = None) -> None:
        """保存图谱到 JSON（加锁）"""
        async with self._lock:
            self._save_unlocked(path)

    def save_sync(self, path: str | None = None) -> None:
        """同步保存（用于初始化，不加锁）"""
        self._save_unlocked(path)

    def _save_unlocked(self, path: str | None = None) -> None:
        save_path = path or self.persist_path
        if not save_path:
            logger.warning("No persist path specified")
            return
        data = {
            "nodes": [dict(self.graph.nodes[n], id=n) for n in self.graph.nodes()],
            "edges": [
                dict(self.graph.edges[u, v], source_id=u, target_id=v)
                for u, v in self.graph.edges()
            ],
        }
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved knowledge graph to {save_path}")

    def load(self, path: str) -> None:
        """从 JSON 加载图谱"""
        if not Path(path).exists():
            logger.warning(f"Path not found: {path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.graph.clear()
        for node_data in data.get("nodes", []):
            node_data = dict(node_data)
            node_id = node_data.pop("id")
            self.graph.add_node(node_id, **node_data)

        for edge_data in data.get("edges", []):
            edge_data = dict(edge_data)
            source_id = edge_data.pop("source_id")
            target_id = edge_data.pop("target_id")
            self.graph.add_edge(source_id, target_id, **edge_data)

        logger.info(f"Loaded knowledge graph from {path}")

    def to_dict(self) -> dict:
        """导出完整图谱为 dict（供 /graph 端点使用）"""
        return {
            "nodes": [dict(self.graph.nodes[n], id=n) for n in self.graph.nodes()],
            "edges": [
                dict(self.graph.edges[u, v], source_id=u, target_id=v)
                for u, v in self.graph.edges()
            ],
            "stats": self.stats(),
        }

    def stats(self) -> dict[str, Any]:
        """图谱统计"""
        return {
            "num_nodes": self.graph.number_of_nodes(),
            "num_edges": self.graph.number_of_edges(),
            "node_types": self._count_node_types(),
            "edge_relations": self._count_edge_relations(),
        }

    def _count_node_types(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node_id in self.graph.nodes():
            node_type = self.graph.nodes[node_id].get("type", "unknown")
            counts[node_type] = counts.get(node_type, 0) + 1
        return counts

    def _count_edge_relations(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for u, v in self.graph.edges():
            relation = self.graph.edges[u, v].get("relation", "unknown")
            counts[relation] = counts.get(relation, 0) + 1
        return counts
