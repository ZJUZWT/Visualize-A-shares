"""Agent 编排层 — Multi-Agent 智能投研决策大脑"""

from .orchestrator import Orchestrator
from .data_fetcher import DataFetcher
from .memory import AgentMemory

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """获取 Orchestrator 全局单例"""
    global _orchestrator
    if _orchestrator is None:
        from llm.config import llm_settings
        from llm.providers import LLMProviderFactory
        from llm.capability import LLMCapability
        from config import settings
        from data_engine import get_data_engine
        from rag import get_rag_store
        de = get_data_engine()
        provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None
        llm_cap = LLMCapability(provider=provider, cache_store=de.store)
        memory = AgentMemory(persist_dir=settings.chromadb.persist_dir)
        _orchestrator = Orchestrator(
            llm_capability=llm_cap,
            memory=memory,
            rag_store=get_rag_store(),
        )
    return _orchestrator


__all__ = ["Orchestrator", "DataFetcher", "AgentMemory", "get_orchestrator"]
