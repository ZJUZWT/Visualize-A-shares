"""StockScape MCP Server — 让 AI 直接触及全量市场数据"""

from __future__ import annotations

import importlib


def __getattr__(name: str):
    if name in {"agent_backtest", "agent_verification_suite", "agent_verification"}:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
