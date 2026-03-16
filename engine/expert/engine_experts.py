"""引擎专家 — 4 个引擎领域专家 + 1 个 RAG 投资顾问

每个引擎专家将用户问题路由到对应引擎工具链，
由 LLM 基于引擎返回数据生成流式回复。
"""

import json
from typing import AsyncGenerator, Literal

from loguru import logger

ExpertType = Literal["data", "quant", "info", "industry", "rag"]

EXPERT_PROFILES: dict[str, dict] = {
    "data": {
        "name": "数据专家",
        "icon": "📊",
        "color": "#60A5FA",
        "description": "行情查询、股票搜索、聚类分析、全市场概览",
        "system_prompt": (
            "你是 A 股数据分析专家，擅长行情数据查询、股票搜索、聚类结构分析和全市场概览。"
            "你会基于 DataEngine 返回的数据，用通俗易懂的语言解读市场数据。"
            "回答时使用 Markdown 格式，数字需要精确引用数据。"
        ),
        "suggestions": [
            "今日全市场概览",
            "搜索新能源相关股票",
            "查询聚类 0 的成分股",
            "帮我看看茅台的详情",
        ],
        "engines": ["data_engine"],
    },
    "quant": {
        "name": "量化专家",
        "icon": "🔬",
        "color": "#A78BFA",
        "description": "技术指标、因子评分、IC 回测、条件选股",
        "system_prompt": (
            "你是 A 股量化分析专家，擅长技术指标分析（RSI/MACD/布林带）、多因子评分、"
            "因子 IC 回测和条件选股。你会基于 QuantEngine 返回的数据给出量化分析建议。"
            "回答时使用 Markdown 格式，善用表格展示因子数据。"
        ),
        "suggestions": [
            "贵州茅台的技术指标如何？",
            "查看因子体系全景",
            "PE 低于 20 且换手率大于 3% 的股票",
            "运行因子 IC 回测",
        ],
        "engines": ["quant_engine"],
    },
    "info": {
        "name": "资讯专家",
        "icon": "📰",
        "color": "#F59E0B",
        "description": "新闻情感、公告解读、事件影响评估",
        "system_prompt": (
            "你是 A 股资讯分析专家，擅长新闻情感分析、公告解读、事件对个股的影响评估。"
            "你会基于 InfoEngine 返回的新闻和公告数据，提炼关键信息并评估市场影响。"
            "回答时使用 Markdown 格式，注意区分正面/负面/中性消息。"
        ),
        "suggestions": [
            "宁德时代最近有什么新闻？",
            "比亚迪近期公告",
            "评估降息对银行股的影响",
            "半导体行业最近的市场情绪如何？",
        ],
        "engines": ["info_engine"],
    },
    "industry": {
        "name": "产业链专家",
        "icon": "🏭",
        "color": "#10B981",
        "description": "行业认知、产业链映射、资金构成、周期分析",
        "system_prompt": (
            "你是 A 股产业链分析专家，擅长行业认知分析、产业链上下游映射、"
            "资金构成分析和行业周期定位。你会基于 IndustryEngine 返回的数据，"
            "给出产业链视角的深度分析。回答时使用 Markdown 格式。"
        ),
        "suggestions": [
            "半导体产业链分析",
            "锂电池行业现在处于什么周期？",
            "查看白酒行业板块成分股",
            "宁德时代的资金构成如何？",
        ],
        "engines": ["industry_engine"],
    },
    "rag": {
        "name": "投资顾问",
        "icon": "🧠",
        "color": "#EC4899",
        "description": "自由对话、知识图谱、信念系统、综合分析",
        "system_prompt": "",  # RAG 专家使用自己的 prompt 系统
        "suggestions": [
            "宁德时代近期走势如何？",
            "A 股政策面有什么变化？",
            "新能源板块值得关注吗？",
            "帮我做一份市场研判",
        ],
        "engines": ["expert_agent"],
    },
}


class EngineExpert:
    """引擎专家 — 基于引擎数据 + LLM 的流式对话"""

    def __init__(self, expert_type: ExpertType, llm_provider=None):
        self.expert_type = expert_type
        self.profile = EXPERT_PROFILES[expert_type]
        self._llm = llm_provider

    async def chat(self, message: str) -> AsyncGenerator[dict, None]:
        """流式对话，yield SSE 事件"""
        if not self._llm:
            yield {"event": "error", "data": {"message": "LLM 未配置"}}
            return

        yield {"event": "thinking_start", "data": {}}

        # 1. 规划工具调用
        tool_plan = await self._plan_tools(message)
        tool_calls = tool_plan.get("tool_calls", [])

        # 2. 执行工具调用
        tool_results = []
        for tc in tool_calls:
            yield {"event": "tool_call", "data": {
                "engine": tc.get("engine", self.expert_type),
                "action": tc["action"],
                "params": tc.get("params", {}),
            }}
            result = await self._execute_tool(tc)
            tool_results.append(result)
            yield {"event": "tool_result", "data": {
                "engine": tc.get("engine", self.expert_type),
                "action": tc["action"],
                "summary": result[:200] if result else "无结果",
            }}

        # 3. 流式生成回复
        full_text = ""
        async for token, accumulated in self._reply_stream(message, tool_results):
            full_text = accumulated
            yield {"event": "reply_token", "data": {"token": token}}

        yield {"event": "reply_complete", "data": {"full_text": full_text}}

    async def _plan_tools(self, message: str) -> dict:
        """让 LLM 规划需要调用的工具（流式收集 + think 标签剥离）"""
        import re
        from llm.providers import ChatMessage

        tools_desc = self._get_available_tools_desc()
        plan_prompt = f"""你是{self.profile['name']}。用户提出了一个问题，你需要决定是否需要调用工具获取数据。

可用工具:
{tools_desc}

请以 JSON 格式回复:
{{
  "tool_calls": [
    {{"action": "工具名", "params": {{"参数名": "值"}}}}
  ]
}}

如果不需要工具，返回空列表:
{{"tool_calls": []}}

直接输出 JSON，不要包含 markdown 代码块、不要包含任何额外文字或思考过程。"""

        try:
            # 流式收集（保持链路活跃）
            chunks: list[str] = []
            async for token in self._llm.chat_stream([
                ChatMessage("system", plan_prompt),
                ChatMessage("user", message),
            ]):
                chunks.append(token)
            text = "".join(chunks).strip()

            if not text:
                logger.warning("工具规划 LLM 返回空内容，跳过工具调用")
                return {"tool_calls": []}

            # 剥离 <think>...</think> 标签
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

            # 提取 JSON（处理 markdown 代码块）
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            # 尝试解析 JSON
            if not text:
                return {"tool_calls": []}
            return json.loads(text)
        except Exception as e:
            logger.warning(f"工具规划失败，跳过工具调用: {e}")
            return {"tool_calls": []}

    async def _execute_tool(self, tc: dict) -> str:
        """执行单个工具调用"""
        action = tc["action"]
        params = tc.get("params", {})

        try:
            if self.expert_type == "data":
                return await self._exec_data_tool(action, params)
            elif self.expert_type == "quant":
                return await self._exec_quant_tool(action, params)
            elif self.expert_type == "info":
                return await self._exec_info_tool(action, params)
            elif self.expert_type == "industry":
                return await self._exec_industry_tool(action, params)
        except Exception as e:
            logger.error(f"工具执行失败 [{action}]: {e}")
            return f"工具调用失败: {e}"

        return "未知引擎类型"

    async def _exec_data_tool(self, action: str, params: dict) -> str:
        """DataEngine 工具"""
        from mcpserver.data_access import DataAccess
        from mcpserver import tools

        da = DataAccess()
        if action == "query_market_overview":
            return tools.query_market_overview(da)
        elif action == "search_stocks":
            return tools.search_stocks(da, params.get("query", ""))
        elif action == "query_stock":
            return tools.query_stock(da, params.get("code", ""))
        elif action == "query_cluster":
            return tools.query_cluster(da, params.get("cluster_id", 0))
        elif action == "find_similar_stocks":
            return tools.find_similar_stocks(da, params.get("code", ""), params.get("top_k", 10))
        elif action == "query_history":
            return tools.query_history(da, params.get("code", ""), params.get("days", 60))
        elif action == "run_screen":
            return tools.run_screen(da, params.get("filters", {}))
        return f"未知 data 工具: {action}"

    async def _exec_quant_tool(self, action: str, params: dict) -> str:
        """QuantEngine 工具"""
        from mcpserver.data_access import DataAccess
        from mcpserver import tools

        da = DataAccess()
        if action == "get_technical_indicators":
            return tools.get_technical_indicators(da, params.get("code", ""))
        elif action == "get_factor_scores":
            return tools.get_factor_scores(da, params.get("code", ""))
        elif action == "query_factor_analysis":
            return tools.query_factor_analysis(da, params.get("factor_name"))
        elif action == "run_backtest":
            return tools.run_backtest(da, params.get("rolling_window", 20), params.get("auto_inject", False))
        elif action == "run_screen":
            return tools.run_screen(da, params.get("filters", {}), params.get("sort_by", "pct_chg"))
        return f"未知 quant 工具: {action}"

    async def _exec_info_tool(self, action: str, params: dict) -> str:
        """InfoEngine 工具"""
        from mcpserver.data_access import DataAccess
        from mcpserver import tools

        da = DataAccess()
        if action == "get_news":
            return tools.get_news(da, params.get("code", ""), params.get("limit", 20))
        elif action == "get_announcements":
            return tools.get_announcements(da, params.get("code", ""), params.get("limit", 10))
        elif action == "assess_event_impact":
            return tools.assess_event_impact(da, params.get("code", ""), params.get("event_desc", ""))
        return f"未知 info 工具: {action}"

    async def _exec_industry_tool(self, action: str, params: dict) -> str:
        """IndustryEngine 工具"""
        from mcpserver.data_access import DataAccess
        from mcpserver import tools

        da = DataAccess()
        if action == "query_industry_cognition":
            return tools.get_industry_cognition(da, params.get("target", ""))
        elif action == "query_industry_mapping":
            return tools.get_industry_mapping_tool(da, params.get("industry", ""))
        elif action == "query_capital_structure":
            return tools.get_capital_structure_tool(da, params.get("code", ""))
        return f"未知 industry 工具: {action}"

    async def _reply_stream(
        self, message: str, tool_results: list[str]
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复（自动过滤 <think> 标签内容）"""
        from llm.providers import ChatMessage

        context_parts = []
        if tool_results:
            context_parts.append("工具调用结果：\n" + "\n---\n".join(tool_results))

        system = self.profile["system_prompt"]
        if context_parts:
            system += "\n\n" + "\n\n".join(context_parts)

        accumulated = ""
        in_think = False
        raw_buffer = ""

        try:
            async for token in self._llm.chat_stream([
                ChatMessage("system", system),
                ChatMessage("user", message),
            ]):
                raw_buffer += token

                # 检测 <think> 标签开始
                if not in_think and "<think>" in raw_buffer:
                    before = raw_buffer.split("<think>", 1)[0]
                    if before:
                        accumulated += before
                        yield before, accumulated
                    in_think = True
                    raw_buffer = raw_buffer.split("<think>", 1)[1]
                    continue

                # 检测 </think> 标签结束
                if in_think and "</think>" in raw_buffer:
                    in_think = False
                    remaining = raw_buffer.split("</think>", 1)[1]
                    raw_buffer = remaining.lstrip("\n")
                    continue

                # 在 <think> 块内：丢弃内容，但防止缓冲区无限增长
                if in_think:
                    if len(raw_buffer) > 200:
                        raw_buffer = raw_buffer[-20:]
                    continue

                # 正常正文：检查是否可能是不完整的 <think> 标签
                if "<" in raw_buffer and not raw_buffer.endswith(">"):
                    if len(raw_buffer) < 10:
                        continue

                # 推送正文 token
                if raw_buffer:
                    accumulated += raw_buffer
                    yield raw_buffer, accumulated
                    raw_buffer = ""

            # 处理残余缓冲区
            if raw_buffer and not in_think:
                accumulated += raw_buffer
                yield raw_buffer, accumulated

        except Exception as e:
            logger.error(f"reply_stream 失败: {e}")
            yield f"回复生成失败: {e}", f"回复生成失败: {e}"

    def _get_available_tools_desc(self) -> str:
        """获取当前引擎可用工具的描述"""
        TOOLS_DESC = {
            "data": """- query_market_overview(): 全市场概览快照
- search_stocks(query: str): 股票搜索（模糊匹配代码或名称）
- query_stock(code: str): 单股全维度分析，code 示例: '000001'
- query_cluster(cluster_id: int): 查询指定聚类信息
- find_similar_stocks(code: str, top_k: int): 跨簇相似股票搜索
- query_history(code: str, days: int): 历史行情数据
- run_screen(filters: dict): 条件选股""",
            "quant": """- get_technical_indicators(code: str): 获取技术指标（RSI/MACD/布林带）
- get_factor_scores(code: str): 获取多因子评分
- query_factor_analysis(factor_name: str): 查看因子体系，不传名称返回全景
- run_backtest(rolling_window: int, auto_inject: bool): 因子 IC 回测
- run_screen(filters: dict, sort_by: str): 条件选股""",
            "info": """- get_news(code: str, limit: int): 获取个股新闻+情感分析
- get_announcements(code: str, limit: int): 获取公司公告
- assess_event_impact(code: str, event_desc: str): 评估事件影响""",
            "industry": """- query_industry_cognition(target: str): 产业链认知（股票代码或行业名）
- query_industry_mapping(industry: str): 行业板块列表及成分股
- query_capital_structure(code: str): 资金构成分析""",
        }
        return TOOLS_DESC.get(self.expert_type, "无可用工具")


def get_expert_profiles() -> list[dict]:
    """返回所有专家的配置信息（用于前端展示）"""
    return [
        {
            "type": k,
            "name": v["name"],
            "icon": v["icon"],
            "color": v["color"],
            "description": v["description"],
            "suggestions": v["suggestions"],
        }
        for k, v in EXPERT_PROFILES.items()
    ]
