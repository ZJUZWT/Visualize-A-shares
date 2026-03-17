"""MCP Streamable HTTP transport 基础验证"""
import pytest


def test_mcp_server_imports():
    """验证 MCP server 模块可正常导入"""
    from mcpserver.server import server
    assert server is not None


def test_mcp_streamable_http_app():
    """验证 FastMCP 能生成 streamable-http ASGI app"""
    from mcpserver.server import server
    app = server.streamable_http_app()
    assert app is not None


def test_mcp_tools_registered():
    """验证 tool 已注册（至少 22 个）"""
    from mcpserver.server import server
    tools = server._tool_manager._tools
    assert len(tools) >= 22
