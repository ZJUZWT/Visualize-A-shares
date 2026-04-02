"""MCP expert tool regression tests."""
import asyncio
import importlib
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def _load_server_module():
    for name in list(sys.modules):
        if name == "mcpserver" or name.startswith("mcpserver."):
            sys.modules.pop(name, None)
    return importlib.import_module("mcpserver.server")


class _FakeContext:
    def __init__(self):
        self.logs: list[tuple[str, str]] = []

    async def log(self, level: str, message: str):
        self.logs.append((level, message))


class _FakeStreamResponse:
    def __init__(self, lines: list[tuple[float, str]]):
        self._lines = lines
        self.status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for delay, line in self._lines:
            if delay:
                await asyncio.sleep(delay)
            yield line


@pytest.mark.asyncio
async def test_ask_expert_keeps_mcp_context_alive_during_long_silence(monkeypatch):
    module = _load_server_module()
    ctx = _FakeContext()
    captured: dict[str, object] = {}
    lines = [
        (0.0, "event: thinking_start"),
        (0.0, 'data: {"message":"start"}'),
        (0.0, ""),
        (0.03, "event: reply_complete"),
        (0.0, 'data: {"full_text":"完整回复"}'),
        (0.0, ""),
    ]

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json):
            captured["request"] = {"method": method, "url": url, "json": json}
            return _FakeStreamResponse(lines)

    monkeypatch.setattr(module._da, "is_online", lambda: True)
    monkeypatch.setattr(module, "_EXPERT_MCP_HEARTBEAT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await module.ask_expert("info", "为什么中泰化学一直在跌", ctx=ctx)

    assert result == "完整回复"
    assert captured["request"] == {
        "method": "POST",
        "url": f"{module._da._api_base}/api/v1/expert/chat/info",
        "json": {"message": "为什么中泰化学一直在跌"},
    }
    timeout = captured["timeout"]
    assert timeout.read is None
    assert any("处理中" in message for _, message in ctx.logs)


@pytest.mark.asyncio
async def test_ask_expert_routes_simple_rag_drop_question_to_info_fast_path(monkeypatch):
    module = _load_server_module()
    captured: dict[str, object] = {}
    lines = [
        (0.0, "event: reply_complete"),
        (0.0, 'data: {"full_text":"快速回复"}'),
        (0.0, ""),
    ]

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json):
            captured["request"] = {"method": method, "url": url, "json": json}
            return _FakeStreamResponse(lines)

    monkeypatch.setattr(module._da, "is_online", lambda: True)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await module.ask_expert("rag", "为什么中泰化学一直在跌")

    assert result == "快速回复"
    assert captured["request"]["url"].endswith("/api/v1/expert/chat/info")


@pytest.mark.asyncio
async def test_ask_expert_fast_path_still_routes_when_stock_map_unavailable(monkeypatch):
    module = _load_server_module()
    captured: dict[str, object] = {}
    lines = [
        (0.0, "event: reply_complete"),
        (0.0, 'data: {"full_text":"快速回复"}'),
        (0.0, ""),
    ]

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json):
            captured["request"] = {"method": method, "url": url, "json": json}
            return _FakeStreamResponse(lines)

    def _raise_stock_map_error(cls):
        raise RuntimeError("duckdb locked")

    monkeypatch.setattr(module._da, "is_online", lambda: True)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    from engine.expert.agent import ExpertAgent

    monkeypatch.setattr(ExpertAgent, "_get_stock_name_map", classmethod(_raise_stock_map_error))

    result = await module.ask_expert("rag", "为什么中泰化学一直在跌")

    assert result == "快速回复"
    assert captured["request"]["url"].endswith("/api/v1/expert/chat/info")


@pytest.mark.asyncio
async def test_ask_expert_fast_path_does_not_reroute_generic_sector_question(monkeypatch):
    module = _load_server_module()
    captured: dict[str, object] = {}
    lines = [
        (0.0, "event: reply_complete"),
        (0.0, 'data: {"full_text":"板块回复"}'),
        (0.0, ""),
    ]

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json):
            captured["request"] = {"method": method, "url": url, "json": json}
            return _FakeStreamResponse(lines)

    monkeypatch.setattr(module._da, "is_online", lambda: True)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = await module.ask_expert("rag", "为什么新能源板块一直在跌")

    assert result == "板块回复"
    assert captured["request"]["url"].endswith("/api/v1/expert/chat/rag")
