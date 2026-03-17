# engine/info_engine/event_assessor.py
"""事件影响评估器 — LLM 驱动"""

import json

from loguru import logger

from .schemas import EventImpact


class EventAssessor:
    """事件影响评估 — LLM 驱动，无 LLM 时退化为中性

    Args:
        llm_capability: LLMCapability 实例。None 或 disabled 时返回 neutral。
    """

    def __init__(self, llm_capability=None):
        self._llm = llm_capability

    async def assess(
        self,
        code: str,
        event_desc: str,
        stock_context: dict | None = None,
    ) -> EventImpact:
        """评估事件对个股的影响"""
        if not self._llm or not self._llm.enabled:
            return EventImpact(
                event_desc=event_desc,
                impact="neutral",
                magnitude="low",
                reasoning="LLM 未配置，无法评估",
                affected_factors=[],
            )

        try:
            result = await self._llm.extract(
                text=(
                    f"股票代码: {code}\n"
                    f"事件: {event_desc}\n"
                    f"上下文: {json.dumps(stock_context or {}, ensure_ascii=False)}"
                ),
                schema={
                    "impact": "positive|negative|neutral",
                    "magnitude": "high|medium|low",
                    "reasoning": "str",
                    "affected_factors": ["str"],
                },
                system="你是 A 股事件影响评估专家。",
            )
            return EventImpact(
                event_desc=event_desc,
                impact=result.get("impact", "neutral"),
                magnitude=result.get("magnitude", "low"),
                reasoning=result.get("reasoning", ""),
                affected_factors=result.get("affected_factors", []),
            )
        except Exception as e:
            logger.warning(f"LLM 事件评估失败 [{code}]: {e}")
            return EventImpact(
                event_desc=event_desc,
                impact="neutral",
                magnitude="low",
                reasoning=f"LLM 评估失败: {e}",
                affected_factors=[],
            )
