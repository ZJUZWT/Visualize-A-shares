import pytest
from expert.schemas import BeliefNode, StockNode, ThinkOutput, BeliefUpdateOutput, new_id


def test_belief_node_has_uuid_id():
    b = BeliefNode(content="test", confidence=0.7)
    assert len(b.id) == 36  # UUID format
    assert b.type == "belief"


def test_stock_node_fields():
    s = StockNode(code="300750", name="宁德时代")
    assert s.code == "300750"
    assert s.type == "stock"


def test_think_output_defaults():
    t = ThinkOutput(needs_data=False)
    assert t.tool_calls == []


def test_belief_update_output():
    out = BeliefUpdateOutput(updated=False)
    assert out.changes == []
