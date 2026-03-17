"""上下文窗口守卫 — 借鉴 OpenClaw 多级溢出保护机制

在 LLM 调用前估算 token 数，如超出预算则分级截断，防止 API 400 错误。
"""

from __future__ import annotations

from loguru import logger


class ContextGuard:
    """上下文窗口守卫

    三级保护策略：
    - Level 1: 截断早期对话历史（保留最近 5 轮 = 10 条消息）
    - Level 2: 如果仍超，进一步减少历史至 2 轮（4 条消息）
    - Level 3: 如果仍超，只保留 system + 最新 user（无历史）

    永远不截断 system prompt 和最新 user 消息的内容。
    """

    def __init__(self, max_input_tokens: int = 28000):
        self.max_input_tokens = max_input_tokens

    def estimate_tokens(self, text: str) -> int:
        """快速估算 token 数

        中文字符 ≈ 0.7 token/字，非中文字符 ≈ 0.25 token/字。
        这是经验公式，误差 ±20%，足够用于预算控制。
        """
        if not text:
            return 0
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - cn_chars
        return int(cn_chars * 0.7 + other_chars * 0.25)

    def _total_tokens(self, messages: list[dict]) -> int:
        """估算消息列表的总 token 数"""
        return sum(self.estimate_tokens(m.get("content", "")) for m in messages)

    def guard_messages(self, messages: list[dict]) -> list[dict]:
        """三级保护，返回可能被截断的消息列表（新列表，不修改原始）

        消息格式: [{"role": "system"|"user"|"assistant", "content": "..."}]

        保证：
        1. 第一条 system 消息永远保留
        2. 最后一条 user 消息永远保留
        3. 中间的对话历史按级别递进截断
        """
        total = self._total_tokens(messages)

        if total <= self.max_input_tokens:
            return list(messages)  # 安全，返回浅拷贝

        # 识别固定部分（system + 最新 user）和可截断的历史
        system_msg = messages[0] if messages and messages[0]["role"] == "system" else None
        last_user_msg = messages[-1] if messages and messages[-1]["role"] == "user" else None

        # 中间的历史消息
        history_start = 1 if system_msg else 0
        history_end = len(messages) - 1 if last_user_msg else len(messages)
        history = messages[history_start:history_end]

        fixed_tokens = 0
        if system_msg:
            fixed_tokens += self.estimate_tokens(system_msg.get("content", ""))
        if last_user_msg:
            fixed_tokens += self.estimate_tokens(last_user_msg.get("content", ""))

        budget_for_history = self.max_input_tokens - fixed_tokens

        # Level 1: 保留最近 5 轮（10 条消息）
        if len(history) > 10:
            history = history[-10:]
            if self._total_tokens(history) <= budget_for_history:
                result = self._assemble(system_msg, history, last_user_msg)
                logger.info(f"⚠️ ContextGuard Level 1: 截断历史到最近5轮 "
                            f"({total}→{self._total_tokens(result)} tokens)")
                return result

        # Level 2: 保留最近 2 轮（4 条消息）
        if len(history) > 4:
            history = history[-4:]
            if self._total_tokens(history) <= budget_for_history:
                result = self._assemble(system_msg, history, last_user_msg)
                logger.warning(f"⚠️ ContextGuard Level 2: 截断历史到最近2轮 "
                               f"({total}→{self._total_tokens(result)} tokens)")
                return result

        # Level 3: 清空全部历史
        result = self._assemble(system_msg, [], last_user_msg)
        logger.warning(f"⚠️ ContextGuard Level 3: 清空全部历史 "
                       f"({total}→{self._total_tokens(result)} tokens)")
        return result

    @staticmethod
    def _assemble(
        system_msg: dict | None,
        history: list[dict],
        last_user_msg: dict | None,
    ) -> list[dict]:
        result = []
        if system_msg:
            result.append(system_msg)
        result.extend(history)
        if last_user_msg:
            result.append(last_user_msg)
        return result
