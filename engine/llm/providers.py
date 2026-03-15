"""
LLM Provider 统一抽象层

架构设计：
- BaseLLMProvider: 抽象基类，定义统一接口
- OpenAICompatibleProvider: 覆盖 90%+ 厂商（OpenAI/DeepSeek/Qwen/Kimi/GLM/百川等）
- AnthropicProvider: Claude 系列
- LLMProviderFactory: 根据配置自动选择 Provider

所有 Provider 都支持：
1. 同步对话: chat()
2. 流式对话: chat_stream()  (SSE 流式输出)
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator

import httpx
from loguru import logger

from .config import LLMConfig


# ─── 消息格式 ────────────────────────────────────────
class ChatMessage:
    """统一消息格式"""

    def __init__(self, role: str, content: str):
        self.role = role      # "system" | "user" | "assistant"
        self.content = content

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


# ─── 抽象基类 ────────────────────────────────────────
class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def chat(self, messages: list[ChatMessage]) -> str:
        """同步对话，返回完整响应"""
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        """流式对话，逐 token 返回"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """检查连接是否正常"""
        ...


# ─── OpenAI 兼容 Provider ────────────────────────────
class OpenAICompatibleProvider(BaseLLMProvider):
    """
    OpenAI 兼容格式 Provider

    适用厂商（仅需更换 base_url）：
    - OpenAI:     https://api.openai.com/v1
    - DeepSeek:   https://api.deepseek.com/v1
    - 通义千问:    https://dashscope.aliyuncs.com/compatible-mode/v1
    - Kimi:       https://api.moonshot.cn/v1
    - 智谱GLM:    https://open.bigmodel.cn/api/paas/v4
    - 百川:       https://api.baichuan-ai.com/v1
    - 零一万物:    https://api.lingyiwanwu.com/v1
    - Groq:       https://api.groq.com/openai/v1
    - Together:   https://api.together.xyz/v1
    """

    async def chat(self, messages: list[ChatMessage]) -> str:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    async def health_check(self) -> bool:
        try:
            url = f"{self.config.base_url.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {self.config.api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")
            return False


# ─── Anthropic Provider ──────────────────────────────
class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude 系列 Provider

    使用 Messages API 格式（与 OpenAI 不兼容）
    API: https://api.anthropic.com/v1/messages
    """

    ANTHROPIC_VERSION = "2023-06-01"

    async def chat(self, messages: list[ChatMessage]) -> str:
        url = f"{self.config.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        # Anthropic 格式：system 独立，messages 只含 user/assistant
        system_text = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_text = m.content
            else:
                api_messages.append(m.to_dict())

        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": api_messages,
        }
        if system_text:
            payload["system"] = system_text

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Anthropic 返回格式: { content: [{ type: "text", text: "..." }] }
            return data["content"][0]["text"]

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        url = f"{self.config.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        system_text = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_text = m.content
            else:
                api_messages.append(m.to_dict())

        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": api_messages,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str:
                        continue
                    try:
                        import json
                        event = json.loads(data_str)
                        # Anthropic SSE: content_block_delta 事件
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue

    async def health_check(self) -> bool:
        """Anthropic 没有 /models 端点，发一个极短请求测试"""
        try:
            result = await self.chat([
                ChatMessage("user", "hi")
            ])
            return bool(result)
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return False


# ─── Provider 工厂 ────────────────────────────────────
class LLMProviderFactory:
    """根据配置创建对应的 LLM Provider"""

    _providers = {
        "openai_compatible": OpenAICompatibleProvider,
        "anthropic": AnthropicProvider,
    }

    @classmethod
    def create(cls, config: LLMConfig) -> BaseLLMProvider:
        provider_class = cls._providers.get(config.provider)
        if not provider_class:
            raise ValueError(
                f"不支持的 Provider: {config.provider}。"
                f"可选值: {', '.join(cls._providers.keys())}"
            )
        return provider_class(config)

    @classmethod
    def create_from_override(
        cls,
        base_config: LLMConfig,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> BaseLLMProvider:
        """允许在请求级别覆盖配置"""
        config_dict = base_config.model_dump()
        if provider is not None:
            config_dict["provider"] = provider
        if api_key is not None:
            config_dict["api_key"] = api_key
        if base_url is not None:
            config_dict["base_url"] = base_url
        if model is not None:
            config_dict["model"] = model
        if temperature is not None:
            config_dict["temperature"] = temperature
        if max_tokens is not None:
            config_dict["max_tokens"] = max_tokens

        config = LLMConfig(**config_dict)
        return cls.create(config)
