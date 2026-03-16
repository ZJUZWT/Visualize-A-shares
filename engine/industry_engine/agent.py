"""产业链 Agent — LLM 驱动的行业认知推理

职责：
1. 产业链结构推理（上下游、核心驱动、壁垒）
2. 供需格局分析
3. 周期定位
4. 认知陷阱生成
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from .schemas import IndustryCognition

# ── Prompt 模板 ──

INDUSTRY_COGNITION_PROMPT = """你是产业链分析专家。请基于你对 {industry} 行业的深度理解，生成以下结构化分析。
当前讨论标的：{target}（{stock_name}），时间基准：{as_of_date}。

请以 JSON 格式返回：
{{
  "upstream": ["上游环节1", "上游环节2"],
  "downstream": ["下游应用1", "下游应用2"],
  "core_drivers": ["核心驱动变量1 — 简要说明", "..."],
  "cost_structure": "成本结构描述（原材料占比、人工、能源等）",
  "barriers": "行业壁垒（资源、技术、资质、规模等）",
  "supply_demand": "当前供需格局分析（供给端变化、需求端趋势、库存状态）",
  "common_traps": [
    "认知陷阱1 — 表面逻辑 vs 实际逻辑",
    "认知陷阱2 — ..."
  ],
  "cycle_position": "景气上行 | 景气下行 | 拐点向上 | 拐点向下 | 高位震荡 | 底部盘整",
  "cycle_reasoning": "周期判断的具体依据",
  "catalysts": ["潜在催化剂1", "..."],
  "risks": ["关键风险1", "..."]
}}

要求：
- common_traps 是最关键的部分，必须列出该行业中投资者最容易犯的认知错误
- 每个陷阱要说明「表面逻辑」和「实际逻辑」的差异
- cycle_position 必须给出明确判断，不能模棱两可
- 所有分析基于 {as_of_date} 时点的行业状态"""


INDUSTRY_STANDALONE_PROMPT = """你是产业链分析专家。请基于你对 {industry} 行业的深度理解，生成以下结构化分析。
时间基准：{as_of_date}。

请以 JSON 格式返回：
{{
  "upstream": ["上游环节1", "上游环节2"],
  "downstream": ["下游应用1", "下游应用2"],
  "core_drivers": ["核心驱动变量1 — 简要说明", "..."],
  "cost_structure": "成本结构描述",
  "barriers": "行业壁垒",
  "supply_demand": "当前供需格局分析",
  "common_traps": ["认知陷阱1 — 表面逻辑 vs 实际逻辑", "..."],
  "cycle_position": "景气上行 | 景气下行 | 拐点向上 | 拐点向下 | 高位震荡 | 底部盘整",
  "cycle_reasoning": "周期判断的具体依据",
  "catalysts": ["潜在催化剂1", "..."],
  "risks": ["关键风险1", "..."]
}}

要求：
- common_traps 必须列出投资者最容易犯的认知错误，说明「表面逻辑」和「实际逻辑」
- cycle_position 必须给出明确判断
- 所有分析基于 {as_of_date} 时点"""


class IndustryAgent:
    """产业链推理 Agent"""

    def __init__(self, llm: BaseLLMProvider, store=None):
        self._llm = llm
        self._store = store

    async def generate_cognition(
        self,
        industry: str,
        target: str = "",
        as_of_date: str = "",
    ) -> IndustryCognition | None:
        """LLM 生成行业认知

        Args:
            industry: 行业名称
            target: 触发股票代码（可选，独立调用时为空）
            as_of_date: 时间锚点
        """
        if not as_of_date:
            as_of_date = datetime.now(tz=ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

        # 获取股票名称（如果有 target）
        stock_name = ""
        if target:
            try:
                from data_engine import get_data_engine
                profile = get_data_engine().get_profile(target)
                stock_name = profile.get("name", target) if profile else target
            except Exception:
                stock_name = target

        # 选择 prompt
        if target and stock_name:
            prompt = INDUSTRY_COGNITION_PROMPT.format(
                industry=industry,
                target=target,
                stock_name=stock_name,
                as_of_date=as_of_date,
            )
        else:
            prompt = INDUSTRY_STANDALONE_PROMPT.format(
                industry=industry,
                as_of_date=as_of_date,
            )

        try:
            # 流式收集完整响应
            chunks: list[str] = []
            async for token in self._llm.chat_stream(
                [ChatMessage(role="user", content=prompt)]
            ):
                chunks.append(token)
            raw = "".join(chunks)
            logger.debug(f"行业认知 LLM 原始返回 (前200字): {raw[:200] if raw else '(空)'}")

            parsed = _lenient_json_loads(raw)
            if not isinstance(parsed, dict):
                logger.warning(f"行业认知 LLM 返回非 dict: {type(parsed)}")
                return None

            cognition = IndustryCognition(
                industry=industry,
                target=target,
                generated_at=datetime.now(tz=ZoneInfo("Asia/Shanghai")).isoformat(),
                as_of_date=as_of_date,
                **{k: v for k, v in parsed.items() if k in IndustryCognition.model_fields},
            )
            logger.info(
                f"行业认知生成完成: {industry}, "
                f"周期={cognition.cycle_position}, "
                f"陷阱={len(cognition.common_traps)}条"
            )
            return cognition

        except Exception as e:
            logger.warning(f"行业认知生成失败: {type(e).__name__}: {e!r}")
            return None


# ── JSON 解析工具 ──

def _extract_json(text: str) -> str:
    """从 LLM 输出提取 JSON"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    result = match.group(1).strip() if match else text.strip()
    result = result.replace("\u201c", '"').replace("\u201d", '"')
    result = result.replace("\u2018", "'").replace("\u2019", "'")
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)
    return result


def _lenient_json_loads(text: str) -> dict | list:
    """宽松 JSON 解析"""
    raw = _extract_json(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    fixed2 = fixed.replace("'", '"')
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass
    m = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[.*\])', fixed, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("宽松解析也失败", raw, 0)
