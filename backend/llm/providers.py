"""
LLM Provider 统一抽象层

架构设计：
- BaseLLMProvider: 抽象基类，定义统一接口
- OpenAICompatibleProvider: 覆盖 90%+ 厂商（OpenAI/DeepSeek/Qwen/Kimi/GLM/百川等）
  - 自动探测 Responses API (/v1/responses) → 不支持则降级 Chat Completions (/v1/chat/completions)
- AnthropicProvider: Claude 系列
- LLMProviderFactory: 根据配置自动选择 Provider
"""

from abc import ABC, abstractmethod
import json as _json
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

import httpx
from loguru import logger

from .config import LLMConfig


# ─── 消息格式 ────────────────────────────────────────
class ChatMessage:
    """统一消息格式 — 支持纯文本和 tool_calls / tool 结果"""

    def __init__(
        self,
        role: str,
        content: str = "",
        *,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ):
        self.role = role      # "system" | "user" | "assistant" | "tool"
        self.content = content
        self.tool_calls = tool_calls      # assistant 消息中 LLM 返回的工具调用
        self.tool_call_id = tool_call_id  # tool 消息中对应的 tool_call id
        self.name = name                  # tool 消息中的函数名

    def to_dict(self) -> dict:
        d: dict = {"role": self.role}
        if self.content:
            d["content"] = self.content
        elif self.role != "assistant":
            # 非 assistant 角色需要 content 字段
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class ToolCallResult:
    """原生 Tool Use 的返回结构"""
    content: str = ""                              # LLM 的文本回复（可能为空）
    tool_calls: list[dict] = field(default_factory=list)  # [{id, type, function: {name, arguments}}]
    raw_message: dict = field(default_factory=dict)       # 完整的 assistant message（用于多轮对话）


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

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
    ) -> ToolCallResult:
        """带工具定义的对话 — 原生 Function Calling

        子类可覆盖。默认实现抛 NotImplementedError，
        调用方应先检查 supports_tool_use 属性。
        """
        raise NotImplementedError(f"{self.__class__.__name__} 不支持原生 tool use")

    @property
    def supports_tool_use(self) -> bool:
        """是否支持原生 Function Calling / Tool Use"""
        return False


# ─── OpenAI 兼容 Provider ────────────────────────────
class OpenAICompatibleProvider(BaseLLMProvider):
    """
    OpenAI 兼容格式 Provider — 自动探测 Responses API 降级

    优先尝试 Responses API (/v1/responses)，
    收到 404/405/501 时自动降级到 Chat Completions (/v1/chat/completions)。
    探测结果按 base_url 缓存，同一地址不重复试。

    适用厂商（仅需更换 base_url）：
    - OpenAI:     https://api.openai.com/v1      ← 支持 Responses API
    - DeepSeek:   https://api.deepseek.com/v1    ← 仅 Chat Completions
    - 通义千问:    https://dashscope.aliyuncs.com/compatible-mode/v1
    - Kimi:       https://api.moonshot.cn/v1
    - 智谱GLM:    https://open.bigmodel.cn/api/paas/v4
    - 百川:       https://api.baichuan-ai.com/v1
    - 零一万物:    https://api.lingyiwanwu.com/v1
    - Groq:       https://api.groq.com/openai/v1
    - Together:   https://api.together.xyz/v1
    """

    # 长任务（产业链推演等）需要更长超时，思考型模型首 token 可能延迟 30s+
    _TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)

    # ── 类级别缓存：base_url → True(支持 Responses) / False(不支持) ──
    # None 表示尚未探测
    _responses_api_support: dict[str, bool] = {}

    # ── 格式转换：ChatMessage[] → Responses API 的 input + instructions ──

    @staticmethod
    def _messages_to_responses_format(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
        """将 ChatMessage 列表转换为 Responses API 格式

        Returns:
            (instructions, input_items)
            - instructions: system prompt 内容（Responses API 用 instructions 代替 system role）
            - input_items: input 数组，每项是 {"role": "user"|"assistant"|"developer", "content": "..."}
        """
        instructions = ""
        input_items: list[dict] = []

        for m in messages:
            if m.role == "system":
                # Responses API: system prompt → instructions 字段
                # 多个 system 消息拼合
                if instructions:
                    instructions += "\n\n"
                instructions += m.content
            elif m.role == "tool":
                # tool 结果 → function_call_output 格式
                input_items.append({
                    "type": "function_call_output",
                    "call_id": m.tool_call_id or "",
                    "output": m.content,
                })
            elif m.role == "assistant" and m.tool_calls:
                # assistant 的 tool_calls → 先加文本消息，再加 function_call items
                if m.content:
                    input_items.append({"role": "assistant", "content": m.content})
                for tc in m.tool_calls:
                    func = tc.get("function", {})
                    input_items.append({
                        "type": "function_call",
                        "id": tc.get("id", ""),
                        "call_id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "arguments": func.get("arguments", "{}"),
                    })
            else:
                input_items.append({"role": m.role, "content": m.content})

        return instructions, input_items

    @staticmethod
    def _extract_responses_text(data: dict) -> str:
        """从 Responses API 返回中提取文本内容

        Response format:
        {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "..."}]}
            ]
        }
        """
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content_part in item.get("content", []):
                    if content_part.get("type") == "output_text":
                        return content_part.get("text", "")
        # fallback: 有些返回直接有 output_text
        if "output_text" in data:
            return data["output_text"]
        return ""

    @staticmethod
    def _extract_responses_tool_calls(data: dict) -> list[dict]:
        """从 Responses API 返回中提取 tool_calls"""
        tool_calls = []
        for item in data.get("output", []):
            if item.get("type") == "function_call":
                tool_calls.append({
                    "id": item.get("call_id") or item.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                })
        return tool_calls

    def _should_try_responses(self) -> bool:
        """判断是否应该尝试 Responses API"""
        base = self.config.base_url.rstrip("/")
        cached = self._responses_api_support.get(base)
        if cached is False:
            return False  # 已确认不支持
        return True  # 未探测或已确认支持

    async def probe_responses_api(self) -> bool:
        """轻量探测 Responses API 是否可用（建议在启动时调用一次）

        发一个最小请求（max_output_tokens=1），看是否返回成功。
        超时设为 10s，避免阻塞启动。
        """
        base = self.config.base_url.rstrip("/")
        if base in self._responses_api_support:
            return self._responses_api_support[base]

        url = f"{base}/responses"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "input": "hi",
            "max_output_tokens": 1,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code in (401, 429):
                    # 鉴权/限流问题，不能判断是否支持，先乐观假设
                    logger.debug(f"Responses API 探测返回 {resp.status_code}，无法判断是否支持")
                    return True
                if resp.status_code == 200:
                    self._mark_responses_support(True)
                    return True
                else:
                    self._mark_responses_support(False)
                    return False
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.debug(f"Responses API 探测超时/连接失败: {e}")
            self._mark_responses_support(False)
            return False
        except Exception as e:
            logger.debug(f"Responses API 探测异常: {e}")
            self._mark_responses_support(False)
            return False

    def _mark_responses_support(self, supported: bool) -> None:
        """缓存探测结果"""
        base = self.config.base_url.rstrip("/")
        self._responses_api_support[base] = supported
        if supported:
            logger.info(f"✅ Responses API 可用: {base}")
        else:
            logger.info(f"⬇️ Responses API 不可用，降级 Chat Completions: {base}")

    def _should_fallback_to_completions(self, exc: Exception) -> bool:
        """判断异常是否应触发降级到 Chat Completions

        降级策略（宽松）：
        - 首次探测时，除 401(鉴权)/429(限流) 外的所有 HTTP 错误都降级
          （400/404/405/500/501/502/503 等都可能是"不支持该端点"的表现）
        - 已确认支持后，不再降级（此时错误应由调用方处理）
        - 超时/连接错误：首次探测时也降级（某些网关对未知路径直接挂住）
        """
        base = self.config.base_url.rstrip("/")
        already_confirmed = self._responses_api_support.get(base) is True
        if already_confirmed:
            return False  # 已确认支持，不降级

        if isinstance(exc, httpx.HTTPStatusError):
            # 401/429 是鉴权/限流问题，两套 API 都会有，不降级直接报错
            return exc.response.status_code not in (401, 429)
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
            # 超时或连接错误：首次探测时降级（有些网关对未知路径直接挂住）
            return True
        return False

    # ══════════════════════════════════════════════════
    # chat() — 非流式对话
    # ══════════════════════════════════════════════════

    async def chat(self, messages: list[ChatMessage]) -> str:
        if self._should_try_responses():
            try:
                return await self._chat_responses(messages)
            except Exception as e:
                if self._should_fallback_to_completions(e):
                    self._mark_responses_support(False)
                    return await self._chat_completions(messages)
                raise
        return await self._chat_completions(messages)

    async def _chat_responses(self, messages: list[ChatMessage]) -> str:
        """Responses API: POST /v1/responses"""
        t0 = time.monotonic()
        base = self.config.base_url.rstrip("/")
        url = f"{base}/responses"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        instructions, input_items = self._messages_to_responses_format(messages)
        payload: dict = {
            "model": self.config.model,
            "input": input_items,
            "temperature": self.config.temperature,
            "stream": False,
        }
        if self.config.max_tokens is not None:
            payload["max_output_tokens"] = self.config.max_tokens
        if instructions:
            payload["instructions"] = instructions

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # 首次成功，标记支持
        base_key = self.config.base_url.rstrip("/")
        if base_key not in self._responses_api_support:
            self._mark_responses_support(True)

        result = self._extract_responses_text(data)
        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ LLM chat/responses ({self.config.model}) 耗时 {elapsed:.1f}s, 响应长度 {len(result)} 字符")
        return result

    async def _chat_completions(self, messages: list[ChatMessage]) -> str:
        """Chat Completions API: POST /v1/chat/completions"""
        t0 = time.monotonic()
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.config.temperature,
            "stream": False,
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            result = data["choices"][0]["message"]["content"]
            elapsed = time.monotonic() - t0
            logger.info(f"⏱️ LLM chat/completions ({self.config.model}) 耗时 {elapsed:.1f}s, 响应长度 {len(result)} 字符")
            return result

    # ══════════════════════════════════════════════════
    # chat_stream() — 流式对话
    # ══════════════════════════════════════════════════

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        if self._should_try_responses():
            try:
                yielded = False
                async for token in self._chat_stream_responses(messages):
                    yielded = True
                    yield token
                if yielded:
                    return
                return
            except Exception as e:
                if self._should_fallback_to_completions(e):
                    self._mark_responses_support(False)
                    async for token in self._chat_stream_completions(messages):
                        yield token
                    return
                raise

        async for token in self._chat_stream_completions(messages):
            yield token

    async def _chat_stream_responses(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        """Responses API 流式: POST /v1/responses (stream=true)

        SSE 事件格式:
        - event: response.output_text.delta  data: {"delta": "文本片段", ...}
        - event: response.output_text.done   data: {"text": "完整文本", ...}
        - event: response.completed          data: {完整 response}
        """
        t0 = time.monotonic()
        token_count = 0
        base = self.config.base_url.rstrip("/")
        url = f"{base}/responses"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        instructions, input_items = self._messages_to_responses_format(messages)
        payload: dict = {
            "model": self.config.model,
            "input": input_items,
            "temperature": self.config.temperature,
            "stream": True,
        }
        if self.config.max_tokens is not None:
            payload["max_output_tokens"] = self.config.max_tokens
        if instructions:
            payload["instructions"] = instructions

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()

                    # 首次成功，标记支持
                    base_key = self.config.base_url.rstrip("/")
                    if base_key not in self._responses_api_support:
                        self._mark_responses_support(True)

                    # Responses API SSE 格式: "event: xxx\ndata: {...}\n\n"
                    current_event_type = ""
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("event: "):
                            current_event_type = line[7:].strip()
                            continue
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            import json
                            event_data = json.loads(data_str)

                            # 方式1: 通过 event type 判断
                            if current_event_type == "response.output_text.delta":
                                delta = event_data.get("delta", "")
                                if delta:
                                    token_count += 1
                                    yield delta
                            # 方式2: 通过 data 中的 type 字段判断（部分实现不发 event 行）
                            elif event_data.get("type") == "response.output_text.delta":
                                delta = event_data.get("delta", "")
                                if delta:
                                    token_count += 1
                                    yield delta

                        except (json.JSONDecodeError, KeyError):
                            continue
                        finally:
                            # 每个 data 行处理后重置 event type
                            current_event_type = ""
        finally:
            elapsed = time.monotonic() - t0
            logger.info(f"⏱️ LLM stream/responses ({self.config.model}) 耗时 {elapsed:.1f}s, {token_count} chunks")

    async def _chat_stream_completions(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        """Chat Completions API 流式: POST /v1/chat/completions (stream=true)"""
        t0 = time.monotonic()
        token_count = 0
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.config.temperature,
            "stream": True,
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
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
                                token_count += 1
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
        finally:
            elapsed = time.monotonic() - t0
            logger.info(f"⏱️ LLM stream/completions ({self.config.model}) 耗时 {elapsed:.1f}s, {token_count} chunks")

    # ══════════════════════════════════════════════════
    # chat_with_tools() — 工具调用
    # ══════════════════════════════════════════════════

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
    ) -> ToolCallResult:
        if self._should_try_responses():
            try:
                return await self._chat_with_tools_responses(messages, tools)
            except Exception as e:
                if self._should_fallback_to_completions(e):
                    self._mark_responses_support(False)
                    return await self._chat_with_tools_completions(messages, tools)
                raise
        return await self._chat_with_tools_completions(messages, tools)

    async def _chat_with_tools_responses(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
    ) -> ToolCallResult:
        """Responses API 工具调用"""
        t0 = time.monotonic()
        base = self.config.base_url.rstrip("/")
        url = f"{base}/responses"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        instructions, input_items = self._messages_to_responses_format(messages)
        payload: dict = {
            "model": self.config.model,
            "input": input_items,
            "temperature": self.config.temperature,
            "stream": False,
        }
        if self.config.max_tokens is not None:
            payload["max_output_tokens"] = self.config.max_tokens
        if instructions:
            payload["instructions"] = instructions
        if tools:
            # Responses API 的 tools 格式略有不同：type 直接用 "function"
            resp_tools = []
            for t in tools:
                if t.get("type") == "function":
                    func = t.get("function", {})
                    resp_tools.append({
                        "type": "function",
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "parameters": func.get("parameters", {}),
                    })
                else:
                    resp_tools.append(t)
            payload["tools"] = resp_tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # 首次成功，标记支持
        base_key = self.config.base_url.rstrip("/")
        if base_key not in self._responses_api_support:
            self._mark_responses_support(True)

        content = self._extract_responses_text(data)
        tool_calls = self._extract_responses_tool_calls(data)
        elapsed = time.monotonic() - t0

        logger.info(
            f"⏱️ LLM tools/responses ({self.config.model}) 耗时 {elapsed:.1f}s, "
            f"content={len(content)}字, tool_calls={len(tool_calls)}个"
        )

        # 构造兼容的 raw_message（方便多轮对话）
        raw_message: dict = {"role": "assistant"}
        if content:
            raw_message["content"] = content
        if tool_calls:
            raw_message["tool_calls"] = tool_calls

        return ToolCallResult(
            content=content,
            tool_calls=tool_calls,
            raw_message=raw_message,
        )

    async def _chat_with_tools_completions(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
    ) -> ToolCallResult:
        """Chat Completions API 工具调用"""
        t0 = time.monotonic()
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.config.temperature,
            "stream": False,
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""
        raw_tool_calls = msg.get("tool_calls") or []
        elapsed = time.monotonic() - t0

        # 标准化 tool_calls
        tool_calls = []
        for tc in raw_tool_calls:
            tool_calls.append({
                "id": tc.get("id", ""),
                "type": tc.get("type", "function"),
                "function": {
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", "{}"),
                },
            })

        logger.info(
            f"⏱️ LLM tools/completions ({self.config.model}) 耗时 {elapsed:.1f}s, "
            f"content={len(content)}字, tool_calls={len(tool_calls)}个"
        )
        return ToolCallResult(
            content=content,
            tool_calls=tool_calls,
            raw_message=msg,
        )

    @property
    def supports_tool_use(self) -> bool:
        return True

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
    _TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)

    async def chat(self, messages: list[ChatMessage]) -> str:
        t0 = time.monotonic()
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
            "max_tokens": self.config.max_tokens or 8192,
            "temperature": self.config.temperature,
            "messages": api_messages,
        }
        if system_text:
            payload["system"] = system_text

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Anthropic 返回格式: { content: [{ type: "text", text: "..." }] }
            result = data["content"][0]["text"]
            elapsed = time.monotonic() - t0
            logger.info(f"⏱️ LLM chat ({self.config.model}) 耗时 {elapsed:.1f}s, 响应长度 {len(result)} 字符")
            return result

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        t0 = time.monotonic()
        token_count = 0
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
            "max_tokens": self.config.max_tokens or 8192,
            "temperature": self.config.temperature,
            "messages": api_messages,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
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
                                    token_count += 1
                                    yield text
                        except (json.JSONDecodeError, KeyError):
                            continue
        finally:
            elapsed = time.monotonic() - t0
            logger.info(f"⏱️ LLM stream ({self.config.model}) 耗时 {elapsed:.1f}s, {token_count} chunks")

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


class ModelRouter:
    """为不同阶段提供 fast / quality 两档模型。"""

    def __init__(self, *, quality_provider: BaseLLMProvider | None, fast_provider: BaseLLMProvider | None = None):
        self._quality = quality_provider
        self._fast = fast_provider or quality_provider

    def get(self, tier: str = "quality") -> BaseLLMProvider | None:
        if tier == "fast":
            return self._fast
        return self._quality

    @classmethod
    def from_provider(cls, provider) -> "ModelRouter":
        if provider is None:
            return cls(quality_provider=None, fast_provider=None)
        config = getattr(provider, "config", None)
        if isinstance(config, LLMConfig):
            return cls.from_config(config)
        return cls(quality_provider=provider, fast_provider=provider)

    @classmethod
    def from_config(cls, config: LLMConfig) -> "ModelRouter":
        quality_provider = LLMProviderFactory.create(config)

        has_fast_override = any(
            value is not None and value != ""
            for value in (
                config.fast_provider,
                config.fast_api_key,
                config.fast_base_url,
                config.fast_model,
                config.fast_temperature,
                config.fast_max_tokens,
            )
        )
        if not has_fast_override:
            return cls(quality_provider=quality_provider, fast_provider=quality_provider)

        fast_provider = LLMProviderFactory.create_from_override(
            config,
            provider=config.fast_provider or config.provider,
            api_key=config.fast_api_key or config.api_key,
            base_url=config.fast_base_url or config.base_url,
            model=config.fast_model or config.model,
            temperature=config.fast_temperature if config.fast_temperature is not None else config.temperature,
            max_tokens=config.fast_max_tokens if config.fast_max_tokens is not None else config.max_tokens,
        )
        return cls(quality_provider=quality_provider, fast_provider=fast_provider)
