"""
LLM 配置管理

支持三种配置方式（优先级从高到低）：
1. API 请求参数（前端传入，最高优先级）
2. 环境变量 / .env 文件
3. 代码默认值
"""

import os
from pathlib import Path
from pydantic import BaseModel, Field

# 尝试从 .env 文件加载（如果存在）
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)


class LLMConfig(BaseModel):
    """LLM 大模型配置

    provider 类型说明：
    - "openai_compatible": OpenAI 兼容格式（覆盖 OpenAI/DeepSeek/Qwen/Kimi/GLM/百川等 90%+ 厂商）
    - "anthropic": Anthropic Claude 系列（使用 Messages API 格式）
    """

    # 是否启用 LLM 功能
    enabled: bool = Field(
        default=False,
        description="是否启用 LLM 辅助分析功能"
    )

    # Provider 类型
    provider: str = Field(
        default="openai_compatible",
        description="LLM 提供商类型: openai_compatible | anthropic"
    )

    # API 配置
    api_key: str = Field(
        default="",
        description="LLM API Key"
    )
    base_url: str = Field(
        default="https://api.openai.com/v1",
        description="API Base URL（OpenAI 兼容厂商只需改这个）"
    )
    model: str = Field(
        default="gpt-4o-mini",
        description="模型名称"
    )

    # 快模型覆盖配置（为空时回退到默认模型）
    fast_provider: str | None = Field(
        default=None,
        description="快模型 provider，未配置时继承 provider"
    )
    fast_api_key: str | None = Field(
        default=None,
        description="快模型 API Key，未配置时继承 api_key"
    )
    fast_base_url: str | None = Field(
        default=None,
        description="快模型 Base URL，未配置时继承 base_url"
    )
    fast_model: str | None = Field(
        default=None,
        description="快模型名称，未配置时回退到默认模型"
    )
    fast_temperature: float | None = Field(
        default=None,
        ge=0.0, le=2.0,
        description="快模型温度，未配置时继承 temperature"
    )
    fast_max_tokens: int | None = Field(
        default=None,
        ge=64, le=32768,
        description="快模型最大输出 token，未配置时继承 max_tokens"
    )

    # 生成参数
    temperature: float = Field(
        default=0.7,
        ge=0.0, le=2.0,
        description="生成温度（创造性）"
    )
    max_tokens: int = Field(
        default=8192,
        ge=64, le=32768,
        description="最大输出 token 数（产业链推演等复杂任务需要 4096+）"
    )

    # 系统提示词
    system_prompt: str = Field(
        default=(
            "你是 StockScape 智能分析助手，专注 A 股市场分析。"
            "你可以看到用户当前浏览的 3D 地形数据，包括股票聚类信息、涨跌幅、成交量等。"
            "请基于提供的实时数据，给出专业、简洁的市场分析和投资洞察。"
            "注意：你的分析仅供参考，不构成投资建议。"
        ),
        description="系统角色提示词"
    )

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """从环境变量构建配置"""
        return cls(
            enabled=os.getenv("LLM_ENABLED", "false").lower() in ("true", "1", "yes"),
            provider=os.getenv("LLM_PROVIDER", "openai_compatible"),
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            fast_provider=os.getenv("LLM_FAST_PROVIDER") or None,
            fast_api_key=os.getenv("LLM_FAST_API_KEY") or None,
            fast_base_url=os.getenv("LLM_FAST_BASE_URL") or None,
            fast_model=os.getenv("LLM_FAST_MODEL") or None,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
            fast_temperature=(
                float(os.getenv("LLM_FAST_TEMPERATURE"))
                if os.getenv("LLM_FAST_TEMPERATURE")
                else None
            ),
            fast_max_tokens=(
                int(os.getenv("LLM_FAST_MAX_TOKENS"))
                if os.getenv("LLM_FAST_MAX_TOKENS")
                else None
            ),
            system_prompt=os.getenv("LLM_SYSTEM_PROMPT", cls.model_fields["system_prompt"].default),
        )


# 全局配置单例（从环境变量初始化）
llm_settings = LLMConfig.from_env()
