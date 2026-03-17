"""
LLM 聊天 API — SSE 流式对话接口

提供:
- POST /api/v1/chat          — 流式对话 (SSE)
- POST /api/v1/chat/sync     — 同步对话
- GET  /api/v1/chat/config   — 获取当前 LLM 配置状态
- POST /api/v1/chat/config   — 更新 LLM 配置
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from api.schemas import ChatRequest, ChatResponse, LLMConfigRequest, LLMConfigResponse
from llm.config import LLMConfig, llm_settings
from llm.providers import LLMProviderFactory, ChatMessage
from llm.context import build_market_context

router = APIRouter(prefix="/api/v1", tags=["chat"])

# 运行时可动态更新的配置
_runtime_config: LLMConfig = llm_settings.model_copy()


def _get_current_config() -> LLMConfig:
    return _runtime_config


def _build_messages(req: ChatRequest, config: LLMConfig) -> list[ChatMessage]:
    """构建完整消息列表（含 system prompt + 市场上下文）"""
    messages: list[ChatMessage] = []

    # 1. System prompt + 上下文注入
    context_str = build_market_context(
        terrain_summary=req.terrain_summary,
        selected_stock=req.selected_stock,
        cluster_info=req.cluster_info,
    )
    system_content = f"{config.system_prompt}\n\n---\n\n{context_str}"
    messages.append(ChatMessage("system", system_content))

    # 2. 历史对话
    if req.history:
        for msg in req.history:
            messages.append(ChatMessage(msg["role"], msg["content"]))

    # 3. 当前用户消息
    messages.append(ChatMessage("user", req.message))

    return messages


@router.post("/chat")
async def chat_stream(req: ChatRequest):
    """
    流式对话 — SSE

    SSE 事件类型：
    - token: { content: "..." }        逐 token 推送
    - done: { full_content: "..." }    完成，附完整内容
    - error: { message: "..." }         错误
    """
    config = _get_current_config()

    # 允许请求级别覆盖配置
    effective_config = config.model_copy()
    if req.override_config:
        oc = req.override_config
        if oc.get("provider"):
            effective_config.provider = oc["provider"]
        if oc.get("api_key"):
            effective_config.api_key = oc["api_key"]
        if oc.get("base_url"):
            effective_config.base_url = oc["base_url"]
        if oc.get("model"):
            effective_config.model = oc["model"]
        if oc.get("temperature") is not None:
            effective_config.temperature = oc["temperature"]
        if oc.get("max_tokens") is not None:
            effective_config.max_tokens = oc["max_tokens"]

    if not effective_config.api_key:
        raise HTTPException(
            status_code=400,
            detail="未配置 LLM API Key。请在设置中填写 API Key。"
        )

    messages = _build_messages(req, effective_config)
    provider = LLMProviderFactory.create(effective_config)

    async def event_stream():
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        full_content = ""
        try:
            async for token in provider.chat_stream(messages):
                full_content += token
                yield sse("token", {"content": token})

            yield sse("done", {"full_content": full_content})

        except Exception as e:
            logger.error(f"❌ LLM 流式对话失败: {e}", exc_info=True)
            error_msg = _friendly_error(e)
            yield sse("error", {"message": error_msg})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(req: ChatRequest):
    """同步对话 — 一次性返回完整响应"""
    config = _get_current_config()

    effective_config = config.model_copy()
    if req.override_config:
        oc = req.override_config
        if oc.get("provider"):
            effective_config.provider = oc["provider"]
        if oc.get("api_key"):
            effective_config.api_key = oc["api_key"]
        if oc.get("base_url"):
            effective_config.base_url = oc["base_url"]
        if oc.get("model"):
            effective_config.model = oc["model"]

    if not effective_config.api_key:
        raise HTTPException(
            status_code=400,
            detail="未配置 LLM API Key。请在设置中填写 API Key。"
        )

    messages = _build_messages(req, effective_config)
    provider = LLMProviderFactory.create(effective_config)

    try:
        content = await provider.chat(messages)
        return ChatResponse(content=content, model=effective_config.model)
    except Exception as e:
        logger.error(f"❌ LLM 同步对话失败: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=_friendly_error(e))


@router.get("/chat/config", response_model=LLMConfigResponse)
async def get_llm_config():
    """获取当前 LLM 配置（隐藏 API Key）"""
    config = _get_current_config()
    return LLMConfigResponse(
        enabled=bool(config.api_key),
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        has_api_key=bool(config.api_key),
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )


@router.post("/chat/config", response_model=LLMConfigResponse)
async def update_llm_config(req: LLMConfigRequest):
    """动态更新 LLM 配置（同时持久化到 .env 文件）"""
    global _runtime_config

    config_dict = _runtime_config.model_dump()
    if req.provider is not None:
        config_dict["provider"] = req.provider
    if req.api_key is not None:
        config_dict["api_key"] = req.api_key
    if req.base_url is not None:
        config_dict["base_url"] = req.base_url
    if req.model is not None:
        config_dict["model"] = req.model
    if req.temperature is not None:
        config_dict["temperature"] = req.temperature
    if req.max_tokens is not None:
        config_dict["max_tokens"] = req.max_tokens

    config_dict["enabled"] = True
    _runtime_config = LLMConfig(**config_dict)

    logger.info(
        f"🤖 LLM 配置已更新: provider={_runtime_config.provider}, "
        f"model={_runtime_config.model}, base_url={_runtime_config.base_url}"
    )

    # 持久化到 .env 文件（后端重启不丢失）
    _persist_config_to_env(_runtime_config)

    return LLMConfigResponse(
        enabled=bool(_runtime_config.api_key),
        provider=_runtime_config.provider,
        base_url=_runtime_config.base_url,
        model=_runtime_config.model,
        has_api_key=bool(_runtime_config.api_key),
        temperature=_runtime_config.temperature,
        max_tokens=_runtime_config.max_tokens,
    )


def _persist_config_to_env(config: LLMConfig) -> None:
    """将 LLM 配置持久化到项目根目录 .env 文件"""
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"

    # 读取现有 .env 内容（如果有）
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text().splitlines()

    # 需要写入的 LLM 配置键值对
    llm_vars = {
        "LLM_ENABLED": "true" if config.api_key else "false",
        "LLM_PROVIDER": config.provider,
        "LLM_API_KEY": config.api_key,
        "LLM_BASE_URL": config.base_url,
        "LLM_MODEL": config.model,
        "LLM_TEMPERATURE": str(config.temperature),
        "LLM_MAX_TOKENS": str(config.max_tokens),
    }

    # 更新已有行 或 追加
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in llm_vars:
                new_lines.append(f"{key}={llm_vars[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # 追加缺失的键
    missing_keys = set(llm_vars.keys()) - updated_keys
    if missing_keys:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("# ─── LLM 配置（由 UI 自动生成） ───")
        for key in ["LLM_ENABLED", "LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_TEMPERATURE", "LLM_MAX_TOKENS"]:
            if key in missing_keys:
                new_lines.append(f"{key}={llm_vars[key]}")

    try:
        env_path.write_text("\n".join(new_lines) + "\n")
        logger.info(f"💾 LLM 配置已持久化到 {env_path}")
    except Exception as e:
        logger.warning(f"⚠️ 持久化 .env 失败: {e}")


def _friendly_error(e: Exception) -> str:
    """将异常转为用户友好的错误信息"""
    msg = str(e)
    if "401" in msg or "Unauthorized" in msg:
        return "API Key 无效或已过期，请检查配置"
    if "403" in msg or "Forbidden" in msg:
        return "API Key 无权访问该模型，请检查权限"
    if "429" in msg or "rate" in msg.lower():
        return "请求过于频繁，请稍后重试"
    if "timeout" in msg.lower():
        return "请求超时，请检查网络或稍后重试"
    if "connection" in msg.lower() or "connect" in msg.lower():
        return "无法连接到 LLM 服务，请检查 Base URL 和网络"
    if "model" in msg.lower() and "not found" in msg.lower():
        return f"模型不存在，请检查模型名称是否正确"
    return f"LLM 调用失败: {msg[:200]}"
