"""AnthropicProvider.chat_stream() bug 修复验证"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from llm.providers import AnthropicProvider, LLMConfig, ChatMessage


@pytest.mark.asyncio
async def test_anthropic_chat_stream_url_uses_config_base_url():
    """验证 chat_stream 使用 config.base_url 而非不存在的 _get_base_url()"""
    config = LLMConfig(
        provider="anthropic",
        api_key="test-key",
        base_url="https://api.example.com",
        model="claude-3",
    )
    provider = AnthropicProvider(config)

    # 不应抛 AttributeError
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        async def fake_lines():
            for line in [
                'data: {"type":"content_block_delta","delta":{"text":"hello"}}',
                'data: {"type":"message_stop"}',
            ]:
                yield line

        mock_resp.aiter_lines = fake_lines

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        tokens = []
        async for token in provider.chat_stream(
            [ChatMessage(role="user", content="hi")]
        ):
            tokens.append(token)

        assert tokens == ["hello"]
        # 验证 URL 包含 config.base_url
        call_args = mock_client.stream.call_args
        assert "https://api.example.com/v1/messages" in str(call_args)
