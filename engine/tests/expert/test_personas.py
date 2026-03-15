"""人格和提示词测试"""

import pytest

from expert.personas import (
    INITIAL_BELIEFS,
    INITIAL_STANCES,
    THINK_SYSTEM_PROMPT,
    BELIEF_UPDATE_PROMPT,
    format_beliefs_for_prompt,
    format_stances_for_prompt,
    format_graph_context,
    format_memory_context,
    format_beliefs_context,
)
from expert.schemas import BeliefNode, StanceNode


def test_initial_beliefs_exist():
    """测试初始信念存在且格式正确"""
    assert len(INITIAL_BELIEFS) > 0
    for b in INITIAL_BELIEFS:
        assert isinstance(b, dict)
        assert "content" in b
        assert "confidence" in b
        assert 0 <= b["confidence"] <= 1


def test_initial_stances_is_list():
    """测试初始立场是列表（可为空）"""
    assert isinstance(INITIAL_STANCES, list)


def test_think_system_prompt_valid():
    """测试思考系统提示词有效"""
    assert THINK_SYSTEM_PROMPT
    assert "JSON" in THINK_SYSTEM_PROMPT
    assert "needs_data" in THINK_SYSTEM_PROMPT
    assert "tool_calls" in THINK_SYSTEM_PROMPT
    assert "{graph_context}" in THINK_SYSTEM_PROMPT
    assert "{memory_context}" in THINK_SYSTEM_PROMPT


def test_belief_update_prompt_valid():
    """测试信念更新提示词有效"""
    assert BELIEF_UPDATE_PROMPT
    assert "JSON" in BELIEF_UPDATE_PROMPT
    assert "{beliefs_context}" in BELIEF_UPDATE_PROMPT
    assert "{user_message}" in BELIEF_UPDATE_PROMPT
    assert "{expert_reply}" in BELIEF_UPDATE_PROMPT


def test_format_beliefs_for_prompt_with_objects():
    """测试格式化信念（BeliefNode 对象）"""
    beliefs = [
        BeliefNode(content="test belief 1", confidence=0.8),
        BeliefNode(content="test belief 2", confidence=0.6),
    ]
    formatted = format_beliefs_for_prompt(beliefs)
    assert "test belief 1" in formatted
    assert "80.0%" in formatted
    assert "60.0%" in formatted


def test_format_beliefs_for_prompt_with_dicts():
    """测试格式化信念（dict）"""
    beliefs = [{"content": "test belief", "confidence": 0.7}]
    formatted = format_beliefs_for_prompt(beliefs)
    assert "test belief" in formatted
    assert "70.0%" in formatted


def test_format_stances_for_prompt():
    """测试格式化立场"""
    stances = [
        StanceNode(target="新能源", signal="bullish", score=0.7, confidence=0.8),
        StanceNode(target="消费", signal="bearish", score=-0.5, confidence=0.6),
    ]
    formatted = format_stances_for_prompt(stances)
    assert "新能源" in formatted
    assert "看多" in formatted
    assert "消费" in formatted
    assert "看空" in formatted


def test_format_graph_context_empty():
    assert "无相关" in format_graph_context([])


def test_format_graph_context_with_nodes():
    nodes = [
        {"id": "abc123", "type": "belief", "content": "政策很重要", "confidence": 0.8},
        {"id": "def456", "type": "stock", "code": "300750", "name": "宁德时代"},
    ]
    result = format_graph_context(nodes)
    assert "政策很重要" in result
    assert "300750" in result


def test_format_memory_context_empty():
    assert "无相关" in format_memory_context([])


def test_format_beliefs_context_empty():
    assert "暂无" in format_beliefs_context([])


def test_format_beliefs_context_with_beliefs():
    beliefs = [{"id": "abc-123", "content": "测试信念", "confidence": 0.75}]
    result = format_beliefs_context(beliefs)
    assert "abc-123" in result
    assert "测试信念" in result
