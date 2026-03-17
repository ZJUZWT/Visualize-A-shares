"""信息引擎模块 — 新闻/公告/情感分析/事件评估"""

from .engine import InfoEngine
from engine.data import get_data_engine

_info_engine: InfoEngine | None = None


def get_info_engine() -> InfoEngine:
    """获取信息引擎全局单例（依赖数据引擎，可选 LLM）"""
    global _info_engine
    if _info_engine is None:
        llm_capability = None
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            from llm.capability import LLMCapability
            if llm_settings.api_key:
                provider = LLMProviderFactory.create(llm_settings)
                llm_capability = LLMCapability(
                    provider=provider,
                    cache_store=get_data_engine().store,
                )
        except Exception:
            pass
        _info_engine = InfoEngine(
            data_engine=get_data_engine(),
            llm_capability=llm_capability,
        )
    return _info_engine


__all__ = ["InfoEngine", "get_info_engine"]
