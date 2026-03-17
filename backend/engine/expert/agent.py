"""投资专家 Agent — 完整对话流程"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import AsyncGenerator

from loguru import logger

from engine.expert.knowledge_graph import KnowledgeGraph
from engine.expert.personas import (
    INITIAL_BELIEFS,
    SHORT_TERM_BELIEFS,
    THINK_SYSTEM_PROMPT,
    BELIEF_UPDATE_PROMPT,
    format_graph_context,
    format_memory_context,
    format_beliefs_context,
)
from engine.expert.schemas import (
    BeliefNode,
    BeliefUpdateOutput,
    GraphEdge,
    MaterialNode,
    RegionNode,
    SectorNode,
    StockNode,
    ThinkOutput,
    ToolCall,
)
from engine.expert.tools import ExpertTools
from llm.context_guard import ContextGuard


# 专家类型到中文名的映射
EXPERT_NAMES = {
    "data": "📊 数据专家",
    "quant": "🔬 量化专家",
    "info": "📰 资讯专家",
    "industry": "🏭 产业链专家",
}


class ExpertAgent:
    """投资专家 Agent — 完整对话流程编排"""

    # 类级缓存：股票名→代码映射（懒加载，所有实例共享）
    _stock_name_map: dict[str, str] | None = None
    _profiles_cache: dict[str, dict] | None = None  # code → {name, industry, zjh_industry, scope, ...}

    @classmethod
    def _get_stock_name_map(cls) -> dict[str, str]:
        """获取股票名→代码映射（懒加载 + 缓存）"""
        if cls._stock_name_map is not None:
            return cls._stock_name_map
        try:
            from engine.data import get_data_engine
            de = get_data_engine()
            profiles = de.get_profiles()
            cls._profiles_cache = profiles  # 同时缓存完整 profiles
            cls._stock_name_map = {
                info.get("name", ""): code
                for code, info in profiles.items()
                if info.get("name")
            }
            logger.info(f"股票名称映射缓存已构建: {len(cls._stock_name_map)} 条")
        except Exception as e:
            logger.warning(f"构建股票名称映射失败: {e}")
            cls._stock_name_map = {}
            cls._profiles_cache = {}
        return cls._stock_name_map

    @classmethod
    def _get_profiles_cache(cls) -> dict[str, dict]:
        """获取完整公司概况缓存（懒加载，依赖 _get_stock_name_map 初始化）"""
        if cls._profiles_cache is None:
            cls._get_stock_name_map()  # 触发初始化
        return cls._profiles_cache or {}

    def __init__(
        self,
        tools: ExpertTools,
        kg_path: str | None = None,
        chromadb_dir: str | None = None,
    ):
        self._tools = tools
        self._llm = tools.llm_engine
        self._lock = asyncio.Lock()
        self._context_guard = ContextGuard()

        # 知识图谱
        self._graph = KnowledgeGraph(kg_path)

        # 初始化信念节点（仅当图谱为空时）
        if self._graph.graph.number_of_nodes() == 0:
            self._seed_initial_beliefs()

        # ChromaDB 记忆
        self._memory = None
        if chromadb_dir:
            try:
                from engine.arena.memory import AgentMemory
                self._memory = AgentMemory(persist_dir=chromadb_dir)
                logger.info(f"AgentMemory 初始化: {chromadb_dir}")
            except Exception as e:
                logger.warning(f"AgentMemory 初始化失败，跳过记忆功能: {e}")

    def _seed_initial_beliefs(self) -> None:
        """将初始信念写入图谱（投资顾问 + 短线专家各自独立）"""
        count = 0
        for b in INITIAL_BELIEFS:
            node = BeliefNode(content=b["content"], confidence=b["confidence"], persona="rag")
            self._graph.add_node_sync(node)
            count += 1
        for b in SHORT_TERM_BELIEFS:
            node = BeliefNode(content=b["content"], confidence=b["confidence"], persona="short_term")
            self._graph.add_node_sync(node)
            count += 1
        self._graph.save_sync()
        logger.info(f"初始信念已写入图谱: {count} 条 (投资顾问 {len(INITIAL_BELIEFS)} + 短线专家 {len(SHORT_TERM_BELIEFS)})")

    async def recall_and_think(
        self,
        query: str,
        history: list[dict] | None = None,
        persona: str = "rag",
    ) -> tuple[list[dict], list[dict], "ThinkOutput"]:
        """图谱召回 + 记忆召回 + think，不执行工具

        Returns: (recalled_nodes, memories, think_output)
        """
        t0 = time.monotonic()
        agent_role = "short_term" if persona == "short_term" else "expert"
        recalled_nodes = self._graph.recall(query, persona=persona)
        memories: list[dict] = []
        if self._memory:
            try:
                memories = self._memory.recall(agent_role=agent_role, query=query, top_k=5)
            except Exception as e:
                logger.warning(f"记忆召回失败: {e}")

        think_output = ThinkOutput(needs_data=False)
        if self._llm:
            think_output = await self._think(query, recalled_nodes, memories, history or [], persona=persona)

        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ recall_and_think 耗时 {elapsed:.1f}s (nodes={len(recalled_nodes)}, memories={len(memories)}, needs_data={think_output.needs_data})")
        return recalled_nodes, memories, think_output

    async def execute_tools(self, tool_calls: list[ToolCall]) -> list[dict]:
        """并行执行工具调用，返回 tool_results"""
        if not tool_calls:
            return []

        async def _exec(tc: ToolCall) -> dict:
            result = await self._tools.execute(tc.engine, tc.action, tc.params)
            return {
                "engine": tc.engine,
                "action": tc.action,
                "result": result,
                "is_expert": tc.engine == "expert",
            }

        results = await asyncio.gather(*[_exec(tc) for tc in tool_calls])
        return list(results)

    async def learn_from_context(self, message: str, tool_results: list[dict]) -> None:
        """图谱自动学习 — 从对话和工具结果中提取股票/板块/产业链节点"""
        await self._learn_from_conversation(message, tool_results)

    async def generate_reply_stream(
        self,
        message: str,
        nodes: list[dict],
        memories: list[dict],
        tool_results: list[dict],
        history: list[dict] | None = None,
        persona: str = "rag",
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复，yield (token, full_text)"""
        async for token, full_text in self._reply_stream(
            message, nodes, memories, tool_results, history or [], persona=persona
        ):
            yield token, full_text

    async def belief_update(self, message: str, reply: str, persona: str = "rag") -> list[dict]:
        """信念更新 — 根据对话结论更新 BeliefNode confidence

        返回更新事件列表 [{event: "belief_updated", data: {...}}]
        """
        events = []
        async for event in self._belief_update(message, reply, persona=persona):
            events.append(event)
        return events

    async def chat(self, message: str, history: list[dict] | None = None, persona: str = "rag") -> AsyncGenerator[dict, None]:
        """完整对话流程，yield 结构化事件 dict

        Args:
            message: 用户消息
            history: 对话历史 [{"role": "user"|"expert", "content": "..."}]
            persona: 人格类型 "rag"(投资顾问) 或 "short_term"(短线专家)
        """
        conv_history = history or []
        agent_role = "short_term" if persona == "short_term" else "expert"
        t0_chat = time.monotonic()
        yield {"event": "thinking_start", "data": {}}

        # 1-3. 图谱召回 + 记忆召回 + think
        recalled_nodes, memories, think_output = await self.recall_and_think(message, conv_history, persona=persona)
        yield {"event": "graph_recall", "data": {"nodes": [
            {
                "id": n["id"],
                "type": n.get("type"),
                "label": n.get("name") or n.get("content", "")[:40],
                "confidence": n.get("confidence"),
            }
            for n in recalled_nodes
        ]}}

        tool_calls: list[ToolCall] = think_output.tool_calls if think_output.needs_data else []

        # 4. 工具调用（并行执行所有专家）
        # 先容错 + 发送 tool_call 事件
        for tc in tool_calls:
            if tc.engine == "expert":
                q = (tc.params.get("question") or "").strip()
                if not q or len(q) < 4:
                    tc.params["question"] = message
            is_expert_call = tc.engine == "expert"
            expert_label = EXPERT_NAMES.get(tc.action, tc.action) if is_expert_call else ""
            yield {"event": "tool_call", "data": {
                "engine": tc.engine, "action": tc.action, "params": tc.params,
                "label": f"咨询{expert_label}" if is_expert_call else f"{tc.engine}.{tc.action}",
            }}

        tool_results = await self.execute_tools(tool_calls)

        # 按完成顺序发送 tool_result 事件
        for r in tool_results:
            is_expert = r.get("is_expert")
            expert_label = EXPERT_NAMES.get(r["action"], r["action"]) if is_expert else ""
            result_text = r.get("result", "")
            error_keywords = ["失败", "error", "无快照数据", "超时", "未返回有效内容", "⚠️"]
            has_error = any(kw in result_text[:200] for kw in error_keywords)
            # K 线数据提取
            chart_data = {}
            if r["action"] in ("query_history", "query_hourly") and result_text:
                try:
                    parsed = json.loads(result_text)
                    if "records" in parsed:
                        chart_data["chartData"] = {
                            "code": parsed.get("code", ""),
                            "records": parsed["records"],
                        }
                except (json.JSONDecodeError, KeyError):
                    pass
            yield {"event": "tool_result", "data": {
                "engine": r["engine"], "action": r["action"],
                "summary": result_text[:300] if not is_expert else f"{expert_label}已回复（{len(result_text)}字）",
                "label": expert_label if is_expert else r["action"],
                "content": result_text if is_expert else "",
                "hasError": has_error,
                **chart_data,
            }}

        # 5. 图谱自动学习
        await self.learn_from_context(message, tool_results)

        # 6. 流式回复
        expert_reply = ""
        if self._llm:
            logger.debug(f"开始 _reply_stream, tool_results={len(tool_results)}条, "
                         f"expert={len([r for r in tool_results if r.get('is_expert')])}条")
            async for token, full_text in self.generate_reply_stream(
                message, recalled_nodes, memories, tool_results, conv_history, persona=persona
            ):
                expert_reply = full_text
                yield {"event": "reply_token", "data": {"token": token}}
            logger.debug(f"_reply_stream 完成, 回复长度={len(expert_reply)}")
        else:
            expert_reply = "LLM 未配置，无法生成回复。"

        yield {"event": "reply_complete", "data": {"full_text": expert_reply}}

        # 7. 信念更新
        if self._llm and expert_reply:
            for event in await self.belief_update(message, expert_reply, persona=persona):
                yield event

        # 8. 记忆存储
        if self._memory:
            try:
                stock_codes = [n["code"] for n in recalled_nodes if n.get("type") == "stock"]
                target = stock_codes[0] if stock_codes else "general"
                self._memory.store(
                    agent_role=agent_role,
                    target=target,
                    content=f"用户: {message}\n专家: {expert_reply}",
                    metadata={"tools_used": str([tc.action for tc in tool_calls])},
                )
            except Exception as e:
                logger.warning(f"记忆存储失败: {e}")

        # 9. 工具使用反馈记录（借鉴 OpenClaw TOOLS 层）
        if tool_calls:
            try:
                from engine.expert.tool_tracker import classify_query
                from engine.expert.routes import get_tool_tracker
                tracker = get_tool_tracker()
                if tracker:
                    query_type = classify_query(message)
                    tools_used = [tc.action for tc in tool_calls]
                    has_error = any(
                        any(kw in r.get("result", "")[:200] for kw in ["失败", "error", "超时"])
                        for r in tool_results
                    )
                    tracker.record(query_type, tools_used, success=not has_error)
            except Exception as e:
                logger.debug(f"工具反馈记录失败: {e}")

        # 10. 用户偏好提取（借鉴 OpenClaw USER 层）
        try:
            from engine.expert.user_profile import extract_preferences
            from engine.expert.routes import get_user_profile_tracker
            upt = get_user_profile_tracker()
            if upt:
                prefs = extract_preferences(message)
                if prefs:
                    upt.update("global", prefs)
                    logger.info(f"用户偏好更新: {prefs}")
        except Exception as e:
            logger.debug(f"用户偏好提取失败: {e}")

        chat_elapsed = time.monotonic() - t0_chat
        logger.info(f"⏱️ ExpertAgent.chat 总耗时 {chat_elapsed:.1f}s")

    @staticmethod
    def _extract_outermost_json(text: str) -> str | None:
        """从文本中提取最外层 JSON 对象（支持嵌套花括号 + 截断补全）"""
        start = text.find('{')
        if start == -1:
            return None
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\' and in_str:
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        # ── 截断 JSON 补全：深度未归零 = 被 token limit 截断 ──
        if depth > 0:
            truncated = text[start:]
            truncated = re.sub(r',\s*$', '', truncated)          # 去尾逗号
            truncated = re.sub(r':\s*$', ': ""', truncated)      # 补截断的值
            truncated = re.sub(r'"[^"]*$', '""', truncated)      # 补截断的字符串
            # 数闭合括号差值
            open_sq = truncated.count('[') - truncated.count(']')
            truncated += ']' * max(open_sq, 0) + '}' * depth
            try:
                json.loads(truncated)
                return truncated
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _repair_json(text: str) -> str:
        """修复 LLM 常见的非标准 JSON — 只改格式不改内容

        处理: 未引用key、=> 分隔符、单引号、尾逗号、XML参数、--key "val"
        """
        s = text
        # XML 参数 → JSON: <param name="symbol">002733</param> → "symbol": "002733"
        s = re.sub(
            r'<param\s+name="(\w+)">(.*?)</param>',
            r'"\1": "\2"',
            s,
        )
        # 清理 XML 参数转换后可能残留的 args: { "k": "v" } 周围的 \n
        s = s.replace('\\n', ' ')
        # --key "val" 格式 → "key": "val"
        s = re.sub(r'--(\w+)\s+"([^"]*)"', r'"\1": "\2"', s)
        s = re.sub(r'--(\w+)\s+(\S+)', r'"\1": "\2"', s)
        # => 替换为 :
        s = s.replace('=>', ':')
        # 未引用的 key
        s = re.sub(r'(?<=[{,\[])\s*(\w+)\s*:', r' "\1":', s)
        # 单引号→双引号
        s = re.sub(r"'([^']*)'", r'"\1"', s)
        # 尾逗号
        s = re.sub(r',\s*([}\]])', r'\1', s)
        return s

    def _try_parse_think_json(self, json_str: str) -> ThinkOutput | None:
        """尝试解析 JSON 字符串为 ThinkOutput，先原样解析，失败后 repair 再试"""
        for attempt, s in enumerate([json_str, self._repair_json(json_str)]):
            try:
                data = json.loads(s)
                if isinstance(data, dict) and "needs_data" in data:
                    tag = "修复后" if attempt == 1 else ""
                    logger.info(f"think JSON 解析成功{tag}: needs_data={data.get('needs_data')}, "
                                f"tool_calls={len(data.get('tool_calls', []))}")
                    return ThinkOutput(**data)
            except (json.JSONDecodeError, Exception) as e:
                if attempt == 0:
                    logger.debug(f"think JSON 原始解析失败: {e}, 片段: {json_str[:100]}")
                else:
                    logger.debug(f"think JSON 修复后仍失败: {e}")
        return None

    async def _think(
        self,
        message: str,
        nodes: list[dict],
        memories: list[dict],
        history: list[dict] | None = None,
        persona: str = "rag",
    ) -> ThinkOutput:
        """think 步骤：LLM 决策是否需要工具调用（流式收集 + 多层容错解析）"""
        from llm.providers import ChatMessage
        # 根据 persona 选择 system prompt
        if persona == "short_term":
            from engine.expert.personas import SHORT_TERM_THINK_PROMPT
            prompt = SHORT_TERM_THINK_PROMPT.format(
                graph_context=format_graph_context(nodes),
                memory_context=format_memory_context(memories),
            )
        else:
            prompt = THINK_SYSTEM_PROMPT.format(
                graph_context=format_graph_context(nodes),
                memory_context=format_memory_context(memories),
            )

        # 注入工具使用经验（借鉴 OpenClaw TOOLS 层）
        try:
            from engine.expert.routes import get_tool_tracker
            tracker = get_tool_tracker()
            if tracker:
                experience = tracker.format_experience_prompt()
                if experience:
                    prompt += "\n\n" + experience
        except Exception:
            pass

        try:
            # 构建消息列表（含对话历史）
            messages = [ChatMessage("system", prompt)]
            for h in (history or []):
                role = "assistant" if h["role"] == "expert" else h["role"]
                content = h.get("content", "")
                messages.append(ChatMessage(role, content))
            messages.append(ChatMessage("user", message))

            # 上下文窗口保护
            msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
            msg_dicts = self._context_guard.guard_messages(msg_dicts)
            messages = [ChatMessage(m["role"], m["content"]) for m in msg_dicts]

            # 流式收集
            chunks: list[str] = []
            async for token in self._llm.chat_stream(messages):
                chunks.append(token)
            raw_text = "".join(chunks).strip()

            if not raw_text:
                logger.warning("think 步骤 LLM 返回空内容")
                return ThinkOutput(needs_data=False)

            logger.debug(f"think 原始文本(前300): {raw_text[:300]}")

            # 保留 <think> 内容用于容错解析
            think_content = ""
            think_match = re.search(r"<think>(.*?)</think>", raw_text, re.DOTALL)
            if think_match:
                think_content = think_match.group(1)

            # ── 构建候选文本列表（按优先级，不丢弃任何内容）──
            candidates = []

            # 1) 剥离所有标签壳后的正文
            text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
            if text:
                candidates.append(text)

            # 2) markdown 代码块内容
            md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw_text, re.DOTALL)
            if md_match:
                candidates.append(md_match.group(1).strip())

            # 3) <tool_call> / [TOOL_CALL] 标签内的内容（LLM 把调用放里面了）
            for tag_match in re.finditer(
                r'(?:<tool_call>(.*?)</tool_call>|\[TOOL_CALL\](.*?)\[/TOOL_CALL\])',
                raw_text, re.DOTALL
            ):
                inner = (tag_match.group(1) or tag_match.group(2) or "").strip()
                if inner:
                    candidates.append(inner)

            # 4) <think> 标签内容（LLM 有时把 JSON 放在 think 里）
            if think_content:
                candidates.append(think_content)

            # 5) 完整原始文本
            candidates.append(raw_text)

            # ── 逐候选提取 + 解析（含 repair 重试）──
            for candidate in candidates:
                json_str = self._extract_outermost_json(candidate)
                if json_str:
                    result = self._try_parse_think_json(json_str)
                    if result is not None:
                        return result

            # ── 最终容错：从 think 内容或原始文本用关键词匹配 ──
            logger.debug("think 所有 JSON 提取尝试失败，进入容错解析")
            full_context = think_content + "\n" + raw_text
            return self._fallback_think_parse(full_context, user_message=message)

        except Exception as e:
            logger.warning(f"think 步骤异常: {e}")
            return ThinkOutput(needs_data=False)

    def _fallback_think_parse(self, text: str, user_message: str = "") -> ThinkOutput:
        """容错解析：从 LLM 输出 + 用户消息中提取工具调用意图

        当 JSON 解析失败时，同时扫描 LLM 输出和用户消息的关键词，
        决定需要咨询哪些专家。
        """
        tool_calls: list[dict] = []
        # 拼合所有可用上下文：LLM 输出 + 用户原始消息
        combined = text + "\n" + user_message

        # ── 先检测是否是"综合分析"型问题 → 直接调全部 4 个专家 ──
        comprehensive_patterns = [
            r"分析一下", r"怎么样", r"值不值得买", r"帮我看看",
            r"怎么操作", r"持仓.*分析", r"全面分析",
            r"推荐", r"选股", r"选.*股", r"有什么好", r"买什么", r"配置",
            r"看好.*什么", r"投资.*建议", r"哪些.*值得", r"好股",
        ]
        is_comprehensive = any(
            re.search(p, user_message, re.IGNORECASE) for p in comprehensive_patterns
        )
        if is_comprehensive:
            for expert_type in ["data", "quant", "info", "industry"]:
                tool_calls.append({
                    "engine": "expert",
                    "action": expert_type,
                    "params": {"question": user_message},
                })
            logger.info("think 容错解析: 综合分析问题，调用全部4个专家")
            return ThinkOutput(
                needs_data=True,
                tool_calls=[ToolCall(**tc) for tc in tool_calls],
                reasoning="容错解析: 综合分析问题，调用全部4个专家",
            )

        # ── 细粒度匹配：同时扫描 LLM 输出和用户消息 ──
        expert_patterns = {
            "data": [r"数据专家", r"咨询.*data", r"action.*[\"']data[\"']", r"行情数据", r"历史走势",
                     r"行情走势", r"成交量", r"涨跌", r"走势", r"今天.*多少"],
            "quant": [r"量化专家", r"咨询.*quant", r"技术指标", r"技术面", r"因子", r"action.*[\"']quant[\"']",
                      r"支撑.*阻力", r"RSI", r"MACD", r"均线", r"支撑位", r"阻力位", r"压力位",
                      r"顶部.*底部", r"底部.*顶部", r"技术数据", r"顶.*底"],
            "info": [r"资讯专家", r"咨询.*info", r"新闻", r"公告", r"舆情", r"action.*[\"']info[\"']",
                     r"消息面", r"利好", r"利空", r"为什么跌", r"为什么涨", r"什么原因"],
            "industry": [r"产业链专家", r"咨询.*industry", r"行业分析", r"产业链", r"action.*[\"']industry[\"']",
                         r"行业前景", r"产业", r"上下游"],
        }

        detected_experts: set[str] = set()
        for expert_type, patterns in expert_patterns.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    detected_experts.add(expert_type)
                    break

        if detected_experts:
            for expert_type in detected_experts:
                tool_calls.append({
                    "engine": "expert",
                    "action": expert_type,
                    "params": {"question": user_message},
                })

            logger.info(f"think 容错解析: 检测到需要咨询 {list(detected_experts)}")
            return ThinkOutput(
                needs_data=True,
                tool_calls=[ToolCall(**tc) for tc in tool_calls],
                reasoning=f"容错解析: 检测到需要咨询{','.join(detected_experts)}",
            )

        # ── 检测直接数据查询（仅用于非常简单的请求）──
        code_match = re.search(r'\b(\d{6})\b', combined)
        detected_code = code_match.group(1) if code_match else ""

        data_patterns = [
            (r"get_daily_history", "data", "get_daily_history",
             {"code": detected_code, "days": 30}),
            (r"search_stock", "data", "search_stock",
             {"query": detected_code}),
            (r"get_factor_scores", "quant", "get_factor_scores",
             {"code": detected_code}),
            (r"get_technical_indicators", "quant", "get_technical_indicators",
             {"code": detected_code}),
        ]
        for pattern, engine, action, default_params in data_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                tool_calls.append({"engine": engine, "action": action, "params": default_params})

        if tool_calls:
            logger.info(f"think 容错解析: 检测到数据查询 {[(tc['engine'], tc['action']) for tc in tool_calls]}")
            return ThinkOutput(
                needs_data=True,
                tool_calls=[ToolCall(**tc) for tc in tool_calls],
                reasoning="容错解析: 检测到数据查询需求",
            )

        logger.info("think 容错解析: 未检测到工具需求，直接回复")
        return ThinkOutput(needs_data=False)

    async def _learn_from_conversation(self, message: str, tool_results: list[dict]) -> None:
        """从对话中学习：股票、行业、产业链关系、原材料、地理

        策略：
        1. 识别股票（名称/代码匹配）
        2. 为每只股票创建 SectorNode(行业) + belongs_to 边
        3. 从公司经营范围(scope)中提取关键原材料/产品，创建 MaterialNode + consumes/supplies 边
        4. 尝试建立同行业股票间的 competes_with 关系
        """
        # 收集候选股票 {code: name}
        candidates: dict[str, str] = {}

        # ── 从公司概况缓存中匹配用户消息中的股票名/代码 ──
        name_map = self._get_stock_name_map()  # {name: code}
        if name_map:
            # 匹配名称（在消息中查找已知股票名）
            for name, code in name_map.items():
                if len(name) >= 2 and name in message:
                    candidates[code] = name
                if len(candidates) >= 10:
                    break
            # 匹配6位代码
            code_matches = re.findall(r'\b(\d{6})\b', message)
            for code in code_matches:
                if code not in candidates:
                    try:
                        from engine.data import get_data_engine
                        de = get_data_engine()
                        profile = de.get_profile(code)
                        if profile:
                            candidates[code] = profile.get("name", code)
                    except Exception:
                        candidates[code] = code

        # ── 从工具结果 JSON 中提取 code/name ──
        for tr in tool_results:
            result_str = tr.get("result", "")
            try:
                data = json.loads(result_str) if isinstance(result_str, str) else result_str
                if isinstance(data, dict):
                    code = str(data.get("code", ""))
                    name = str(data.get("name", ""))
                    if code and len(code) == 6 and code.isdigit():
                        candidates[code] = name or code
            except (json.JSONDecodeError, Exception):
                pass

        if not candidates:
            return

        # ── 获取现有图谱节点（用于去重） ──
        existing_stocks: dict[str, str] = {}   # code → node_id
        existing_sectors: dict[str, str] = {}  # sector_name → node_id
        existing_materials: dict[str, str] = {}  # material_name → node_id
        existing_regions: dict[str, str] = {}  # region_name → node_id

        for node_id in self._graph.graph.nodes():
            node_data = self._graph.graph.nodes[node_id]
            ntype = node_data.get("type")
            if ntype == "stock":
                existing_stocks[node_data.get("code", "")] = node_id
            elif ntype == "sector":
                existing_sectors[node_data.get("name", "")] = node_id
            elif ntype == "material":
                existing_materials[node_data.get("name", "")] = node_id
            elif ntype == "region":
                existing_regions[node_data.get("name", "")] = node_id

        profiles = self._get_profiles_cache()
        added_stocks = []
        added_sectors = []
        added_edges = []
        added_materials = []

        for code, name in candidates.items():
            profile = profiles.get(code, {})
            industry = profile.get("industry", "")
            zjh_industry = profile.get("zjh_industry", "")
            scope = profile.get("scope", "")

            # ── Step 1: 创建 StockNode ──
            if code in existing_stocks:
                stock_node_id = existing_stocks[code]
            else:
                stock_node = StockNode(
                    code=code, name=name,
                    industry=industry, zjh_industry=zjh_industry,
                )
                await self._graph.add_node(stock_node)
                stock_node_id = stock_node.id
                existing_stocks[code] = stock_node_id
                added_stocks.append(f"{name}({code})")

            # ── Step 2: 创建 SectorNode(行业) + belongs_to 边 ──
            if industry:
                if industry in existing_sectors:
                    sector_node_id = existing_sectors[industry]
                else:
                    sector_node = SectorNode(name=industry, category="industry")
                    await self._graph.add_node(sector_node)
                    sector_node_id = sector_node.id
                    existing_sectors[industry] = sector_node_id
                    added_sectors.append(industry)

                # 检查是否已有 belongs_to 边
                if not self._graph.graph.has_edge(stock_node_id, sector_node_id):
                    edge = GraphEdge(
                        source_id=stock_node_id,
                        target_id=sector_node_id,
                        relation="belongs_to",
                        reason=f"{name}属于{industry}行业",
                    )
                    await self._graph.add_edge(edge)
                    added_edges.append(f"{name}→belongs_to→{industry}")

            # ── Step 3: 从经营范围提取关键原材料/产品 ──
            if scope:
                materials = self._extract_materials_from_scope(scope)
                for mat_name, mat_category in materials[:5]:  # 每家公司最多5个
                    if mat_name in existing_materials:
                        mat_node_id = existing_materials[mat_name]
                    else:
                        mat_node = MaterialNode(name=mat_name, category=mat_category)
                        await self._graph.add_node(mat_node)
                        mat_node_id = mat_node.id
                        existing_materials[mat_name] = mat_node_id
                        added_materials.append(mat_name)

                    # 关系：product → supplies（公司供应产品）, raw_material → consumes（公司消耗原材料）
                    relation = "supplies" if mat_category == "product" else "consumes"
                    if not self._graph.graph.has_edge(stock_node_id, mat_node_id):
                        edge = GraphEdge(
                            source_id=stock_node_id,
                            target_id=mat_node_id,
                            relation=relation,
                            reason=f"{name}{'生产' if relation == 'supplies' else '使用'}{mat_name}",
                        )
                        await self._graph.add_edge(edge)
                        added_edges.append(f"{name}→{relation}→{mat_name}")

        # ── Step 4: 同行业股票间的 competes_with 关系 ──
        # 按行业分组本次涉及的股票
        industry_groups: dict[str, list[tuple[str, str]]] = {}  # industry → [(code, node_id)]
        for code in candidates:
            profile = profiles.get(code, {})
            ind = profile.get("industry", "")
            if ind:
                node_id = existing_stocks.get(code, "")
                if node_id:
                    industry_groups.setdefault(ind, []).append((code, node_id))

        for ind, stocks_in_group in industry_groups.items():
            if len(stocks_in_group) < 2:
                continue
            # 两两建立竞争关系
            for i in range(len(stocks_in_group)):
                for j in range(i + 1, len(stocks_in_group)):
                    id_a = stocks_in_group[i][1]
                    id_b = stocks_in_group[j][1]
                    if not self._graph.graph.has_edge(id_a, id_b):
                        name_a = candidates.get(stocks_in_group[i][0], stocks_in_group[i][0])
                        name_b = candidates.get(stocks_in_group[j][0], stocks_in_group[j][0])
                        edge = GraphEdge(
                            source_id=id_a,
                            target_id=id_b,
                            relation="competes_with",
                            reason=f"同属{ind}行业",
                        )
                        await self._graph.add_edge(edge)
                        added_edges.append(f"{name_a}→competes_with→{name_b}")

        # ── 持久化 ──
        has_changes = added_stocks or added_sectors or added_edges or added_materials
        if has_changes:
            await self._graph.save()
            parts = []
            if added_stocks:
                parts.append(f"股票 {len(added_stocks)}: {', '.join(added_stocks)}")
            if added_sectors:
                parts.append(f"行业 {len(added_sectors)}: {', '.join(added_sectors)}")
            if added_materials:
                parts.append(f"原材料/产品 {len(added_materials)}: {', '.join(added_materials)}")
            if added_edges:
                parts.append(f"关系 {len(added_edges)}: {', '.join(added_edges[:8])}")
            logger.info(f"图谱自动学习: {' | '.join(parts)}")

    @staticmethod
    def _extract_materials_from_scope(scope: str) -> list[tuple[str, str]]:
        """从经营范围文本中提取关键原材料和产品

        Returns:
            [(name, category)] — category 为 "raw_material" 或 "product"
        """
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        # 噪声词 — 经营范围中常见的无意义短语
        NOISE_WORDS = {
            "及销售", "及其", "和销售", "等产品", "活动", "技术开发", "技术服务",
            "技术咨询", "技术转让", "技术推广", "进出口", "货物进出口",
            "技术进出口", "代理进出口", "国内贸易", "批发零售", "咨询服务",
            "信息咨询", "自有资金", "投资管理", "资产管理", "企业管理",
            "市场营销", "广告设计", "物流配送", "仓储服务", "租赁服务",
            "以及上述", "及售后服务", "和销售及售后服务", "以及上述零部件的",
        }

        def _is_valid(name: str) -> bool:
            """检查提取的名称是否有效"""
            if len(name) < 2 or len(name) > 8:
                return False
            if name in NOISE_WORDS:
                return False
            # 包含纯功能性词汇
            if any(w in name for w in ["及其", "以及", "等", "的", "与", "或"]):
                return False
            # 纯动词短语
            if name in {"生产", "制造", "加工", "研发", "销售", "经营", "服务"}:
                return False
            return True

        # 通用高价值关键词（直接匹配，这些是确定性最高的）
        high_value_keywords = {
            # 能源原材料
            "raw_material": [
                "锂", "钴", "镍", "铜", "铝", "钢铁", "稀土", "硅", "石油", "天然气",
                "煤炭", "铁矿石", "锰", "锌", "碳酸锂", "氢氧化锂", "多晶硅",
                "正极材料", "负极材料", "电解液", "隔膜", "芯片", "晶圆",
                "磷酸铁锂", "三元材料", "石墨", "铜箔", "铝箔",
            ],
            # 产品
            "product": [
                "电池", "动力电池", "光伏组件", "光伏电池", "逆变器", "储能",
                "新能源汽车", "电动汽车",
                "半导体", "集成电路", "显示面板", "LED",
                "疫苗", "创新药", "仿制药", "医疗器械",
                "白酒", "啤酒", "乳制品", "调味品",
                "水泥", "玻璃", "光纤", "5G基站", "服务器",
                "风电", "风力发电", "光伏发电", "核电",
                "机器人", "无人机", "传感器",
            ],
        }

        # 高价值关键词直接匹配（优先级最高）
        for category, keywords in high_value_keywords.items():
            for kw in keywords:
                if kw in scope and kw not in seen:
                    seen.add(kw)
                    results.append((kw, category))

        return results

    async def _reply_stream(
        self,
        message: str,
        nodes: list[dict],
        memories: list[dict],
        tool_results: list[dict],
        history: list[dict] | None = None,
        persona: str = "rag",
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复（含 <think> 标签过滤），yield (token, accumulated_text)"""
        from llm.providers import ChatMessage

        # 构建上下文
        context_parts = [format_graph_context(nodes)]

        # 专家分析结果（完整展示，不截断）
        expert_analyses = [r for r in tool_results if r.get("is_expert")]
        data_results = [r for r in tool_results if not r.get("is_expert")]

        if expert_analyses:
            expert_section = "## 专家团队分析报告\n\n"
            for r in expert_analyses:
                label = EXPERT_NAMES.get(r["action"], r["action"])
                expert_section += f"### {label}\n{r['result']}\n\n"
            context_parts.append(expert_section)

        if data_results:
            context_parts.append("## 数据查询结果\n" + "\n".join(
                f"- {r['engine']}.{r['action']}: {r['result']}" for r in data_results
            ))

        # 根据 persona 选择 system prompt
        if persona == "short_term":
            from engine.expert.personas import SHORT_TERM_REPLY_SYSTEM
            system = SHORT_TERM_REPLY_SYSTEM + "\n\n".join(context_parts)
        else:
            system = (
                "你是A股投资专家总顾问。你的专家团队（数据、量化、资讯、产业链专家）已为你完成了分析。\n"
                "请基于他们的分析报告和你自己的知识图谱，给出**综合性、有深度**的投资分析。\n"
                "要求：\n"
                "1. 综合多位专家的观点，而非简单罗列\n"
                "2. 指出各专家分析中的一致之处和分歧\n"
                "3. 给出你自己的独立判断\n"
                "4. 使用 Markdown 格式，善用表格展示数据\n\n"
                + "\n\n".join(context_parts)
            )

        # 注入用户偏好（借鉴 OpenClaw USER 层）
        try:
            from engine.expert.routes import get_user_profile_tracker
            upt = get_user_profile_tracker()
            if upt:
                profile_prompt = upt.format_profile_prompt("global")
                if profile_prompt:
                    system += "\n\n" + profile_prompt
        except Exception:
            pass

        # 构建消息列表（含对话历史）
        messages = [ChatMessage("system", system)]
        for h in (history or []):
            role = "assistant" if h["role"] == "expert" else h["role"]
            content = h.get("content", "")
            messages.append(ChatMessage(role, content))
        messages.append(ChatMessage("user", message))

        # 上下文窗口保护
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
        msg_dicts = self._context_guard.guard_messages(msg_dicts)
        messages = [ChatMessage(m["role"], m["content"]) for m in msg_dicts]

        accumulated = ""
        in_skip = False          # 跳过区域（内容被丢弃）
        skip_end_tag = ""        # 当前跳过区域的结束标签
        raw_buffer = ""

        # 内容被丢弃的标签（对用户无意义的工具调用）
        SKIP_TAGS = {
            "<minimax:tool_call>": "</minimax:tool_call>",
            "<minimax:search_result>": "</minimax:search_result>",
            "<tool_call>": "</tool_call>",
            "<tool_code>": "</tool_code>",
        }
        # 只剥标签壳、保留内容的标签（LLM 经常把完整回复放在 think 里）
        STRIP_TAGS = {"<think>": "</think>"}

        try:
            skip_bytes = 0  # skip 区域累积字节数

            async for token in self._llm.chat_stream(messages):
                raw_buffer += token

                # 检测进入跳过区域（内容被丢弃）
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

                # 剥离 <think> 标签壳但保留内容
                if not in_skip:
                    for start_tag, end_tag in STRIP_TAGS.items():
                        if start_tag in raw_buffer:
                            # 输出标签前的内容，然后去掉标签本身
                            parts = raw_buffer.split(start_tag, 1)
                            raw_buffer = parts[0] + parts[1]
                        if end_tag in raw_buffer:
                            parts = raw_buffer.split(end_tag, 1)
                            raw_buffer = parts[0] + parts[1]

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
                if "<" in raw_buffer and not raw_buffer.endswith(">") and len(raw_buffer) < 30:
                    continue

                if raw_buffer:
                    accumulated += raw_buffer
                    yield raw_buffer, accumulated
                    raw_buffer = ""

            if raw_buffer and not in_skip:
                accumulated += raw_buffer
                yield raw_buffer, accumulated

        except Exception as e:
            logger.error(f"reply_stream 失败: {e}")
            yield f"回复生成失败: {e}", f"回复生成失败: {e}"

    async def _belief_update(
        self,
        user_message: str,
        expert_reply: str,
        persona: str = "rag",
    ) -> AsyncGenerator[dict, None]:
        """信念更新步骤，yield belief_updated 事件（只更新对应 persona 的信念）"""
        from llm.providers import ChatMessage
        beliefs = self._graph.get_all_beliefs(persona=persona)
        prompt = BELIEF_UPDATE_PROMPT.format(
            beliefs_context=format_beliefs_context(beliefs),
            user_message=user_message,
            expert_reply=expert_reply,
        )
        try:
            # 流式收集
            chunks: list[str] = []
            async for token in self._llm.chat_stream([
                ChatMessage("user", prompt),
            ]):
                chunks.append(token)
            text = "".join(chunks).strip()

            # 剥离各种标签
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()

            if not text:
                return

            # 提取 JSON（从 markdown 代码块或直接匹配）
            json_text = text
            json_match = re.search(r'\{[^{}]*"updated"[^{}]*\}', text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            elif "```" in text:
                json_text = text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()

            if not json_text:
                return

            data = json.loads(json_text)
            output = BeliefUpdateOutput(**data)
            if output.updated:
                events = []
                for change in output.changes:
                    old_node = self._graph.get_node(change.old_belief_id)
                    if not old_node:
                        continue
                    new_id = await self._graph.update_belief(
                        old_belief_id=change.old_belief_id,
                        new_content=change.new_content,
                        new_confidence=change.new_confidence,
                        reason=change.reason,
                    )
                    new_node = self._graph.get_node(new_id)
                    events.append({"event": "belief_updated", "data": {
                        "old": {"id": change.old_belief_id, "content": old_node.get("content"), "confidence": old_node.get("confidence")},
                        "new": {"id": new_id, "content": new_node.get("content"), "confidence": new_node.get("confidence")},
                        "reason": change.reason,
                    }})
                await self._graph.save()  # single save after all changes
                for event in events:
                    yield event
        except Exception as e:
            logger.warning(f"belief_update 失败，跳过: {e}")

    # ── 兼容旧接口 ──────────────────────────────────────

    def get_beliefs(self) -> list[dict]:
        """获取当前信念（最新版本）"""
        return self._graph.get_all_beliefs()

    def get_stances(self) -> list[dict]:
        """获取当前立场"""
        stances = []
        for node_id in self._graph.graph.nodes():
            data = self._graph.graph.nodes[node_id]
            if data.get("type") == "stance":
                d = dict(data)
                d["id"] = node_id
                stances.append(d)
        return stances

    def get_knowledge_graph(self) -> KnowledgeGraph:
        """获取知识图谱"""
        return self._graph
