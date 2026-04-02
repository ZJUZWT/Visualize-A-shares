"""Expert 对话意图分流。"""

from __future__ import annotations

import re
from typing import Literal


ExpertIntent = Literal[
    "concept_explain",
    "method_teach",
    "market_chat",
    "stock_analysis",
    "sector_analysis",
    "trading_decision",
]


_CONCEPT_PATTERNS = (
    r"什么是",
    r"是什么意思",
    r"啥是",
    r"怎么看",
    r"怎么理解",
    r"区别",
    r"原理",
    r"概念",
    r"科普",
)

_METHOD_PATTERNS = (
    r"怎么用",
    r"如何用",
    r"怎么分析",
    r"分析方法",
    r"分析框架",
    r"怎么判断",
)

_TRADING_PATTERNS = (
    r"能买吗",
    r"能不能买",
    r"买不买",
    r"买入",
    r"卖出",
    r"止损",
    r"止盈",
    r"仓位",
    r"短线",
    r"操作",
    r"机会",
)

_SECTOR_PATTERNS = (
    r"板块",
    r"行业",
    r"赛道",
    r"产业链",
)

_STOCK_CODE_RE = re.compile(r"\b\d{6}\b")


def classify_expert_intent(message: str) -> ExpertIntent:
    """基于规则的最小可用意图分类。"""
    text = (message or "").strip()
    if not text:
        return "market_chat"

    has_stock_code = bool(_STOCK_CODE_RE.search(text))
    has_sector = any(re.search(pattern, text) for pattern in _SECTOR_PATTERNS)
    has_trading = any(re.search(pattern, text) for pattern in _TRADING_PATTERNS)
    has_concept = any(re.search(pattern, text) for pattern in _CONCEPT_PATTERNS)
    has_method = any(re.search(pattern, text) for pattern in _METHOD_PATTERNS)

    if has_concept and not has_stock_code and not has_trading and not has_sector:
        return "concept_explain"
    if has_method and not has_stock_code and not has_trading:
        return "method_teach"
    if has_sector and has_trading:
        return "sector_analysis"
    if has_stock_code and has_trading:
        return "trading_decision"
    if has_stock_code:
        return "stock_analysis"
    if has_sector:
        return "sector_analysis"
    if has_trading:
        return "trading_decision"
    return "market_chat"


def should_use_direct_reply(intent: ExpertIntent) -> bool:
    """无需进入工具分析主链的意图。"""
    return intent in {"concept_explain", "method_teach"}
