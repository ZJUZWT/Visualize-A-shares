# engine/info_engine/event_assessor.py
"""事件影响评估器 — LLM 驱动"""

import json

from loguru import logger

from .schemas import EventImpact


class EventAssessor:
    """事件影响评估 — LLM 驱动，无 LLM 时退化为中性

    Args:
        llm_provider: BaseLLMProvider 实例。None 时返回 neutral。
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    async def assess(
        self,
        code: str,
        event_desc: str,
        stock_context: dict | None = None,
    ) -> EventImpact:
        """评估事件对个股的影响"""
        if not self._llm:
            return EventImpact(
                event_desc=event_desc,
                impact="neutral",
                magnitude="low",
                reasoning="LLM 未配置，无法评估事件影响",
                affected_factors=[],
            )

        try:
            return await self._assess_llm(code, event_desc, stock_context)
        except Exception as e:
            logger.warning(f"LLM 事件评估失败 [{code}]: {e}")
            return EventImpact(
                event_desc=event_desc,
                impact="neutral",
                magnitude="low",
                reasoning=f"LLM 评估失败: {e}",
                affected_factors=[],
            )

    async def _assess_llm(
        self,
        code: str,
        event_desc: str,
        stock_context: dict | None,
    ) -> EventImpact:
        """LLM 驱动的事件评估"""
        from llm.providers import ChatMessage

        context_text = ""
        if stock_context:
            context_text = f"\n\n个股背景: {json.dumps(stock_context, ensure_ascii=False)}"

        messages = [
            ChatMessage("system",
                "你是一个金融事件影响评估专家。分析以下事件对指定股票的潜在影响。"
                "仅返回 JSON（不要 markdown 代码块），格式："
                '{"impact": "positive|negative|neutral", '
                '"magnitude": "high|medium|low", '
                '"reasoning": "推理过程", '
                '"affected_factors": ["因素1", "因素2"]}'
            ),
            ChatMessage("user",
                f"股票代码: {code}\n事件: {event_desc}{context_text}"
            ),
        ]

        raw = await self._llm.chat(messages)
        data = json.loads(raw.strip())
        return EventImpact(
            event_desc=event_desc,
            impact=data["impact"],
            magnitude=data["magnitude"],
            reasoning=data["reasoning"],
            affected_factors=data.get("affected_factors", []),
        )
