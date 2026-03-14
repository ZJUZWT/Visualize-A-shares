"""Agent Runner — 单个 Agent 的 LLM 调用逻辑"""

import json
import re

from loguru import logger

from llm.capability import LLMCapability
from .schemas import AgentVerdict
from .personas import build_system_prompt


class AgentRunError(Exception):
    """Agent 运行错误"""
    pass


def _extract_json(text: str) -> str:
    """从 LLM 输出中提取 JSON（处理 markdown 代码块包裹）"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


async def run_agent(
    agent_role: str,
    target: str,
    data_context: dict,
    memory_context: list[dict],
    calibration_weight: float,
    llm_capability: LLMCapability,
) -> AgentVerdict:
    """执行单个 Agent 分析

    Args:
        agent_role: fundamental / info / quant
        target: 股票代码
        data_context: 该 Agent 可见的数据
        memory_context: 该 Agent 的历史推理记忆
        calibration_weight: 当前校准权重
        llm_provider: LLM 调用实例

    Returns:
        AgentVerdict

    Raises:
        AgentRunError: LLM 返回无法解析的内容
    """
    system_prompt = build_system_prompt(agent_role, calibration_weight)
    user_msg = f"请分析股票 {target}。\n\n## 数据\n```json\n{json.dumps(data_context, ensure_ascii=False, indent=2)}\n```"

    if memory_context:
        memory_text = "\n".join(
            f"- [{m.get('metadata', {}).get('timestamp', '?')}] {m.get('content', '')}"
            for m in memory_context[:5]
        )
        user_msg += f"\n\n## 历史分析记忆\n{memory_text}"

    try:
        raw = await llm_capability.complete(prompt=user_msg, system=system_prompt)
    except Exception as e:
        raise AgentRunError(f"LLM 调用失败 [{agent_role}]: {e}") from e

    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Agent [{agent_role}] 返回非 JSON: {raw[:200]}")
        raise AgentRunError(f"JSON 解析失败 [{agent_role}]: {e}") from e

    data["agent_role"] = agent_role

    try:
        return AgentVerdict(**data)
    except Exception as e:
        raise AgentRunError(f"Verdict 校验失败 [{agent_role}]: {e}") from e
