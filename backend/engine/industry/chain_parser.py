"""智能输入拆解 — 将任意文本拆解为产业链图节点列表

快速路径：如果输入是已知的单实体（关键词表命中），直接返回，不调 LLM。
慢速路径：多实体 / 关系型 / 宏观事件 → 调 LLM 拆解。
"""

from __future__ import annotations

import json
import re

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from .chain_agent import _MATERIAL_KEYWORDS, _INDUSTRY_KEYWORDS, _guess_subject_type, _lenient_json_loads

# ── Prompt ──

PARSE_INPUT_PROMPT = """你是一个产业链分析助手。用户输入了一段文本，请拆解为独立的分析节点。

## 用户输入
{user_input}

## 规则
1. 将输入拆解为 1~5 个独立的分析节点
2. 每个节点是一个可以独立存在于产业链图中的实体
3. 如果输入就是单个实体（如"宁德时代"），返回 1 个节点
4. 如果输入包含关系描述（如"黄金与石油的关系"），拆解为多个独立实体节点
5. 如果输入是宏观事件（如"美联储加息"），把它当作一个事件节点
6. 每个节点判断类型：company/material/industry/macro/commodity/event

## 示例
输入："黄金与石油的关系"
输出：{{"nodes": [{{"name": "黄金", "type": "commodity"}}, {{"name": "石油", "type": "commodity"}}]}}

输入："美联储加息对新兴市场的影响"
输出：{{"nodes": [{{"name": "美联储加息", "type": "macro"}}, {{"name": "新兴市场", "type": "industry"}}]}}

输入："宁德时代"
输出：{{"nodes": [{{"name": "宁德时代", "type": "company"}}]}}

输入："战争频繁 vs 和平时期"
输出：{{"nodes": [{{"name": "地缘冲突", "type": "macro"}}, {{"name": "和平红利", "type": "macro"}}]}}

## 输出格式
直接输出 JSON：
{{"nodes": [{{"name": "...", "type": "company|material|industry|macro|commodity|event"}}]}}
"""

# ── 关系型/宏观型关键词 — 触发 LLM 拆解 ──

_RELATION_TRIGGERS = {"与", "和", "对", "vs", "VS", "关系", "影响", "冲击", "导致"}

_MACRO_KEYWORDS = {
    "加息", "降息", "利率", "汇率", "通胀", "通缩", "衰退", "萧条",
    "战争", "冲突", "制裁", "封锁", "关税", "贸易战", "选举", "政策",
    "QE", "缩表", "美联储", "央行", "美元", "人民币", "日元",
    "地震", "台风", "洪水", "干旱", "疫情", "瘟疫",
}

_COMMODITY_KEYWORDS = {
    "黄金", "白银", "原油", "石油", "天然气", "铜", "铁矿石", "铝",
    "锂", "镍", "钴", "稀土", "大豆", "玉米", "小麦", "棉花",
    "螺纹钢", "焦炭", "焦煤", "棕榈油", "豆粕", "白糖", "橡胶",
    "美元指数", "比特币",
}


class ChainInputParser:
    """将任意文本拆解为节点列表"""

    def __init__(self, llm: BaseLLMProvider):
        self._llm = llm

    async def parse(self, user_input: str) -> list[dict]:
        """返回 [{"name": "xxx", "type": "company|material|..."}]"""
        s = user_input.strip()
        if not s:
            return []

        # ── 快速路径：单实体命中关键词表 ──
        if not self._needs_llm_parse(s):
            t = _guess_subject_type_extended(s)
            return [{"name": s, "type": t}]

        # ── 慢速路径：LLM 拆解 ──
        try:
            prompt = PARSE_INPUT_PROMPT.format(user_input=s)
            chunks: list[str] = []
            async for token in self._llm.chat_stream(
                [ChatMessage(role="user", content=prompt)]
            ):
                chunks.append(token)
            raw = "".join(chunks)
            parsed = _lenient_json_loads(raw)
            nodes = parsed.get("nodes", [])
            if not nodes:
                return [{"name": s, "type": _guess_subject_type_extended(s)}]
            return [
                {"name": n.get("name", s), "type": n.get("type", "industry")}
                for n in nodes
            ]
        except Exception as e:
            logger.warning(f"ChainInputParser LLM 拆解失败，回退: {e}")
            return [{"name": s, "type": _guess_subject_type_extended(s)}]

    def _needs_llm_parse(self, s: str) -> bool:
        """判断是否需要 LLM 拆解（包含关系词/多实体暗示）"""
        for trigger in _RELATION_TRIGGERS:
            if trigger in s:
                return True
        return False


def _guess_subject_type_extended(subject: str) -> str:
    """扩展版类型判断 — 增加 macro/commodity"""
    s = subject.strip()

    # 宏观关键词
    for kw in _MACRO_KEYWORDS:
        if kw in s:
            return "macro"

    # 大宗商品
    for kw in _COMMODITY_KEYWORDS:
        if kw == s or kw in s:
            return "commodity"

    # 回退到原有判断
    return _guess_subject_type(s)
