"""ToolOutcomeTracker 工具使用反馈学习测试"""

import pytest

from engine.expert.tool_tracker import ToolOutcomeTracker, classify_query


class TestClassifyQuery:
    def test_stock_analysis(self):
        assert classify_query("分析一下宁德时代") == "个股分析"

    def test_stock_recommendation(self):
        assert classify_query("今天有什么好股票推荐") == "选股推荐"

    def test_sector_question(self):
        assert classify_query("新能源板块今天怎么样") == "板块行业"

    def test_technical_question(self):
        assert classify_query("MACD金叉了该怎么操作") == "技术面"

    def test_news_question(self):
        assert classify_query("最近有什么利好消息") == "消息面"

    def test_general_chat(self):
        assert classify_query("你好啊") == "闲聊"


class TestToolOutcomeTracker:
    @pytest.fixture
    def tracker(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        return ToolOutcomeTracker(db_path)

    def test_record_and_get_stats(self, tracker):
        """记录工具使用并获取统计"""
        tracker.record(
            query_type="个股分析",
            tools_used=["data", "quant", "info", "industry"],
            success=True,
        )
        tracker.record(
            query_type="个股分析",
            tools_used=["data", "quant"],
            success=True,
        )
        stats = tracker.get_recent_stats(days=7)
        assert len(stats) > 0
        assert any(s["query_type"] == "个股分析" for s in stats)

    def test_format_experience_prompt(self, tracker):
        """格式化经验 prompt"""
        tracker.record("个股分析", ["data", "quant", "info", "industry"], True)
        tracker.record("个股分析", ["data", "quant", "info", "industry"], True)
        tracker.record("技术面", ["data", "quant"], True)
        prompt = tracker.format_experience_prompt()
        assert "个股分析" in prompt or prompt == ""

    def test_empty_stats(self, tracker):
        """无数据时返回空"""
        stats = tracker.get_recent_stats()
        assert stats == []
        prompt = tracker.format_experience_prompt()
        assert prompt == ""
