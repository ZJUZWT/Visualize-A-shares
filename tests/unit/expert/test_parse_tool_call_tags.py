"""测试 _parse_tool_call_tags 兜底解析方法"""

import pytest

from engine.expert.engine_experts import EngineExpert


class TestParseToolCallTags:
    """验证 [TOOL_CALL] / <tool_call> 幻觉格式的兜底解析"""

    def test_standard_tool_call_tags(self):
        """解析标准 [TOOL_CALL]...[/TOOL_CALL] 格式"""
        raw = """我来查询市场数据。
[TOOL_CALL] {"tool": "query_market_overview", "args": {}} [/TOOL_CALL]
[TOOL_CALL] {"tool": "run_screen", "args": {"filters": {"change_pct": {"gt": 3}}}} [/TOOL_CALL]"""

        result = EngineExpert._parse_tool_call_tags(raw)
        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["action"] == "query_market_overview"
        assert result["tool_calls"][1]["action"] == "run_screen"
        assert result["tool_calls"][1]["params"]["filters"]["change_pct"]["gt"] == 3

    def test_arrow_format(self):
        """解析 {tool => "xxx", args => {...}} 箭头格式"""
        raw = """[TOOL_CALL] {tool => "run_screen", args => {"filters": {"turnover_rate": {"gt": 3}}}} [/TOOL_CALL]"""

        result = EngineExpert._parse_tool_call_tags(raw)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["action"] == "run_screen"

    def test_arrow_format_with_non_json_args(self):
        """箭头格式但参数不是有效 JSON（如 --flag 格式），仍能提取工具名"""
        raw = """[TOOL_CALL] {tool => "run_screen", args => {
  --filter {"change_pct": {"gt": 0}}
  --days 5
  --limit 100
}} [/TOOL_CALL]"""

        result = EngineExpert._parse_tool_call_tags(raw)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["action"] == "run_screen"
        # 参数可能为空（因为不是有效JSON），但工具名被识别
        assert isinstance(result["tool_calls"][0]["params"], dict)

    def test_xml_tool_call_tags(self):
        """解析 <tool_call>...</tool_call> 格式"""
        raw = """<tool_call>{"action": "get_news", "params": {"code": "000001"}}</tool_call>"""

        result = EngineExpert._parse_tool_call_tags(raw)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["action"] == "get_news"
        assert result["tool_calls"][0]["params"]["code"] == "000001"

    def test_multiple_mixed_formats(self):
        """混合格式"""
        raw = """
[TOOL_CALL] {"tool": "query_market_overview", "args": {}} [/TOOL_CALL]
<tool_call>{"action": "run_screen", "params": {"filters": {}}}</tool_call>
"""
        result = EngineExpert._parse_tool_call_tags(raw)
        assert len(result["tool_calls"]) == 2

    def test_no_tool_calls(self):
        """没有工具调用标签时返回空列表"""
        raw = "这是一段普通的文本，没有任何工具调用。"
        result = EngineExpert._parse_tool_call_tags(raw)
        assert result["tool_calls"] == []

    def test_empty_tool_call(self):
        """空的工具调用标签"""
        raw = "[TOOL_CALL]  [/TOOL_CALL]"
        result = EngineExpert._parse_tool_call_tags(raw)
        assert result["tool_calls"] == []

    def test_unclosed_tool_call(self):
        """未闭合的 [TOOL_CALL]"""
        raw = """[TOOL_CALL] {tool => "query_stock", args => {"code": "600519"}}"""
        result = EngineExpert._parse_tool_call_tags(raw)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["action"] == "query_stock"

    def test_real_world_failure_case(self):
        """复现实际失败场景：数据专家输出 [TOOL_CALL] 格式"""
        raw = """我来扫描全市场，找出符合您要求的强势股。
[TOOL_CALL] {tool => "query_market_overview", args => {

}}
[/TOOL_CALL]
[TOOL_CALL] {tool => "run_screen", args => {
  --order_by "change_pct"
  --limit 50
  --offset 0
  --conditions {"rise_fall_rate_min": 3, "rise_fall_rate_max": 7}
}}
[/TOOL_CALL]"""

        result = EngineExpert._parse_tool_call_tags(raw)
        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["action"] == "query_market_overview"
        assert result["tool_calls"][1]["action"] == "run_screen"
