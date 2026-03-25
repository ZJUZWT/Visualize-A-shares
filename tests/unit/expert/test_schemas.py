import pytest
from engine.expert.schemas import (
    BeliefNode,
    StockNode,
    ThinkOutput,
    BeliefUpdateOutput,
    new_id,
    ClarificationOutput,
    ClarificationOption,
    ClarificationSelection,
    SelfCritiqueOutput,
)


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


def test_clarification_output_contains_skip_option():
    out = ClarificationOutput(
        should_clarify=True,
        question_summary="你想先判断这只股票值不值得继续跟踪。",
        reasoning="问题较宽，需要先确认关注重点。",
        options=[
            ClarificationOption(
                id="valuation",
                label="A",
                title="先看估值与安全边际",
                description="判断值不值、贵不贵。",
                focus="估值、安全边际、赔率",
            )
        ],
        skip_option=ClarificationOption(
            id="skip",
            label="S",
            title="跳过，直接分析",
            description="不做澄清，直接进入完整分析。",
            focus="完整分析",
        ),
    )
    assert out.should_clarify is True
    assert out.skip_option.id == "skip"


def test_self_critique_output_defaults_to_empty_lists():
    critique = SelfCritiqueOutput(summary="有一定不确定性")
    assert critique.risks == []
    assert critique.counterpoints == []
    assert critique.missing_data == []


def test_clarification_selection_can_mark_skip():
    selection = ClarificationSelection(
        option_id="skip",
        label="S",
        title="跳过，直接分析",
        focus="完整分析",
        skip=True,
    )
    assert selection.skip is True
