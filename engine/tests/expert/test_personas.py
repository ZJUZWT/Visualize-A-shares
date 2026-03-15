"""人格和提示词测试"""

import json

import pytest

from expert.personas import (
    INITIAL_BELIEFS,
    INITIAL_STANCES,
    THINK_SYSTEM_PROMPT,
    BELIEF_UPDATE_PROMPT,
    format_beliefs_for_prompt,
    format_stances_for_prompt,
    format_debate_prompt,
)
from expert.schemas import BeliefNode, StanceNode


def test_initial_beliefs_exist():
    """测试初始信念存在"""
    assert len(INITIAL_BELIEFS) > 0
    assert all(isinstance(b, BeliefNode) for b in INITIAL_BELIEFS)
    assert all(0 <= b.confidence <= 1 for b in INITIAL_BELIEFS)


def test_initial_stances_exist():
    """测试初始立场存在"""
    assert len(INITIAL_STANCES) > 0
    assert all(isinstance(s, StanceNode) for s in INITIAL_STANCES)
    assert all(s.signal in ["bullish", "bearish", "neutral"] for s in INITIAL_STANCES)


def test_think_system_prompt_valid():
    """测试思考系统提示词有效"""
    assert THINK_SYSTEM_PROMPT
    assert "JSON" in THINK_SYSTEM_PROMPT
    assert "needs_data" in THINK_SYSTEM_PROMPT
    assert "tool_calls" in THINK_SYSTEM_PROMPT


def test_belief_update_prompt_valid():
    """测试信念更新提示词有效"""
    assert BELIEF_UPDATE_PROMPT
    assert "JSON" in BELIEF_UPDATE_PROMPT
    assert "{current_beliefs}" in BELIEF_UPDATE_PROMPT
    assert "{new_information}" in BELIEF_UPDATE_PROMPT


def test_format_beliefs_for_prompt():
    """测试格式化信念"""
    beliefs = [
        BeliefNode(content="test belief 1", confidence=0.8),
        BeliefNode(content="test belief 2", confidence=0.6),
    ]
    formatted = format_beliefs_for_prompt(beliefs)
    assert "test belief 1" in formatted
    assert "80.0%" in formatted
    assert "60.0%" in formatted


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


def test_format_debate_prompt():
    """测试格式化辩论提示词"""
    prompt = format_debate_prompt(
        role="bull_expert",
        code="300750",
        name="宁德时代",
        stance="看多新能源",
        beliefs="新能源前景好",
    )
    assert "看多专家" in prompt
    assert "300750" in prompt
    assert "宁德时代" in prompt
    assert "看多新能源" in prompt
    assert "新能源前景好" in prompt
