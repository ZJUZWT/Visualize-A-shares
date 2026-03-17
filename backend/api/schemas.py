"""
API 数据模型 (Pydantic Schemas) — LLM 聊天部分

仅保留 LLM Chat 相关的数据契约。
地形/聚类相关 schemas 已迁移到 cluster_engine.schemas。
"""

from pydantic import BaseModel, Field


# ─── LLM Chat Schemas ─────────────────────────────────

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., min_length=1, max_length=4096, description="用户消息")
    history: list[dict] = Field(
        default_factory=list,
        description='对话历史 [{"role": "user"|"assistant", "content": "..."}]'
    )

    # 上下文注入（前端自动填充当前地形数据）
    terrain_summary: dict | None = Field(None, description="地形概览数据")
    selected_stock: dict | None = Field(None, description="当前选中的股票")
    cluster_info: dict | None = Field(None, description="当前聚类信息")

    # 允许在请求级别覆盖 LLM 配置
    override_config: dict | None = Field(
        None,
        description="覆盖 LLM 配置 {provider, api_key, base_url, model, temperature, max_tokens}"
    )


class ChatResponse(BaseModel):
    """聊天同步响应"""
    content: str = Field(..., description="AI 回复内容")
    model: str = Field("", description="使用的模型")


class LLMConfigRequest(BaseModel):
    """LLM 配置更新请求"""
    provider: str | None = Field(None, description="openai_compatible | anthropic")
    api_key: str | None = Field(None, description="API Key")
    base_url: str | None = Field(None, description="API Base URL")
    model: str | None = Field(None, description="模型名称")
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=64, le=32768)


class LLMConfigResponse(BaseModel):
    """LLM 配置状态响应"""
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    model: str = ""
    has_api_key: bool = False
    temperature: float = 0.7
    max_tokens: int = 2048
