# tests/test_chain_schemas.py
"""产业链推演 Schema 单元测试"""
import pytest
from engine.industry.chain_schemas import (
    PhysicalConstraint,
    ChainNode,
    ChainLink,
    ChainExploreRequest,
    ChainExploreResult,
)


def test_physical_constraint_defaults():
    pc = PhysicalConstraint(node="乙烯裂解")
    assert pc.node == "乙烯裂解"
    assert pc.shutdown_recovery_time == ""
    assert pc.restart_cost == ""


def test_chain_node_creation():
    node = ChainNode(
        id="n_石油",
        name="石油",
        node_type="material",
        impact="neutral",
    )
    assert node.id == "n_石油"
    assert node.node_type == "material"
    assert node.representative_stocks == []


def test_chain_link_with_constraint():
    link = ChainLink(
        source="石油",
        target="乙烯",
        relation="upstream",
        impact="negative",
        impact_reason="油价上涨推升乙烯成本",
        confidence=0.85,
        transmission_speed="1-3个月",
        transmission_strength="强刚性",
        transmission_mechanism="成本推动",
        dampening_factors=["库存缓冲30天", "长协价锁定"],
        amplifying_factors=["行业集中度高"],
        constraint=PhysicalConstraint(
            node="乙烯裂解",
            shutdown_recovery_time="冷启动需2-4周",
            restart_cost="重启一次数千万元",
        ),
    )
    assert link.confidence == 0.85
    assert len(link.dampening_factors) == 2
    assert link.constraint.shutdown_recovery_time == "冷启动需2-4周"


def test_chain_explore_request_validation():
    req = ChainExploreRequest(event="石油涨价", max_depth=3)
    assert req.event == "石油涨价"
    assert req.max_depth == 3
    assert req.start_node == ""


def test_chain_explore_request_depth_bounds():
    with pytest.raises(Exception):
        ChainExploreRequest(event="石油涨价", max_depth=0)
    with pytest.raises(Exception):
        ChainExploreRequest(event="石油涨价", max_depth=7)


def test_chain_explore_result_empty():
    result = ChainExploreResult(event="石油涨价")
    assert result.nodes == []
    assert result.links == []
    assert result.depth_reached == 0
