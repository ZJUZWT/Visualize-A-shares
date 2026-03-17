"""
StockScape LLM 模块 — 统一大模型抽象层

支持 OpenAI 兼容格式（覆盖 90%+ 厂商）和 Anthropic 格式
用户只需配置 base_url + api_key + model 即可切换任意厂商
"""

from .providers import LLMProviderFactory, BaseLLMProvider
from .config import LLMConfig, llm_settings

__all__ = ["LLMProviderFactory", "BaseLLMProvider", "LLMConfig", "llm_settings"]
