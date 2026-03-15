"""知识图谱测试"""

import json
import tempfile
from pathlib import Path

import pytest

from expert.knowledge_graph import KnowledgeGraph
from expert.schemas import (
    BeliefNode,
    GraphEdge,
    StockNode,
    SectorNode,
)


@pytest.fixture
def kg():
    """创建临时知识图谱"""
    return KnowledgeGraph()


@pytest.fixture
def temp_path():
    """创建临时文件路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "kg.json")


def test_add_node(kg):
    """测试添加节点"""
    stock = StockNode(code="300750", name="宁德时代")
    kg.add_node(stock)
    assert kg.graph.number_of_nodes() == 1
    assert stock.id in kg.graph.nodes


def test_add_edge(kg):
    """测试添加边"""
    stock = StockNode(code="300750", name="宁德时代")
    sector = SectorNode(name="新能源")
    kg.add_node(stock)
    kg.add_node(sector)

    edge = GraphEdge(
        source_id=stock.id,
        target_id=sector.id,
        relation="belongs_to",
        reason="宁德时代属于新能源行业"
    )
    kg.add_edge(edge)
    assert kg.graph.number_of_edges() == 1


def test_get_node(kg):
    """测试获取节点"""
    stock = StockNode(code="300750", name="宁德时代")
    kg.add_node(stock)
    retrieved = kg.get_node(stock.id)
    assert retrieved is not None
    assert retrieved.code == "300750"
    assert retrieved.type == "stock"


def test_recall_bfs(kg):
    """测试 BFS 召回算法"""
    stock = StockNode(code="300750", name="宁德时代")
    sector = SectorNode(name="新能源")
    belief = BeliefNode(content="新能源前景好", confidence=0.8)

    kg.add_node(stock)
    kg.add_node(sector)
    kg.add_node(belief)

    kg.add_edge(GraphEdge(
        source_id=stock.id,
        target_id=sector.id,
        relation="belongs_to"
    ))
    kg.add_edge(GraphEdge(
        source_id=sector.id,
        target_id=belief.id,
        relation="supports"
    ))

    result = kg.recall(stock.id, depth=2)
    assert len(result["nodes"]) >= 2
    assert len(result["edges"]) >= 1


def test_save_and_load(kg, temp_path):
    """测试保存和加载"""
    stock = StockNode(code="300750", name="宁德时代")
    sector = SectorNode(name="新能源")
    kg.add_node(stock)
    kg.add_node(sector)
    kg.add_edge(GraphEdge(
        source_id=stock.id,
        target_id=sector.id,
        relation="belongs_to"
    ))

    kg.save(temp_path)
    assert Path(temp_path).exists()

    kg2 = KnowledgeGraph(temp_path)
    assert kg2.graph.number_of_nodes() == 2
    assert kg2.graph.number_of_edges() == 1
