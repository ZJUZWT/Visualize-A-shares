"""知识图谱测试"""

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
    return KnowledgeGraph()


@pytest.fixture
def temp_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "kg.json")


def test_add_node_sync(kg):
    """测试同步添加节点"""
    stock = StockNode(code="300750", name="宁德时代")
    kg.add_node_sync(stock)
    assert kg.graph.number_of_nodes() == 1
    assert stock.id in kg.graph.nodes


def test_add_edge_sync(kg):
    """测试同步添加边"""
    stock = StockNode(code="300750", name="宁德时代")
    sector = SectorNode(name="新能源")
    kg.add_node_sync(stock)
    kg.add_node_sync(sector)
    edge = GraphEdge(source_id=stock.id, target_id=sector.id, relation="belongs_to")
    kg.add_edge_sync(edge)
    assert kg.graph.number_of_edges() == 1


@pytest.mark.asyncio
async def test_add_node_async(kg):
    """测试异步添加节点"""
    stock = StockNode(code="300750", name="宁德时代")
    await kg.add_node(stock)
    assert kg.graph.number_of_nodes() == 1
    assert stock.id in kg.graph.nodes


@pytest.mark.asyncio
async def test_add_edge_async(kg):
    """测试异步添加边"""
    stock = StockNode(code="300750", name="宁德时代")
    sector = SectorNode(name="新能源")
    await kg.add_node(stock)
    await kg.add_node(sector)
    edge = GraphEdge(source_id=stock.id, target_id=sector.id, relation="belongs_to")
    await kg.add_edge(edge)
    assert kg.graph.number_of_edges() == 1


def test_get_node_returns_dict(kg):
    """测试 get_node 返回 dict（含 id 字段）"""
    stock = StockNode(code="300750", name="宁德时代")
    kg.add_node_sync(stock)
    result = kg.get_node(stock.id)
    assert result is not None
    assert isinstance(result, dict)
    assert result["id"] == stock.id
    assert result["code"] == "300750"
    assert result["type"] == "stock"


def test_get_node_missing(kg):
    """测试获取不存在的节点返回 None"""
    assert kg.get_node("nonexistent") is None


def test_recall_by_stock_code(kg):
    """测试通过股票代码召回"""
    stock = StockNode(code="300750", name="宁德时代")
    kg.add_node_sync(stock)
    results = kg.recall("请分析300750的走势")
    assert any(n["id"] == stock.id for n in results)


def test_recall_by_stock_name(kg):
    """测试通过股票名称召回"""
    stock = StockNode(code="300750", name="宁德时代")
    kg.add_node_sync(stock)
    results = kg.recall("宁德时代最近怎么样")
    assert any(n["id"] == stock.id for n in results)


def test_recall_by_belief_keyword(kg):
    """测试通过信念关键词召回"""
    belief = BeliefNode(content="政策是A股重要变量", confidence=0.8)
    kg.add_node_sync(belief)
    results = kg.recall("政策对市场有什么影响")
    assert any(n["id"] == belief.id for n in results)


def test_recall_1hop_expansion(kg):
    """测试1-hop扩展"""
    stock = StockNode(code="300750", name="宁德时代")
    sector = SectorNode(name="新能源")
    kg.add_node_sync(stock)
    kg.add_node_sync(sector)
    kg.add_edge_sync(GraphEdge(source_id=stock.id, target_id=sector.id, relation="belongs_to"))
    # 通过代码匹配到 stock，1-hop 应扩展到 sector
    results = kg.recall("300750")
    ids = [n["id"] for n in results]
    assert stock.id in ids
    assert sector.id in ids


def test_recall_returns_at_most_10(kg):
    """测试召回最多10个节点"""
    for i in range(15):
        kg.add_node_sync(StockNode(code=f"{300000+i:06d}", name=f"股票{i}"))
    # 触发信念关键词，加入大量节点
    for i in range(5):
        kg.add_node_sync(BeliefNode(content=f"信念{i}", confidence=0.5))
    results = kg.recall("政策基本面情绪估值资金技术")
    assert len(results) <= 10


def test_recall_empty_graph(kg):
    """测试空图谱召回返回空列表"""
    results = kg.recall("300750")
    assert results == []


def test_get_all_beliefs(kg):
    """测试获取所有信念节点"""
    b1 = BeliefNode(content="信念1", confidence=0.7)
    b2 = BeliefNode(content="信念2", confidence=0.8)
    stock = StockNode(code="000001", name="平安银行")
    kg.add_node_sync(b1)
    kg.add_node_sync(b2)
    kg.add_node_sync(stock)
    beliefs = kg.get_all_beliefs()
    assert len(beliefs) == 2
    assert all(b["type"] == "belief" for b in beliefs)


@pytest.mark.asyncio
async def test_update_belief(kg):
    """测试信念更新创建新节点和 updated_by 边"""
    old = BeliefNode(content="旧信念", confidence=0.5)
    kg.add_node_sync(old)
    new_id = await kg.update_belief(
        old_belief_id=old.id,
        new_content="新信念",
        new_confidence=0.9,
        reason="测试原因",
    )
    assert new_id != old.id
    assert new_id in kg.graph.nodes
    assert kg.graph.has_edge(old.id, new_id)
    edge_data = kg.graph.edges[old.id, new_id]
    assert edge_data["relation"] == "updated_by"
    assert edge_data["reason"] == "测试原因"


def test_save_and_load(kg, temp_path):
    """测试保存和加载"""
    stock = StockNode(code="300750", name="宁德时代")
    sector = SectorNode(name="新能源")
    kg.add_node_sync(stock)
    kg.add_node_sync(sector)
    kg.add_edge_sync(GraphEdge(source_id=stock.id, target_id=sector.id, relation="belongs_to"))
    kg.save_sync(temp_path)
    assert Path(temp_path).exists()

    kg2 = KnowledgeGraph(temp_path)
    assert kg2.graph.number_of_nodes() == 2
    assert kg2.graph.number_of_edges() == 1


def test_to_dict(kg):
    """测试 to_dict 导出"""
    stock = StockNode(code="300750", name="宁德时代")
    kg.add_node_sync(stock)
    d = kg.to_dict()
    assert "nodes" in d
    assert "edges" in d
    assert "stats" in d
    assert len(d["nodes"]) == 1
