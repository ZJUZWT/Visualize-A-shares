"""工具层测试"""

import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd

from expert.tools import ExpertTools
from expert.schemas import ToolCall


@pytest.fixture
def mock_engines():
    """创建模拟引擎"""
    data_engine = Mock()
    cluster_engine = Mock()
    llm_engine = Mock()
    return data_engine, cluster_engine, llm_engine


@pytest.fixture
def expert_tools(mock_engines):
    """创建 ExpertTools 实例"""
    data_engine, cluster_engine, llm_engine = mock_engines
    return ExpertTools(data_engine, cluster_engine, llm_engine)


def test_execute_data_engine_search_stock(expert_tools, mock_engines):
    """测试数据引擎搜索股票"""
    data_engine, _, _ = mock_engines

    # 模拟快照数据
    snapshot_df = pd.DataFrame({
        "code": ["300750", "000001"],
        "name": ["宁德时代", "平安银行"],
        "price": [100.0, 10.0],
        "pct_chg": [1.5, -0.5],
    })
    data_engine.get_snapshot.return_value = snapshot_df

    tool_call = ToolCall(
        engine="data",
        action="search_stock",
        params={"query": "300750", "limit": 10}
    )
    result = expert_tools.execute_tool_call(tool_call)

    assert "results" in result
    assert len(result["results"]) > 0
    assert result["results"][0]["code"] == "300750"


def test_execute_cluster_engine_search_stocks(expert_tools, mock_engines):
    """测试聚类引擎搜索股票"""
    _, cluster_engine, _ = mock_engines

    cluster_engine.search_stocks.return_value = [
        {"code": "300750", "name": "宁德时代", "cluster_id": 1}
    ]

    tool_call = ToolCall(
        engine="cluster",
        action="search_stocks",
        params={"query": "宁德", "limit": 10}
    )
    result = expert_tools.execute_tool_call(tool_call)

    assert "results" in result
    assert len(result["results"]) > 0


def test_execute_unknown_engine(expert_tools):
    """测试未知引擎"""
    tool_call = ToolCall(
        engine="unknown",
        action="test",
        params={}
    )
    result = expert_tools.execute_tool_call(tool_call)

    assert "error" in result
    assert "Unknown engine" in result["error"]
