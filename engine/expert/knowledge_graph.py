"""投资专家 Agent 知识图谱"""

import json
from pathlib import Path
from typing import Any

import networkx as nx
from loguru import logger

from expert.schemas import (
    BeliefNode,
    EventNode,
    GraphEdge,
    GraphNode,
    SectorNode,
    StockNode,
    StanceNode,
)


class KnowledgeGraph:
    """知识图谱：NetworkX DiGraph + JSON 持久化"""

    def __init__(self, persist_path: str | None = None):
        self.graph = nx.DiGraph()
        self.persist_path = persist_path
        if persist_path and Path(persist_path).exists():
            self.load(persist_path)

    def add_node(self, node: GraphNode) -> None:
        """添加节点到图谱"""
        node_data = node.model_dump()
        self.graph.add_node(node.id, **node_data)
        logger.debug(f"Added node: {node.id} ({node.type})")

    def add_edge(self, edge: GraphEdge) -> None:
        """添加边到图谱"""
        if edge.source_id not in self.graph or edge.target_id not in self.graph:
            logger.warning(
                f"Edge references missing nodes: {edge.source_id} -> {edge.target_id}"
            )
            return
        edge_data = edge.model_dump()
        self.graph.add_edge(edge.source_id, edge.target_id, **edge_data)
        logger.debug(f"Added edge: {edge.source_id} -> {edge.target_id} ({edge.relation})")

    def get_node(self, node_id: str) -> GraphNode | None:
        """获取节点"""
        if node_id not in self.graph:
            return None
        data = self.graph.nodes[node_id]
        node_type = data.get("type")
        if node_type == "stock":
            return StockNode(**data)
        elif node_type == "sector":
            return SectorNode(**data)
        elif node_type == "event":
            return EventNode(**data)
        elif node_type == "belief":
            return BeliefNode(**data)
        elif node_type == "stance":
            return StanceNode(**data)
        return None

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

    def recall(self, query_node_id: str, depth: int = 2) -> dict[str, Any]:
        """召回算法：BFS 获取相关节点和边"""
        if query_node_id not in self.graph:
            return {"nodes": [], "edges": []}

        visited = set()
        queue = [(query_node_id, 0)]
        nodes_data = []
        edges_data = []

        while queue:
            node_id, current_depth = queue.pop(0)
            if node_id in visited or current_depth > depth:
                continue
            visited.add(node_id)

            node_data = self.graph.nodes[node_id]
            nodes_data.append(node_data)

            if current_depth < depth:
                for neighbor in self.graph.successors(node_id):
                    if neighbor not in visited:
                        queue.append((neighbor, current_depth + 1))
                        edge_data = self.graph.edges[node_id, neighbor]
                        edges_data.append(edge_data)

        return {"nodes": nodes_data, "edges": edges_data}

    def save(self, path: str | None = None) -> None:
        """保存图谱到 JSON"""
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
            node_id = node_data.pop("id")
            self.graph.add_node(node_id, **node_data)

        for edge_data in data.get("edges", []):
            source_id = edge_data.pop("source_id")
            target_id = edge_data.pop("target_id")
            self.graph.add_edge(source_id, target_id, **edge_data)

        logger.info(f"Loaded knowledge graph from {path}")

    def stats(self) -> dict[str, Any]:
        """图谱统计"""
        return {
            "num_nodes": self.graph.number_of_nodes(),
            "num_edges": self.graph.number_of_edges(),
            "node_types": self._count_node_types(),
            "edge_relations": self._count_edge_relations(),
        }

    def _count_node_types(self) -> dict[str, int]:
        """统计节点类型"""
        counts = {}
        for node_id in self.graph.nodes():
            node_type = self.graph.nodes[node_id].get("type", "unknown")
            counts[node_type] = counts.get(node_type, 0) + 1
        return counts

    def _count_edge_relations(self) -> dict[str, int]:
        """统计边关系类型"""
        counts = {}
        for u, v in self.graph.edges():
            relation = self.graph.edges[u, v].get("relation", "unknown")
            counts[relation] = counts.get(relation, 0) + 1
        return counts
