from llm.config import LLMConfig
from llm.providers import ModelRouter


def test_model_router_uses_fast_tier_overrides():
    config = LLMConfig(
        enabled=True,
        provider="openai_compatible",
        api_key="quality-key",
        base_url="https://quality.example/v1",
        model="quality-model",
        fast_model="fast-model",
        fast_api_key="fast-key",
        fast_base_url="https://fast.example/v1",
    )

    router = ModelRouter.from_config(config)

    fast = router.get("fast")
    quality = router.get("quality")

    assert fast.config.model == "fast-model"
    assert fast.config.api_key == "fast-key"
    assert fast.config.base_url == "https://fast.example/v1"
    assert quality.config.model == "quality-model"
    assert quality.config.api_key == "quality-key"


def test_model_router_falls_back_to_quality_when_fast_not_configured():
    config = LLMConfig(
        enabled=True,
        provider="openai_compatible",
        api_key="quality-key",
        base_url="https://quality.example/v1",
        model="quality-model",
    )

    router = ModelRouter.from_config(config)

    fast = router.get("fast")
    quality = router.get("quality")

    assert fast.config.model == "quality-model"
    assert fast.config.api_key == "quality-key"
    assert quality.config.model == "quality-model"
