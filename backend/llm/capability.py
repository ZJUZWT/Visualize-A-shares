# engine/llm/capability.py
"""LLMCapability — 统一语义化 LLM 接口，内置 llm_cache"""

import hashlib
import json

from loguru import logger

from .providers import BaseLLMProvider, ChatMessage


class LLMCapability:
    """引擎可选的 LLM 能力 — 统一语义化接口，内置共享缓存

    用法:
        cap = LLMCapability(provider=llm_provider, cache_store=data_engine.store)
        result = await cap.classify("文本", ["positive", "negative", "neutral"])

    无 provider 时 enabled=False，所有方法静默降级，不抛异常。
    """

    def __init__(self, provider: BaseLLMProvider | None = None, cache_store=None):
        self._provider = provider      # None = 未配置，降级
        self._cache = cache_store      # DuckDBStore | None

    @property
    def enabled(self) -> bool:
        return self._provider is not None

    # ── 公开接口 ───────────────────────────────────────────

    async def complete(self, prompt: str, system: str = "", cache_key: str | None = None) -> str:
        """无状态文本补全（带可选缓存）— 使用流式收集保持链路活跃"""
        if not self.enabled:
            return ""
        key = cache_key or self._cache_key(prompt)
        cached = await self._get_cache(key)
        if cached is not None:
            return cached
        messages = []
        if system:
            messages.append(ChatMessage("system", system))
        messages.append(ChatMessage("user", prompt))
        try:
            # 流式收集：保持链路活跃，避免 wall-clock 超时
            chunks: list[str] = []
            async for token in self._provider.chat_stream(messages):
                chunks.append(token)
            result = "".join(chunks)
        except Exception as e:
            logger.warning(f"LLMCapability.complete 调用失败: {e}")
            return ""
        await self._set_cache(key, self._cache_key(prompt), result)
        return result

    async def classify(
        self,
        text: str,
        categories: list[str],
        system: str = "",
    ) -> dict:
        """分类任务，返回 {"label": <category>, "score": float, "reason": str}"""
        if not self.enabled:
            return {"label": categories[0], "score": 0.0, "reason": "llm_disabled"}

        key = self._cache_key(text, str(categories))
        cached = await self._get_cache(key)
        if cached is not None:
            try:
                return json.loads(cached)
            except Exception:
                pass

        cats_str = str(categories)
        prompt = (
            f"请对以下文本进行分类，从 {cats_str} 中选择最合适的类别。\n\n"
            f"文本：{text}\n\n"
            f'请严格输出 JSON（不含 markdown 代码块）：\n'
            f'{{"label": "<类别>", "score": <0.0-1.0置信度>, "reason": "<简短理由>"}}'
        )
        raw = await self.complete(prompt, system=system, cache_key=key)
        result = self._parse_json(raw)
        if result is None:
            return {"label": categories[0], "score": 0.0, "reason": "parse_error"}

        if result.get("label") not in categories:
            result["label"] = categories[0]

        await self._set_cache(key, self._cache_key(text, str(categories)), json.dumps(result, ensure_ascii=False))
        return result

    async def extract(
        self,
        text: str,
        schema: dict,
        system: str = "",
    ) -> dict:
        """结构化提取，返回符合 schema 描述的 dict"""
        if not self.enabled:
            return {}

        key = self._cache_key(text, str(schema))
        cached = await self._get_cache(key)
        if cached is not None:
            try:
                return json.loads(cached)
            except Exception:
                pass

        schema_str = json.dumps(schema, ensure_ascii=False)
        prompt = (
            f"请从以下文本中提取结构化信息。\n\n"
            f"文本：{text}\n\n"
            f"请严格按照以下 JSON schema 输出（不含 markdown 代码块）：\n{schema_str}"
        )
        raw = await self.complete(prompt, system=system, cache_key=key)
        result = self._parse_json(raw)
        if result is None:
            return {}

        await self._set_cache(key, self._cache_key(text, str(schema)), json.dumps(result, ensure_ascii=False))
        return result

    # ── 内部工具 ───────────────────────────────────────────

    def _cache_key(self, *parts: str) -> str:
        """生成缓存 key（SHA256 前 16 位）"""
        raw = "||".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _parse_json(self, text: str) -> dict | None:
        """从 LLM 输出中提取 JSON，支持 markdown 代码块包裹"""
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        try:
            return json.loads(text.strip())
        except Exception:
            return None

    async def _get_cache(self, key: str) -> str | None:
        """查询 DuckDBStore.get_llm_cache，cache_store=None 时返回 None"""
        if self._cache is None:
            return None
        try:
            return self._cache.get_llm_cache(key)
        except Exception as e:
            logger.warning(f"llm_cache 查询异常: {e}")
            return None

    async def _set_cache(self, key: str, prompt_hash: str, result_json: str) -> None:
        """写入 DuckDBStore.set_llm_cache，失败时只记录 warning"""
        if self._cache is None:
            return
        try:
            model = getattr(self._provider, "config", None)
            model_name = getattr(model, "model", "") if model else ""
            if not isinstance(model_name, str):
                model_name = ""
            self._cache.set_llm_cache(key, prompt_hash, result_json, model=model_name)
        except Exception as e:
            logger.warning(f"llm_cache 写入异常: {e}")
