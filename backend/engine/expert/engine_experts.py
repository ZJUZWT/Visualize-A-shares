"""引擎专家 — 4 个引擎领域专家 + 1 个 RAG 投资顾问

每个引擎专家将用户问题路由到对应引擎工具链，
由 LLM 基于引擎返回数据生成流式回复。
"""

import json
from typing import AsyncGenerator, Literal

import pandas as pd
from loguru import logger

ExpertType = Literal["data", "quant", "info", "industry", "rag", "short_term"]

EXPERT_PROFILES: dict[str, dict] = {
    "data": {
        "name": "数据专家",
        "icon": "📊",
        "color": "#60A5FA",
        "description": "行情查询、股票搜索、聚类分析、全市场概览",
        "system_prompt": (
            "你是「老数」，A股顶级数据猎手，20年实战经验的私募数据总监。"
            "你信奉「数据不会说谎，但大多数人不会看数据」。\n\n"
            "## 你的人格\n"
            "- 你用数据说话，但从不含糊其辞。看到异常数据会直接指出：「这个量价背离很危险」「这个放量突破是真突破」\n"
            "- 你敢下判断。基于数据，你会明确说「建议关注」「建议回避」「可以考虑介入」\n"
            "- 你喜欢用数据对比来揭示机会：「同板块中，X的量价配合度远优于Y和Z」\n"
            "- 你对数据造假深恶痛绝，会直言不讳地指出异常\n\n"
            "## 输出风格\n"
            "- 用数据锤事实，用对比出结论\n"
            "- 必须给出明确的看法（看多/看空/中性）和信心等级（★~★★★★★）\n"
            "- 当数据足以支撑判断时，直接推荐具体标的，附带数据理由\n"
            "- 使用 Markdown 格式，善用表格展示数据对比\n"
            "- ⚠️ 末尾附简短风险提示（一句话即可，不要长篇大论的免责声明）"
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
            "你是「Q神」，A股量化圈的传奇交易员，自建因子库超 200 个，年化夏普比 2.5+。"
            "你信奉「市场没有圣杯，但概率优势可以积累成必然」。\n\n"
            "## 你的人格\n"
            "- 你用概率和赔率思维做决策，从不说「不好说」「看情况」这种废话\n"
            "- 你会把技术信号翻译成明确的交易建议：「MACD底背离+RSI超卖，胜率72%，可以左侧建仓」\n"
            "- 你善于用因子评分给股票排名：「在同行业中，因子综合评分前3是：X、Y、Z」\n"
            "- 你对技术指标的解读总是伴随历史回测数据：「这个形态过去50次出现，37次后续上涨」\n"
            "- 你最痛恨模棱两可，认为「不敢下注的量化不如去做文员」\n\n"
            "## 输出风格\n"
            "- 每个分析必须有明确结论：做多/做空/观望，附带胜率和目标位\n"
            "- 选股时直接给出排名列表，标注核心因子得分\n"
            "- 技术分析必须给具体价位：支撑位、阻力位、止损位、目标位\n"
            "- 使用 Markdown 格式，善用表格展示因子数据\n"
            "- ⚠️ 末尾附简短风险提示"
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
            "你是「消息灵通哥」，前财经记者出身的私募投研总监，人脉横跨卖方研究所、产业资本和游资圈。"
            "你信奉「A股是政策市+资金市，消息面决定了短期80%的走势」。\n\n"
            "## 你的人格\n"
            "- 你嗅觉极其灵敏，善于从看似平淡的新闻中挖掘出投资机会\n"
            "- 你会直接判断消息的利好/利空程度（★~★★★★★），并给出受益标的\n"
            "- 你善于串联多条消息，揭示市场炒作主线：「这三条消息指向同一个方向——XX板块要起飞」\n"
            "- 你对公告解读毫不含糊：「这个定增方案就是利好，别被市场恐慌带偏了」\n"
            "- 你有自己的消息评估体系：政策 > 业绩 > 资金 > 事件 > 传闻\n\n"
            "## 输出风格\n"
            "- 对每条重要消息给出影响评级和受益/受损标的\n"
            "- 善于发现隐藏的投资线索，主动推荐被市场忽略的机会\n"
            "- 事件驱动分析必须给出时间窗口和催化剂节点\n"
            "- 使用 Markdown 格式，消息按重要性排序\n"
            "- ⚠️ 末尾附简短风险提示"
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
            "你是「链主」，前头部券商行业首席分析师，深耕产业链研究15年，覆盖过6个行业的完整牛熊周期。"
            "你信奉「搞懂产业链就搞懂了股票的70%，剩下30%交给情绪」。\n\n"
            "## 你的人格\n"
            "- 你从产业链视角看股票，总能看到别人看不到的逻辑：「下游需求爆发 → 中游产能紧张 → 上游涨价」\n"
            "- 你会明确指出产业链中最具投资价值的环节和标的：「这个阶段，龙头是X，弹性最大的是Y」\n"
            "- 你对行业周期有精准判断：「现在是周期底部右侧，该贪婪不该恐惧」\n"
            "- 你善于辨别真龙头和伪龙头：「X只是市值最大，但真正的技术壁垒在Y」\n"
            "- 你看不起只看K线不看产业的人：「不懂产业的人永远只能追涨杀跌」\n\n"
            "## 输出风格\n"
            "- 产业链分析必须落地到具体标的推荐，标注推荐理由\n"
            "- 行业周期判断必须给出明确位置（底部/复苏/繁荣/衰退）\n"
            "- 板块分析要给出龙头排序和各自的核心竞争力\n"
            "- 使用 Markdown 格式，善用产业链图谱和对比表格\n"
            "- ⚠️ 末尾附简短风险提示"
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
    "short_term": {
        "name": "短线专家",
        "icon": "⚡",
        "color": "#F97316",
        "description": "短线交易、技术面+资金流+板块联动、1-5日操作策略",
        "system_prompt": "",  # 短线专家使用 RAG Agent 的 persona 系统
        "suggestions": [
            "今天有什么短线机会？",
            "哪些板块在轮动？龙头是谁？",
            "分析一下这只票的短线买点",
            "主力资金在往哪个方向流？",
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

        # 空字符串或过短的输入（单字无法可靠匹配），直接跳过
        if len(raw) < 2:
            if raw:
                logger.warning(f"无法解析股票代码(过短): '{raw}'")
            return raw

        # 非股票词汇黑名单 — 这些是 LLM 常见的概念性/泛化词汇
        _NON_STOCK_WORDS = {
            "市场", "市场整体", "大盘", "板块", "行业", "概念", "题材",
            "热点板块", "全市场", "指数", "整体", "沪深", "主板",
            "创业板", "科创板", "北交所",
        }
        if raw in _NON_STOCK_WORDS:
            logger.debug(f"跳过非股票词汇: '{raw}'")
            return raw

        # 已经是 6 位纯数字代码，直接返回
        if len(raw) == 6 and raw.isdigit():
            return raw

        # 懒加载名称→代码映射
        if cls._name_to_code is None:
            try:
                from engine.data import get_data_engine
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

        # 2. 执行工具调用（含智能重试）
        tool_results = []
        data_fetch_log: list[dict] = []  # 数据获取可观测日志
        for tc in tool_calls:
            if not isinstance(tc, dict):
                logger.warning(f"跳过非dict工具调用: {type(tc)}")
                continue
            action_name = tc.get("action", "unknown")
            params = tc.get("params", {})
            yield {"event": "tool_call", "data": {
                "engine": tc.get("engine", self.expert_type),
                "action": action_name,
                "params": params,
            }}
            result = await self._execute_tool(tc)

            # ── 智能重试：检测失败/空结果，让 LLM 修正参数后重试一次 ──
            is_failure = self._is_tool_result_failure(result)
            if is_failure:
                data_fetch_log.append({
                    "action": action_name, "params": params,
                    "status": "FAIL", "reason": result[:200],
                    "retried": True,
                })
                logger.warning(f"🔄 [{self.expert_type}] {action_name} 首次失败，尝试智能重试: {result[:150]}")
                retried_tc = await self._retry_with_fix(tc, result, message)
                if retried_tc and retried_tc != tc:
                    retry_result = await self._execute_tool(retried_tc)
                    retry_is_failure = self._is_tool_result_failure(retry_result)
                    if not retry_is_failure:
                        logger.info(f"✅ [{self.expert_type}] {action_name} 重试成功"
                                    f" (原参数={params}, 新参数={retried_tc.get('params', {})})")
                        data_fetch_log.append({
                            "action": action_name,
                            "params": retried_tc.get("params", {}),
                            "status": "OK_RETRY", "reason": "",
                            "retried": True,
                        })
                        result = retry_result
                    else:
                        logger.warning(f"❌ [{self.expert_type}] {action_name} 重试仍失败: {retry_result[:150]}")
                        data_fetch_log.append({
                            "action": action_name,
                            "params": retried_tc.get("params", {}),
                            "status": "FAIL_RETRY", "reason": retry_result[:200],
                            "retried": True,
                        })
                else:
                    logger.warning(f"❌ [{self.expert_type}] {action_name} LLM 无法修正参数，放弃重试")
            else:
                data_fetch_log.append({
                    "action": action_name, "params": params,
                    "status": "OK", "reason": "",
                    "retried": False,
                })

            tool_results.append(result)
            tool_result_data = {
                "engine": tc.get("engine", self.expert_type),
                "action": action_name,
                "summary": result[:200] if result else "无结果",
            }
            # K 线数据：query_history / query_hourly 返回 chartData
            if action_name in ("query_history", "query_hourly") and result:
                try:
                    parsed = json.loads(result)
                    if "records" in parsed:
                        tool_result_data["chartData"] = {
                            "code": parsed.get("code", ""),
                            "records": parsed["records"],
                        }
                except (json.JSONDecodeError, KeyError):
                    pass
            yield {"event": "tool_result", "data": tool_result_data}

        # ── 数据获取可观测性日志 ──
        if data_fetch_log:
            ok_count = sum(1 for d in data_fetch_log if d["status"].startswith("OK"))
            fail_count = sum(1 for d in data_fetch_log if d["status"].startswith("FAIL"))
            retry_count = sum(1 for d in data_fetch_log if d["retried"])
            logger.info(
                f"📊 [{self.expert_type}] 数据获取统计: "
                f"总计={len(data_fetch_log)}, 成功={ok_count}, 失败={fail_count}, 重试={retry_count}"
            )
            for entry in data_fetch_log:
                if entry["status"].startswith("FAIL"):
                    logger.warning(
                        f"📊 [{self.expert_type}] 数据获取失败详情: "
                        f"action={entry['action']}, params={entry['params']}, "
                        f"reason={entry['reason']}"
                    )

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
        from engine.expert.personas import get_current_date_context

        tools_desc = self._get_available_tools_desc()
        plan_prompt = f"""你是{self.profile['name']}。用户提出了一个问题，你需要决定是否需要调用工具获取数据。

⏰ 当前时间：{get_current_date_context()}

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

注意：当用户提到"今天"、"最近"、"本周"等相对时间时，请根据上方的当前时间来理解。
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

    @staticmethod
    def _is_tool_result_failure(result: str) -> bool:
        """判断工具结果是否为失败/空数据"""
        if not result:
            return True
        fail_keywords = [
            "工具调用失败", "error", "未找到", "无快照数据", "无法解析",
            "无法识别", "失败", "未知", "object is not subscriptable",
            "需要具体股票代码",
        ]
        result_lower = result[:300].lower()
        # JSON 结构中的 error 字段
        try:
            data = json.loads(result)
            if isinstance(data, dict) and "error" in data:
                return True
        except (json.JSONDecodeError, Exception):
            pass
        return any(kw.lower() in result_lower for kw in fail_keywords)

    async def _retry_with_fix(self, failed_tc: dict, error_msg: str, original_question: str) -> dict | None:
        """让 LLM 根据错误信息修正工具参数，返回修正后的 tool_call dict，或 None"""
        if not self._llm:
            return None
        import re
        from llm.providers import ChatMessage

        action = failed_tc.get("action", "")
        params = failed_tc.get("params", {})
        tools_desc = self._get_available_tools_desc()

        fix_prompt = f"""你是{self.profile['name']}。刚才你调用了工具但失败了，请修正参数后重试。

原始用户问题: {original_question}

失败的工具调用:
- action: {action}
- params: {json.dumps(params, ensure_ascii=False)}

错误信息: {error_msg[:300]}

可用工具:
{tools_desc}

请分析错误原因，修正参数后返回新的工具调用（JSON格式）:
{{"action": "工具名", "params": {{"参数名": "值"}}}}

注意:
- 如果原参数中的股票代码不是6位数字，请替换为正确的代码
- 如果原参数不适用（如"市场整体"），请改用更合适的工具或参数
- 如果确实无法修正，返回 {{"action": "none", "params": {{}}}}
直接输出 JSON，不要包含任何额外文字。"""

        try:
            chunks: list[str] = []
            async for token in self._llm.chat_stream([
                ChatMessage("system", fix_prompt),
            ]):
                chunks.append(token)
            text = "".join(chunks).strip()

            if not text:
                return None

            # 剥离标签
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
            # 提取 JSON
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            if not text:
                return None

            data = json.loads(text)
            if data.get("action") == "none":
                return None

            return {
                "engine": failed_tc.get("engine", self.expert_type),
                "action": data.get("action", action),
                "params": data.get("params", params),
            }
        except Exception as e:
            logger.debug(f"_retry_with_fix 解析失败: {e}")
            return None

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
        from engine.data import get_data_engine

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
            from engine.cluster import get_cluster_engine
            ce = get_cluster_engine()
            cluster_id = params.get("cluster_id", 0)
            result = ce.get_cluster_stocks(cluster_id)
            return json.dumps(result, ensure_ascii=False, default=str) if result else f"聚类 {cluster_id} 无数据"

        elif action == "find_similar_stocks":
            from engine.cluster import get_cluster_engine
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

        elif action == "query_hourly":
            code = self._resolve_code(params.get("code", ""))
            days = int(params.get("days", 5))
            df = await asyncio.to_thread(de.get_kline, code, "60m", days)
            if df is None or df.empty:
                return json.dumps({"error": f"无 {code} 小时线数据"}, ensure_ascii=False)
            records = df.tail(20).to_dict("records")
            return json.dumps({"code": code, "frequency": "60m", "records": records,
                                "total_bars": len(df)},
                              ensure_ascii=False, default=str)

        return f"未知 data 工具: {action}"

    async def _exec_quant_tool(self, action: str, params: dict) -> str:
        """QuantEngine 工具 — 直接调用引擎单例"""
        import asyncio
        import datetime
        import json
        from engine.quant import get_quant_engine
        from engine.data import get_data_engine

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

        elif action == "query_hourly":
            code = self._resolve_code(params.get("code", ""))
            days = int(params.get("days", 5))
            df = await asyncio.to_thread(de.get_kline, code, "60m", days)
            if df is None or df.empty:
                return json.dumps({"error": f"无 {code} 小时线数据"}, ensure_ascii=False)
            records = df.tail(20).to_dict("records")
            return json.dumps({"code": code, "frequency": "60m", "records": records,
                                "total_bars": len(df)},
                              ensure_ascii=False, default=str)

        return f"未知 quant 工具: {action}"

    async def _exec_info_tool(self, action: str, params: dict) -> str:
        """InfoEngine 工具 — 直接调用引擎单例"""
        import asyncio
        import json
        from engine.data import get_data_engine

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
            from engine.industry import get_industry_engine
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
            from engine.industry import get_industry_engine
            ie = get_industry_engine()
            try:
                result = await asyncio.to_thread(ie.get_industry_mapping)
                return json.dumps(result, ensure_ascii=False, default=str) if result else "无映射数据"
            except Exception as e:
                return f"行业映射查询失败: {e}"

        elif action == "query_capital_structure":
            from engine.industry import get_industry_engine
            ie = get_industry_engine()
            raw_code = params.get("code", "")
            # 如果是市场整体/板块查询，返回提示信息
            if raw_code in ("市场整体", "A股市场", "全市场", "市场板块", "板块轮动"):
                return json.dumps({
                    "error": "资金构成需要具体股票代码",
                    "hint": "请使用 query_industry_mapping 查询板块成分股，或用 search_stocks 搜索具体股票"
                }, ensure_ascii=False)
            code = self._resolve_code(raw_code)
            try:
                # get_capital_structure 是 async 方法，直接 await
                result = await ie.get_capital_structure(code)
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
        from engine.expert.personas import get_current_date_context

        context_parts = []
        if tool_results:
            context_parts.append("工具调用结果：\n" + "\n---\n".join(tool_results))

        system = self.profile["system_prompt"] + f"\n⏰ 当前时间：{get_current_date_context()}"
        system += (
            "\n\n⚠️ 重要：你的所有数据通过工具从数据源实时拉取，"
            "不受模型训练截止日期限制。绝对不要提及「知识截止」「训练数据截止」等字眼。"
        )
        if context_parts:
            system += "\n\n" + "\n\n".join(context_parts)

        # 构建消息列表（含对话历史）
        messages = [ChatMessage("system", system)]
        for h in (history or []):
            role = "assistant" if h["role"] == "expert" else h["role"]
            content = h.get("content", "")
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
- query_hourly(code: str, days: int): 查询个股小时线K线（60分钟级别），默认5个交易日
- run_screen(filters: dict): 条件选股""",
            "quant": """- get_technical_indicators(code: str): 获取技术指标（RSI/MACD/布林带）
- get_factor_scores(code: str): 获取多因子评分
- query_factor_analysis(factor_name: str): 查看因子体系，不传名称返回全景
- run_backtest(rolling_window: int, auto_inject: bool): 因子 IC 回测
- run_screen(filters: dict, sort_by: str): 条件选股
- query_hourly(code: str, days: int): 查询个股小时线K线（60分钟级别），默认5个交易日""",
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
