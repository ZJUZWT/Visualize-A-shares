"""产业链引擎模块 — 行业认知/映射/资金构成"""

from __future__ import annotations

from .engine import IndustryEngine

_industry_engine: IndustryEngine | None = None


def get_industry_engine() -> IndustryEngine:
    """获取产业链引擎全局单例（依赖数据引擎，可选 LLM）"""
    global _industry_engine
    if _industry_engine is None:
        llm_provider = None
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            if llm_settings.api_key:
                llm_provider = LLMProviderFactory.create(llm_settings)
        except Exception:
            pass
        from engine.data import get_data_engine
        _industry_engine = IndustryEngine(
            data_engine=get_data_engine(),
            llm_provider=llm_provider,
        )
    return _industry_engine


__all__ = ["IndustryEngine", "get_industry_engine"]
