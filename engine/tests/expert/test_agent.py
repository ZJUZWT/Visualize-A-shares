"""Agent 测试"""

import pytest
from unittest.mock import Mock, AsyncMock
import asyncio

from expert.agent import ExpertAgent
from expert.schemas import ExpertChatRequest, BeliefNode, StanceNode


@pytest.fixture
def mock_tools():
    """创建模拟工具"""
    tools = Mock()
    tools.llm_engine = AsyncMock()
    tools.execute_tool_call = Mock(return_value={"result": "test"})
    return tools


@pytest.fixture
def expert_agent(mock_tools):
    """创建 ExpertAgent 实例"""
    return ExpertAgent(mock_tools)


@pytest.mark.asyncio
async def test_agent_initialization(expert_agent):
    """测试 Agent 初始化"""
    assert expert_agent.beliefs is not None
    assert len(expert_agent.beliefs) > 0
    assert expert_agent.stances is not None
    assert len(expert_agent.stances) > 0


@pytest.mark.asyncio
async def test_agent_get_beliefs(expert_agent):
    """测试获取信念"""
    beliefs = expert_agent.get_beliefs()
    assert len(beliefs) > 0
    assert all(isinstance(b, BeliefNode) for b in beliefs)


@pytest.mark.asyncio
async def test_agent_get_stances(expert_agent):
    """测试获取立场"""
    stances = expert_agent.get_stances()
    assert len(stances) > 0
    assert all(isinstance(s, StanceNode) for s in stances)
