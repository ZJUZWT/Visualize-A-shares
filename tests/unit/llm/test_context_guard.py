"""ContextGuard 上下文窗口守卫测试"""

import pytest
from llm.context_guard import ContextGuard


@pytest.fixture
def guard():
    return ContextGuard(max_input_tokens=1000)


class TestTokenEstimation:
    def test_empty_string(self, guard):
        assert guard.estimate_tokens("") == 0

    def test_pure_chinese(self, guard):
        """中文按 0.7 token/字估算"""
        text = "这是测试文本" * 100  # 600 中文字
        tokens = guard.estimate_tokens(text)
        assert 350 < tokens < 500  # ~420

    def test_pure_english(self, guard):
        """英文按 0.25 token/字估算"""
        text = "hello world test " * 100  # 1700 英文字符
        tokens = guard.estimate_tokens(text)
        assert 350 < tokens < 500  # ~425

    def test_mixed(self, guard):
        """中英混合"""
        text = "你好hello世界world"
        tokens = guard.estimate_tokens(text)
        assert tokens > 0


class TestGuardMessages:
    def test_within_budget_no_change(self, guard):
        """未超预算，消息不变"""
        messages = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"},
        ]
        result = guard.guard_messages(messages)
        assert len(result) == 2
        assert result[0]["content"] == "你是助手"

    def test_level1_truncate_history(self):
        """Level 1: 截断早期对话历史"""
        guard = ContextGuard(max_input_tokens=200)
        messages = [
            {"role": "system", "content": "系统提示"},
        ]
        # 加入 20 轮对话
        for i in range(20):
            messages.append({"role": "user", "content": f"用户消息{i}" * 20})
            messages.append({"role": "assistant", "content": f"助手回复{i}" * 20})
        messages.append({"role": "user", "content": "最新问题"})

        result = guard.guard_messages(messages)
        # system 和最新 user 必须保留
        assert result[0]["role"] == "system"
        assert result[-1]["role"] == "user"
        assert result[-1]["content"] == "最新问题"
        # 历史被截断
        assert len(result) < len(messages)

    def test_system_and_last_user_always_preserved(self):
        """system prompt 和最新 user 消息永远不被截断"""
        guard = ContextGuard(max_input_tokens=50)
        messages = [
            {"role": "system", "content": "很长的系统提示" * 50},
            {"role": "user", "content": "用户消息"},
        ]
        result = guard.guard_messages(messages)
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == "用户消息"

    def test_returns_new_list(self, guard):
        """guard_messages 返回新列表，不修改原始消息"""
        messages = [
            {"role": "system", "content": "系统"},
            {"role": "user", "content": "用户"},
        ]
        original_len = len(messages)
        guard.guard_messages(messages)
        assert len(messages) == original_len
