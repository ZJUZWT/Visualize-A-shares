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
        from config import settings

        if not llm_settings.api_key:
            raise RuntimeError("LLM API Key 未配置。请设置环境变量 LLM_API_KEY 或在 .env 中配置。")

        provider = LLMProviderFactory.create(llm_settings)
        memory = AgentMemory(persist_dir=settings.chromadb.persist_dir)
        _orchestrator = Orchestrator(llm_provider=provider, memory=memory)
    return _orchestrator


__all__ = ["Orchestrator", "DataFetcher", "AgentMemory", "get_orchestrator"]
