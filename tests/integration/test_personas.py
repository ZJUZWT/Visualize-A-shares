"""Agent 人格定义和工具白名单测试"""
import pytest


def test_all_three_personas_defined():
    from engine.arena.personas import AGENT_PERSONAS
    assert "fundamental" in AGENT_PERSONAS
    assert "info" in AGENT_PERSONAS
    assert "quant" in AGENT_PERSONAS


def test_persona_has_required_fields():
    from engine.arena.personas import AGENT_PERSONAS
    required = {"role", "perspective", "bias", "risk_tolerance",
                "confidence_calibration", "forbidden_factors"}
    for name, persona in AGENT_PERSONAS.items():
        missing = required - set(persona.keys())
        assert not missing, f"Agent '{name}' 缺少字段: {missing}"


def test_tool_access_all_roles_defined():
    from engine.arena.personas import AGENT_TOOL_ACCESS
    expected_roles = {"prescreen", "fundamental", "info", "quant",
                      "aggregator", "expert"}
    assert set(AGENT_TOOL_ACCESS.keys()) == expected_roles


def test_tool_access_no_overlap_for_analysis_agents():
    """基本面/消息面/技术面 Agent 的工具不应该交叉（除 search_stocks）"""
    from engine.arena.personas import AGENT_TOOL_ACCESS
    fundamental = set(AGENT_TOOL_ACCESS["fundamental"])
    info = set(AGENT_TOOL_ACCESS["info"])
    quant = set(AGENT_TOOL_ACCESS["quant"])
    assert not (fundamental & info), f"基本面和消息面工具有交叉: {fundamental & info}"


def test_build_system_prompt_contains_persona():
    from engine.arena.personas import build_system_prompt
    prompt = build_system_prompt("fundamental", calibration_weight=0.8)
    assert "基本面分析师" in prompt
    assert "价值投资" in prompt
    assert "0.8" in prompt


def test_build_system_prompt_contains_forbidden():
    from engine.arena.personas import build_system_prompt
    prompt = build_system_prompt("info", calibration_weight=0.6)
    assert "PE" in prompt
