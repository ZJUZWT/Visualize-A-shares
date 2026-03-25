from __future__ import annotations

import re

from engine.expert.schemas import ToolCall

from .context import ExecutionContext


class ToolExecutionPlanner:
    """最小依赖规划器。"""

    def plan(
        self,
        tool_calls: list[ToolCall],
        *,
        context: ExecutionContext | None = None,
    ) -> list[list[ToolCall]]:
        if not tool_calls:
            return []

        has_data_expert = any(tc.engine == "expert" and tc.action == "data" for tc in tool_calls)
        has_quant_expert = any(tc.engine == "expert" and tc.action == "quant" for tc in tool_calls)

        if not has_data_expert or not has_quant_expert:
            return [tool_calls]

        if self._can_run_quant_with_data(tool_calls, context):
            return [tool_calls]

        phase1 = [tc for tc in tool_calls if not (tc.engine == "expert" and tc.action == "quant")]
        phase2 = [tc for tc in tool_calls if tc.engine == "expert" and tc.action == "quant"]
        phases = []
        if phase1:
            phases.append(phase1)
        if phase2:
            phases.append(phase2)
        return phases

    def _can_run_quant_with_data(
        self,
        tool_calls: list[ToolCall],
        context: ExecutionContext | None,
    ) -> bool:
        if context and (
            context.entities.stock_codes
            or context.prefetch.has_stock_context()
        ):
            return True

        for tc in tool_calls:
            code = str(tc.params.get("code", "")).strip()
            question = str(tc.params.get("question", ""))
            if re.search(r"(?<!\d)\d{6}(?!\d)", code) or re.search(r"(?<!\d)\d{6}(?!\d)", question):
                return True
        return False
