"""投资专家 Agent — 完整对话流程"""

import asyncio
import json
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
            yield {"event": "tool_call", "data": {
                "engine": tc.engine, "action": tc.action, "params": tc.params
            }}
            summary = await self._tools.execute(tc.engine, tc.action, tc.params)
            tool_results.append({"engine": tc.engine, "action": tc.action, "summary": summary})
            yield {"event": "tool_result", "data": {
                "engine": tc.engine, "action": tc.action, "summary": summary
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
        """think 步骤：LLM 决策是否需要工具调用"""
        from llm.providers import ChatMessage
        prompt = THINK_SYSTEM_PROMPT.format(
            graph_context=format_graph_context(nodes),
            memory_context=format_memory_context(memories),
        )
        try:
            response = await self._llm.chat([
                ChatMessage("system", prompt),
                ChatMessage("user", message),
            ])
            data = json.loads(response)
            return ThinkOutput(**data)
        except Exception as e:
            logger.warning(f"think 步骤解析失败: {e}")
            return ThinkOutput(needs_data=False)

    async def _reply_stream(
        self,
        message: str,
        nodes: list[dict],
        memories: list[dict],
        tool_results: list[dict],
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复，yield (token, accumulated_text)"""
        from llm.providers import ChatMessage
        context_parts = [format_graph_context(nodes)]
        if tool_results:
            context_parts.append("数据查询结果：\n" + "\n".join(
                f"- {r['engine']}.{r['action']}: {r['summary']}" for r in tool_results
            ))
        system = "你是一位理性的A股投资专家，请基于以下上下文回答用户问题。\n\n" + "\n\n".join(context_parts)
        accumulated = ""
        try:
            async for token in self._llm.chat_stream([
                ChatMessage("system", system),
                ChatMessage("user", message),
            ]):
                accumulated += token
                yield token, accumulated
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
            response = await self._llm.chat([ChatMessage("user", prompt)])
            data = json.loads(response)
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
