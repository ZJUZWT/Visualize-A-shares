"""投资专家 Agent — 完整对话流程"""

import asyncio
import json
import re
from pathlib import Path
from typing import AsyncGenerator

from loguru import logger

from expert.knowledge_graph import KnowledgeGraph
from expert.personas import (
    INITIAL_BELIEFS,
    THINK_SYSTEM_PROMPT,
    BELIEF_UPDATE_PROMPT,
    format_graph_context,
    format_memory_context,
    format_beliefs_context,
)
from expert.schemas import (
    BeliefNode,
    BeliefUpdateOutput,
    ThinkOutput,
    ToolCall,
)
from expert.tools import ExpertTools


# 专家类型到中文名的映射
EXPERT_NAMES = {
    "data": "📊 数据专家",
    "quant": "🔬 量化专家",
    "info": "📰 资讯专家",
    "industry": "🏭 产业链专家",
}


class ExpertAgent:
    """投资专家 Agent — 完整对话流程编排"""

    def __init__(
        self,
        tools: ExpertTools,
        kg_path: str | None = None,
        chromadb_dir: str | None = None,
    ):
        self._tools = tools
        self._llm = tools.llm_engine
        self._lock = asyncio.Lock()

        # 知识图谱
        self._graph = KnowledgeGraph(kg_path)

        # 初始化信念节点（仅当图谱为空时）
        if self._graph.graph.number_of_nodes() == 0:
            self._seed_initial_beliefs()

        # ChromaDB 记忆
        self._memory = None
        if chromadb_dir:
            try:
                from agent.memory import AgentMemory
                self._memory = AgentMemory(persist_dir=chromadb_dir)
                logger.info(f"AgentMemory 初始化: {chromadb_dir}")
            except Exception as e:
                logger.warning(f"AgentMemory 初始化失败，跳过记忆功能: {e}")

    def _seed_initial_beliefs(self) -> None:
        """将初始信念写入图谱"""
        for b in INITIAL_BELIEFS:
            node = BeliefNode(content=b["content"], confidence=b["confidence"])
            self._graph.add_node_sync(node)
        self._graph.save_sync()
        logger.info(f"初始信念已写入图谱: {len(INITIAL_BELIEFS)} 条")

    async def chat(self, message: str) -> AsyncGenerator[dict, None]:
        """完整对话流程，yield 结构化事件 dict"""
        yield {"event": "thinking_start", "data": {}}

        # 1. 图谱召回
        recalled_nodes = self._graph.recall(message)
        yield {"event": "graph_recall", "data": {"nodes": [
            {
                "id": n["id"],
                "type": n.get("type"),
                "label": n.get("name") or n.get("content", "")[:40],
                "confidence": n.get("confidence"),
            }
            for n in recalled_nodes
        ]}}

        # 2. 记忆召回
        memories: list[dict] = []
        if self._memory:
            try:
                memories = self._memory.recall(agent_role="expert", query=message, top_k=5)
            except Exception as e:
                logger.warning(f"记忆召回失败: {e}")

        # 3. think 步骤
        tool_calls: list[ToolCall] = []
        if self._llm:
            think_output = await self._think(message, recalled_nodes, memories)
            tool_calls = think_output.tool_calls if think_output.needs_data else []

        # 4. 工具调用
        tool_results: list[dict] = []
        for tc in tool_calls:
            # 容错：专家咨询的 question 为空时用原始消息补充
            if tc.engine == "expert" and not tc.params.get("question"):
                tc.params["question"] = message

            # 前端事件：标注是否是专家咨询
            is_expert_call = tc.engine == "expert"
            expert_label = EXPERT_NAMES.get(tc.action, tc.action) if is_expert_call else ""

            yield {"event": "tool_call", "data": {
                "engine": tc.engine, "action": tc.action, "params": tc.params,
                "label": f"咨询{expert_label}" if is_expert_call else f"{tc.engine}.{tc.action}",
            }}

            result = await self._tools.execute(tc.engine, tc.action, tc.params)
            tool_results.append({
                "engine": tc.engine,
                "action": tc.action,
                "result": result,
                "is_expert": is_expert_call,
            })

            yield {"event": "tool_result", "data": {
                "engine": tc.engine, "action": tc.action,
                "summary": result[:300] if not is_expert_call else f"{expert_label}已回复（{len(result)}字）",
                "label": expert_label if is_expert_call else tc.action,
            }}

        # 5. 流式回复
        expert_reply = ""
        if self._llm:
            async for token, full_text in self._reply_stream(
                message, recalled_nodes, memories, tool_results
            ):
                expert_reply = full_text
                yield {"event": "reply_token", "data": {"token": token}}
        else:
            expert_reply = "LLM 未配置，无法生成回复。"

        yield {"event": "reply_complete", "data": {"full_text": expert_reply}}

        # 6. 信念更新
        if self._llm and expert_reply:
            async for event in self._belief_update(message, expert_reply):
                yield event

        # 7. 记忆存储
        if self._memory:
            try:
                stock_codes = [n["code"] for n in recalled_nodes if n.get("type") == "stock"]
                target = stock_codes[0] if stock_codes else "general"
                self._memory.store(
                    agent_role="expert",
                    target=target,
                    content=f"用户: {message}\n专家: {expert_reply}",
                    metadata={"tools_used": str([tc.action for tc in tool_calls])},
                )
            except Exception as e:
                logger.warning(f"记忆存储失败: {e}")

    async def _think(
        self,
        message: str,
        nodes: list[dict],
        memories: list[dict],
    ) -> ThinkOutput:
        """think 步骤：LLM 决策是否需要工具调用（流式收集 + 容错解析）"""
        from llm.providers import ChatMessage
        prompt = THINK_SYSTEM_PROMPT.format(
            graph_context=format_graph_context(nodes),
            memory_context=format_memory_context(memories),
        )
        try:
            # 流式收集
            chunks: list[str] = []
            async for token in self._llm.chat_stream([
                ChatMessage("system", prompt),
                ChatMessage("user", message),
            ]):
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

            # 剥离 <think> 标签
            text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
            # 剥离 <minimax:*> 标签（MiniMax 特有）
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
            # 剥离 [TOOL_CALL]...[/TOOL_CALL] 块
            text = re.sub(r"\[TOOL_CALL\].*?\[/TOOL_CALL\]", "", text, flags=re.DOTALL).strip()

            # 提取 JSON（优先从正文中提取）
            json_text = text
            # 尝试找到 JSON 对象
            json_match = re.search(r'\{[^{}]*"needs_data"[^{}]*\}', text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            elif "```" in text:
                json_text = text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()

            # 尝试 JSON 解析
            if json_text:
                try:
                    data = json.loads(json_text)
                    logger.info(f"think 步骤 JSON 解析成功: needs_data={data.get('needs_data')}")
                    return ThinkOutput(**data)
                except json.JSONDecodeError:
                    logger.debug(f"think JSON 解析失败，尝试容错: {json_text[:150]}")

            # ── 容错解析：从 think 内容或原始文本中提取意图 ──
            full_context = think_content + "\n" + raw_text
            return self._fallback_think_parse(full_context)

        except Exception as e:
            logger.warning(f"think 步骤异常: {e}")
            return ThinkOutput(needs_data=False)

    def _fallback_think_parse(self, text: str) -> ThinkOutput:
        """容错解析：从 LLM 非标准输出中提取工具调用意图"""
        tool_calls: list[dict] = []

        # 从文本中提取 6 位股票代码
        code_match = re.search(r'\b(\d{6})\b', text)
        detected_code = code_match.group(1) if code_match else ""

        # 专家类型关键词匹配
        expert_patterns = {
            "data": [r"数据专家", r"咨询.*data", r"action.*[\"']data[\"']", r"行情数据", r"历史走势"],
            "quant": [r"量化专家", r"咨询.*quant", r"技术指标", r"技术面", r"因子", r"action.*[\"']quant[\"']",
                      r"支撑.*阻力", r"RSI", r"MACD", r"均线"],
            "info": [r"资讯专家", r"咨询.*info", r"新闻", r"公告", r"舆情", r"action.*[\"']info[\"']"],
            "industry": [r"产业链专家", r"咨询.*industry", r"行业分析", r"产业链", r"action.*[\"']industry[\"']"],
        }

        # 检测需要咨询的专家
        detected_experts: set[str] = set()
        for expert_type, patterns in expert_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    detected_experts.add(expert_type)
                    break

        if detected_experts:
            for expert_type in detected_experts:
                # 尝试从文本中提取 question
                question = ""
                tc_pattern = rf'action.*?["\']?{expert_type}["\']?.*?question.*?["\']([^"\']+)["\']'
                q_match = re.search(tc_pattern, text, re.DOTALL | re.IGNORECASE)
                if q_match:
                    question = q_match.group(1)

                tool_calls.append({
                    "engine": "expert",
                    "action": expert_type,
                    "params": {"question": question},
                })

            logger.info(f"think 容错解析: 检测到需要咨询 {list(detected_experts)}")
            return ThinkOutput(
                needs_data=True,
                tool_calls=[ToolCall(**tc) for tc in tool_calls],
                reasoning=f"容错解析: 检测到需要咨询{','.join(detected_experts)}",
            )

        # 检测直接数据查询（仅用于非常简单的请求）
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
            if re.search(pattern, text, re.IGNORECASE):
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

    async def _reply_stream(
        self,
        message: str,
        nodes: list[dict],
        memories: list[dict],
        tool_results: list[dict],
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

        accumulated = ""
        in_skip = False          # 跳过区域（<think> 或 <minimax:*>）
        skip_end_tag = ""        # 当前跳过区域的结束标签
        raw_buffer = ""

        # 需要过滤的标签及其结束标签
        SKIP_TAGS = {
            "<think>": "</think>",
            "<minimax:tool_call>": "</minimax:tool_call>",
            "<minimax:search_result>": "</minimax:search_result>",
        }

        try:
            async for token in self._llm.chat_stream([
                ChatMessage("system", system),
                ChatMessage("user", message),
            ]):
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
                    continue

                if in_skip:
                    if len(raw_buffer) > 200:
                        raw_buffer = raw_buffer[-20:]
                    continue

                if "<" in raw_buffer and not raw_buffer.endswith(">") and len(raw_buffer) < 20:
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
    ) -> AsyncGenerator[dict, None]:
        """信念更新步骤，yield belief_updated 事件"""
        from llm.providers import ChatMessage
        beliefs = self._graph.get_all_beliefs()
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
