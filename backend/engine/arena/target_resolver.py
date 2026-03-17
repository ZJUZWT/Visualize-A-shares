# engine/agent/target_resolver.py
"""Target 类型解析器 — 将辩论标的识别为 stock / sector / macro"""

import re
from dataclasses import dataclass

from loguru import logger


@dataclass
class TargetResolution:
    """解析结果"""
    target_type: str   # "stock" | "sector" | "macro"
    resolved_code: str = ""    # 仅 stock 时有值
    sector_name: str = ""      # 仅 sector 时有值
    display_name: str = ""     # prompt 展示名


class TargetResolver:
    """三级识别：规则 → 行业匹配 → LLM 分类"""

    def __init__(self, llm=None):
        self._llm = llm  # BaseLLMProvider | None

    def _get_industry_set(self) -> set[str]:
        """从 DataEngine profiles 获取所有行业名"""
        try:
            from engine.data import get_data_engine
            profiles = get_data_engine().get_profiles()
            return {
                info.get("industry", "")
                for info in profiles.values()
                if info.get("industry")
            }
        except Exception as e:
            logger.warning(f"获取行业列表失败: {e}")
            return set()

    def _resolve_by_rules(self, target: str) -> TargetResolution | None:
        """规则识别，返回 None 表示规则无法判断"""
        stripped = target.strip()

        # 1. 6位数字 → stock
        if re.fullmatch(r"\d{6}", stripped):
            return TargetResolution(
                target_type="stock",
                resolved_code=stripped,
                display_name=self._get_stock_name(stripped) or stripped,
            )

        # 2. 行业列表精确/子串匹配 → sector
        industries = self._get_industry_set()
        # 精确匹配优先
        if stripped in industries:
            return TargetResolution(
                target_type="sector",
                sector_name=stripped,
                display_name=stripped,
            )
        # 子串匹配：target 是某行业名的子串，或某行业名是 target 的子串
        for ind in industries:
            if stripped in ind or ind in stripped:
                return TargetResolution(
                    target_type="sector",
                    sector_name=ind,
                    display_name=ind,
                )

        return None

    def _get_stock_name(self, code: str) -> str:
        """从 profiles 获取股票名称"""
        try:
            from engine.data import get_data_engine
            profile = get_data_engine().get_profile(code)
            return profile.get("name", "") if profile else ""
        except Exception:
            return ""

    async def resolve(self, target: str) -> TargetResolution:
        """完整解析流程"""
        # 1. 规则识别
        result = self._resolve_by_rules(target)
        if result:
            logger.info(f"TargetResolver 规则识别: '{target}' → {result.target_type}")
            return result

        # 2. LLM 分类（如果可用）
        if self._llm:
            result = await self._resolve_by_llm(target)
            if result:
                return result

        # 3. fallback → macro
        logger.info(f"TargetResolver fallback: '{target}' → macro")
        return TargetResolution(
            target_type="macro",
            display_name=target,
        )

    async def _resolve_by_llm(self, target: str) -> TargetResolution | None:
        """LLM 分类 fallback（非流式，approved exception）"""
        prompt = f"判断以下辩论题目属于哪类：股票/板块/宏观主题，只输出一个词。题目：{target}"
        try:
            from llm.providers import ChatMessage
            response = await self._llm.chat(
                [ChatMessage(role="user", content=prompt)]
            )
            category = response.strip()
            logger.info(f"TargetResolver LLM 分类: '{target}' → '{category}'")

            if "股票" in category:
                # 尝试解析股票代码
                code = self._resolve_stock_code(target)
                if code:
                    return TargetResolution(
                        target_type="stock",
                        resolved_code=code,
                        display_name=self._get_stock_name(code) or target,
                    )
                # 解析失败 → 交给外层 fallback
                return None

            if "板块" in category:
                return TargetResolution(
                    target_type="sector",
                    sector_name=target,
                    display_name=target,
                )

            if "宏观" in category:
                return TargetResolution(
                    target_type="macro",
                    display_name=target,
                )

            return None  # 无法识别，交给外层 fallback

        except Exception as e:
            logger.warning(f"TargetResolver LLM 分类失败: {e}")
            return None

    def _resolve_stock_code(self, target: str) -> str:
        """复用现有 resolve_stock_code 逻辑"""
        try:
            from engine.data import get_data_engine
            profiles = get_data_engine().get_profiles()
            target_lower = target.lower()
            for code, info in profiles.items():
                name = info.get("name", "")
                if name and (name in target or target_lower in name.lower()):
                    return code
        except Exception as e:
            logger.warning(f"_resolve_stock_code 失败: {e}")
        return ""
