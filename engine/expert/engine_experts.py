"""引擎专家 — 4 个引擎领域专家 + 1 个 RAG 投资顾问

每个引擎专家将用户问题路由到对应引擎工具链，
由 LLM 基于引擎返回数据生成流式回复。
"""

import json
from typing import AsyncGenerator, Literal

import pandas as pd
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

    # 类级缓存：名称→代码映射（懒加载）
    _name_to_code: dict[str, str] | None = None

    @classmethod
    def _resolve_code(cls, raw: str) -> str:
        """将 LLM 传入的 code 参数解析为标准 6 位股票代码

        LLM 经常传股票名称（如"雄韬股份"）而非代码（"002733"），
        此方法自动解析名称→代码，保证下游数据引擎能正确查询。
        """
        raw = raw.strip()
        # 已经是 6 位纯数字代码，直接返回
        if len(raw) == 6 and raw.isdigit():
            return raw

        # 懒加载名称→代码映射
        if cls._name_to_code is None:
            try:
                from data_engine import get_data_engine
                de = get_data_engine()
                profiles = de.get_profiles()
                cls._name_to_code = {}
                for code, info in profiles.items():
                    name = info.get("name", "")
                    if name:
                        cls._name_to_code[name] = code
                logger.info(f"EngineExpert 名称映射缓存已构建: {len(cls._name_to_code)} 条")
            except Exception as e:
                logger.warning(f"构建名称映射失败: {e}")
                cls._name_to_code = {}

        # 精确匹配
        if raw in cls._name_to_code:
            resolved = cls._name_to_code[raw]
            logger.debug(f"代码解析: '{raw}' → '{resolved}'")
            return resolved

        # 模糊匹配（名称包含输入）
        for name, code in cls._name_to_code.items():
            if raw in name or name in raw:
                logger.debug(f"代码模糊解析: '{raw}' → '{code}' ({name})")
                return code

        # 无法解析，原样返回（下游会报错但不会崩溃）
        logger.warning(f"无法解析股票代码: '{raw}'")
        return raw

    def __init__(self, expert_type: ExpertType, llm_provider=None):
        self.expert_type = expert_type
        self.profile = EXPERT_PROFILES[expert_type]
        self._llm = llm_provider

    async def chat(self, message: str, history: list[dict] | None = None) -> AsyncGenerator[dict, None]:
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
            if not isinstance(tc, dict):
                logger.warning(f"跳过非dict工具调用: {type(tc)}")
                continue
            yield {"event": "tool_call", "data": {
                "engine": tc.get("engine", self.expert_type),
                "action": tc.get("action", "unknown"),
                "params": tc.get("params", {}),
            }}
            result = await self._execute_tool(tc)
            tool_results.append(result)
            yield {"event": "tool_result", "data": {
                "engine": tc.get("engine", self.expert_type),
                "action": tc.get("action", "unknown"),
                "summary": result[:200] if result else "无结果",
            }}

        # 3. 流式生成回复
        full_text = ""
        async for token, accumulated in self._reply_stream(message, tool_results, history=history):
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

            # 剥离各种可能的标签
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<tool_code>.*?</tool_code>", "", text, flags=re.DOTALL).strip()

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
        """执行单个工具调用 — 直接调用引擎单例，不走 HTTP"""
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
        """DataEngine 工具 — 直接调用引擎单例"""
        import asyncio
        import datetime
        import json
        from data_engine import get_data_engine

        de = get_data_engine()

        if action == "get_current_date":
            now = datetime.datetime.now()
            return json.dumps({
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                "is_trading_day": now.weekday() < 5,  # 简化判断：工作日
            }, ensure_ascii=False)

        elif action == "query_market_overview":
            snap = de.get_snapshot()
            if snap is None or snap.empty:
                return json.dumps({"error": "无快照数据"}, ensure_ascii=False)
            total = len(snap)
            up = int((snap.get("pct_chg", pd.Series()) > 0).sum()) if "pct_chg" in snap.columns else 0
            down = int((snap.get("pct_chg", pd.Series()) < 0).sum()) if "pct_chg" in snap.columns else 0
            return json.dumps({"total_stocks": total, "up": up, "down": down, "flat": total - up - down}, ensure_ascii=False)

        elif action == "search_stocks":
            snap = de.get_snapshot()
            if snap is None or snap.empty:
                return json.dumps({"error": "无快照数据"}, ensure_ascii=False)
            query = params.get("query", "").lower()
            results = []
            for _, row in snap.iterrows():
                code = str(row.get("code", ""))
                name = str(row.get("name", ""))
                if query in code.lower() or query in name.lower():
                    results.append({"code": code, "name": name,
                                    "price": float(row.get("price", 0)),
                                    "pct_chg": float(row.get("pct_chg", 0))})
                if len(results) >= 20:
                    break
            return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, default=str)

        elif action == "query_stock":
            code = self._resolve_code(params.get("code", ""))
            snap = de.get_snapshot()
            if snap is None or snap.empty:
                return json.dumps({"error": "无快照数据"}, ensure_ascii=False)
            row = snap[snap["code"].astype(str) == code]
            if row.empty:
                return json.dumps({"error": f"未找到 {code}"}, ensure_ascii=False)
            return row.iloc[0].to_json(force_ascii=False, default_handler=str)

        elif action == "query_history":
            code = self._resolve_code(params.get("code", ""))
            days = int(params.get("days", 60))
            end = datetime.date.today().strftime("%Y-%m-%d")
            start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            df = await asyncio.to_thread(de.get_daily_history, code, start, end)
            if df is None or df.empty:
                return json.dumps({"error": f"无 {code} 日线数据"}, ensure_ascii=False)
            records = df.tail(20).to_dict("records")
            return json.dumps({"code": code, "records": records, "total_days": len(df)},
                              ensure_ascii=False, default=str)

        elif action == "query_cluster":
            from cluster_engine import get_cluster_engine
            ce = get_cluster_engine()
            cluster_id = params.get("cluster_id", 0)
            result = ce.get_cluster_stocks(cluster_id)
            return json.dumps(result, ensure_ascii=False, default=str) if result else f"聚类 {cluster_id} 无数据"

        elif action == "find_similar_stocks":
            from cluster_engine import get_cluster_engine
            ce = get_cluster_engine()
            code = self._resolve_code(params.get("code", ""))
            top_k = params.get("top_k", 10)
            result = ce.find_similar(code, top_k)
            return json.dumps(result, ensure_ascii=False, default=str) if result else f"未找到 {code} 的相似股票"

        elif action == "run_screen":
            snap = de.get_snapshot()
            if snap is None or snap.empty:
                return json.dumps({"error": "无快照数据"}, ensure_ascii=False)
            filters = params.get("filters", {})
            result = snap.copy()
            for col, cond in filters.items():
                if col in result.columns:
                    if isinstance(cond, dict):
                        if "gt" in cond:
                            result = result[pd.to_numeric(result[col], errors="coerce") > cond["gt"]]
                        if "lt" in cond:
                            result = result[pd.to_numeric(result[col], errors="coerce") < cond["lt"]]
            records = result.head(30).to_dict("records")
            return json.dumps({"count": len(result), "results": records}, ensure_ascii=False, default=str)

        return f"未知 data 工具: {action}"

    async def _exec_quant_tool(self, action: str, params: dict) -> str:
        """QuantEngine 工具 — 直接调用引擎单例"""
        import asyncio
        import datetime
        import json
        from quant_engine import get_quant_engine
        from data_engine import get_data_engine

        qe = get_quant_engine()
        de = get_data_engine()

        if action == "get_technical_indicators":
            code = self._resolve_code(params.get("code", ""))
            days = 120
            end = datetime.date.today().strftime("%Y-%m-%d")
            start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            daily = await asyncio.to_thread(de.get_daily_history, code, start, end)
            if daily is None or daily.empty:
                return json.dumps({"error": f"无 {code} 日线数据，无法计算技术指标"}, ensure_ascii=False)
            indicators = qe.compute_indicators(daily)
            return json.dumps({"code": code, "data_days": len(daily), "indicators": indicators},
                              ensure_ascii=False, default=str)

        elif action == "get_factor_scores":
            snap = de.get_snapshot()
            if snap is None or snap.empty:
                return json.dumps({"error": "无快照数据"}, ensure_ascii=False)
            code = self._resolve_code(params.get("code", ""))
            row = snap[snap["code"].astype(str) == code]
            if row.empty:
                return json.dumps({"error": f"快照中未找到 {code}"}, ensure_ascii=False)
            weights, source = qe.get_factor_weights()
            factor_defs = qe.get_factor_defs()
            factors = {}
            for fdef in factor_defs:
                val = row.iloc[0].get(fdef.source_col)
                factors[fdef.name] = {"value": float(val) if val is not None and str(val) != "nan" else None,
                                       "weight": weights.get(fdef.name, 0), "direction": fdef.direction,
                                       "desc": fdef.desc}
            return json.dumps({"code": code, "factors": factors, "weight_source": source},
                              ensure_ascii=False, default=str)

        elif action == "query_factor_analysis":
            factor_name = params.get("factor_name")
            factor_defs = qe.get_factor_defs()
            weights, source = qe.get_factor_weights()
            if factor_name:
                matched = [f for f in factor_defs if f.name == factor_name]
                if not matched:
                    return json.dumps({"error": f"未找到因子: {factor_name}"}, ensure_ascii=False)
                f = matched[0]
                return json.dumps({"name": f.name, "source_col": f.source_col, "direction": f.direction,
                                   "group": f.group, "weight": weights.get(f.name, 0), "desc": f.desc},
                                  ensure_ascii=False)
            # 全景
            all_factors = [{"name": f.name, "group": f.group, "direction": f.direction,
                            "weight": weights.get(f.name, 0), "desc": f.desc} for f in factor_defs]
            return json.dumps({"weight_source": source, "factors": all_factors}, ensure_ascii=False)

        elif action == "run_backtest":
            result = await asyncio.to_thread(qe.run_backtest, rolling_window=params.get("rolling_window", 20))
            return json.dumps({"backtest_days": result.backtest_days, "icir_weights": result.icir_weights},
                              ensure_ascii=False, default=str)

        elif action == "run_screen":
            return await self._exec_data_tool("run_screen", params)

        return f"未知 quant 工具: {action}"

    async def _exec_info_tool(self, action: str, params: dict) -> str:
        """InfoEngine 工具 — 直接调用引擎单例"""
        import asyncio
        import json
        from data_engine import get_data_engine

        de = get_data_engine()

        if action == "get_news":
            code = self._resolve_code(params.get("code", ""))
            limit = params.get("limit", 20)
            news_df = await asyncio.to_thread(de.get_news, code, limit)
            if news_df is None or (hasattr(news_df, 'empty') and news_df.empty):
                return json.dumps({"error": f"无 {code} 新闻数据"}, ensure_ascii=False)
            # DataFrame → list[dict]
            if hasattr(news_df, 'to_dict'):
                records = news_df.to_dict("records")
            else:
                records = news_df
            return json.dumps({"code": code, "news": records}, ensure_ascii=False, default=str)

        elif action == "get_announcements":
            code = self._resolve_code(params.get("code", ""))
            limit = params.get("limit", 10)
            try:
                ann_df = await asyncio.to_thread(de.get_announcements, code, limit)
                if ann_df is None or (hasattr(ann_df, 'empty') and ann_df.empty):
                    return json.dumps({"error": f"无 {code} 公告数据"}, ensure_ascii=False)
                if hasattr(ann_df, 'to_dict'):
                    records = ann_df.to_dict("records")
                else:
                    records = ann_df
                return json.dumps({"code": code, "announcements": records}, ensure_ascii=False, default=str)
            except AttributeError:
                return json.dumps({"error": "公告功能暂未实现"}, ensure_ascii=False)

        elif action == "assess_event_impact":
            # 事件影响评估需要 LLM
            code = self._resolve_code(params.get("code", ""))
            event_desc = params.get("event_desc", "")
            return json.dumps({"code": code, "event": event_desc,
                              "note": "事件影响评估需结合新闻和技术面综合分析"}, ensure_ascii=False)

        return f"未知 info 工具: {action}"

    async def _exec_industry_tool(self, action: str, params: dict) -> str:
        """IndustryEngine 工具 — 直接调用引擎单例"""
        import asyncio
        import json

        if action == "query_industry_cognition":
            from industry_engine import get_industry_engine
            ie = get_industry_engine()
            target = params.get("target", "")
            try:
                # analyze() 是 async 方法，直接 await（不能用 asyncio.to_thread）
                result = await ie.analyze(target=target)
                if result:
                    return json.dumps(result, ensure_ascii=False, default=str)
                return f"⚠️ 需要后端在线且配置 LLM 才能获取产业链认知"
            except Exception as e:
                return f"产业链认知查询失败: {e}"

        elif action == "query_industry_mapping":
            from industry_engine import get_industry_engine
            ie = get_industry_engine()
            industry = params.get("industry", "")
            try:
                result = await asyncio.to_thread(ie.get_industry_mapping, industry)
                return json.dumps(result, ensure_ascii=False, default=str) if result else "无映射数据"
            except Exception as e:
                return f"行业映射查询失败: {e}"

        elif action == "query_capital_structure":
            from industry_engine import get_industry_engine
            ie = get_industry_engine()
            code = self._resolve_code(params.get("code", ""))
            try:
                result = await asyncio.to_thread(ie.get_capital_structure, code)
                return json.dumps(result, ensure_ascii=False, default=str) if result else f"无 {code} 资金构成数据"
            except Exception as e:
                return f"资金构成查询失败: {e}"

        return f"未知 industry 工具: {action}"

    async def _reply_stream(
        self, message: str, tool_results: list[str],
        history: list[dict] | None = None,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复（自动过滤 <think> / <minimax:*> 标签内容）"""
        from llm.providers import ChatMessage

        context_parts = []
        if tool_results:
            context_parts.append("工具调用结果：\n" + "\n---\n".join(tool_results))

        system = self.profile["system_prompt"]
        if context_parts:
            system += "\n\n" + "\n\n".join(context_parts)

        # 构建消息列表（含对话历史）
        messages = [ChatMessage("system", system)]
        for h in (history or []):
            role = "assistant" if h["role"] == "expert" else h["role"]
            content = h.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            messages.append(ChatMessage(role, content))
        messages.append(ChatMessage("user", message))

        accumulated = ""
        in_skip = False          # 跳过区域
        skip_end_tag = ""        # 当前跳过区域的结束标签
        raw_buffer = ""

        # 需要过滤的标签及其结束标签
        SKIP_TAGS = {
            "<think>": "</think>",
            "<minimax:tool_call>": "</minimax:tool_call>",
            "<minimax:search_result>": "</minimax:search_result>",
            "<tool_call>": "</tool_call>",
            "<tool_code>": "</tool_code>",
        }

        try:
            skip_bytes = 0  # skip 区域累积字节数

            async for token in self._llm.chat_stream(messages):
                raw_buffer += token

                # 检测进入跳过区域
                if not in_skip:
                    for start_tag, end_tag in SKIP_TAGS.items():
                        if start_tag in raw_buffer:
                            before = raw_buffer.split(start_tag, 1)[0]
                            if before:
                                accumulated += before
                                yield before, accumulated
                            in_skip = True
                            skip_end_tag = end_tag
                            skip_bytes = 0
                            raw_buffer = raw_buffer.split(start_tag, 1)[1]
                            break
                    if in_skip:
                        continue

                # 检测离开跳过区域
                if in_skip and skip_end_tag in raw_buffer:
                    in_skip = False
                    remaining = raw_buffer.split(skip_end_tag, 1)[1]
                    raw_buffer = remaining.lstrip("\n")
                    skip_end_tag = ""
                    skip_bytes = 0
                    continue

                # 在跳过块内：丢弃内容，但防止缓冲区无限增长
                if in_skip:
                    skip_bytes += len(token)
                    # 保护：如果 skip 区域累积超过 2000 字节还未关闭，强制退出
                    if skip_bytes > 2000:
                        logger.warning(f"skip 区域未关闭(>{skip_bytes}B)，强制退出: {skip_end_tag}")
                        in_skip = False
                        raw_buffer = ""
                        skip_end_tag = ""
                        skip_bytes = 0
                    elif len(raw_buffer) > 200:
                        raw_buffer = raw_buffer[-20:]
                    continue

                # 正常正文：检查是否可能是不完整的标签
                if "<" in raw_buffer and not raw_buffer.endswith(">"):
                    if len(raw_buffer) < 30:
                        continue

                # 推送正文 token
                if raw_buffer:
                    accumulated += raw_buffer
                    yield raw_buffer, accumulated
                    raw_buffer = ""

            # 处理残余缓冲区
            if raw_buffer and not in_skip:
                accumulated += raw_buffer
                yield raw_buffer, accumulated

        except Exception as e:
            logger.error(f"reply_stream 失败: {e}")
            yield f"回复生成失败: {e}", f"回复生成失败: {e}"

    def _get_available_tools_desc(self) -> str:
        """获取当前引擎可用工具的描述"""
        TOOLS_DESC = {
            "data": """- get_current_date(): 获取当前日期、时间、星期几、是否交易日
- query_market_overview(): 全市场概览快照
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
