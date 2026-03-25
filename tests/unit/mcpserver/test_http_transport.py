"""MCP Streamable HTTP transport 基础验证"""
import importlib
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND))


def _load_server_module():
    for name in list(sys.modules):
        if name == "mcpserver" or name.startswith("mcpserver."):
            sys.modules.pop(name, None)
    return importlib.import_module("mcpserver.server")

import pytest


def test_mcp_server_imports():
    """验证 MCP server 模块可正常导入"""
    module = _load_server_module()
    assert module.server is not None


def test_mcp_streamable_http_app():
    """验证 FastMCP 能生成 streamable-http ASGI app"""
    module = _load_server_module()
    app = module.server.streamable_http_app()
    assert app is not None


def test_mcp_tools_registered():
    """验证 verification tool 已注册到 MCP server"""
    module = _load_server_module()
    tools = module.server._tool_manager._tools
    assert "run_demo_agent_verification_suite" in tools
    assert "run_agent_backtest" in tools
    assert "get_agent_backtest_summary" in tools
    assert "get_agent_backtest_day" in tools
    assert "verify_agent_cycle" in tools
    assert "inspect_agent_snapshot" in tools
    assert "prepare_demo_agent_portfolio" in tools
    assert "verify_demo_agent_cycle" in tools
    assert "get_demo_agent_cycle_summary" in tools
    assert len(tools) >= 30


def test_mcp_server_does_not_eager_import_agent_verification():
    """验证 server 模块导入时不会提前 import agent_verification 包装层"""
    _load_server_module()
    assert "mcpserver.agent_verification" not in sys.modules


def test_mcp_server_does_not_eager_import_agent_backtest():
    """验证 server 模块导入时不会提前 import agent_backtest 包装层"""
    _load_server_module()
    assert "mcpserver.agent_backtest" not in sys.modules
