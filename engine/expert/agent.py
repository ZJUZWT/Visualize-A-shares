"""投资专家 Agent — 完整对话流程"""

import json
from typing import Any, AsyncGenerator

from loguru import logger

from expert.knowledge_graph import KnowledgeGraph
from expert.personas import (
    INITIAL_BELIEFS,
    INITIAL_STANCES,
    THINK_SYSTEM_PROMPT,
    BELIEF_UPDATE_PROMPT,
    format_beliefs_for_prompt,
    format_stances_for_prompt,
)
from expert.schemas import (
    BeliefNode,
    BeliefUpdateOutput,
    ExpertChatRequest,
    StanceNode,
    ThinkOutput,
    ToolCall,
)
from expert.tools import ExpertTools


class ExpertAgent:
    """投资专家 Agent — 完整对话流程编排"""

    def __init__(self, tools: ExpertTools, kg_path: str | None = None):
        self.tools = tools
        self.kg = KnowledgeGraph(kg_path)
        self.beliefs = list(INITIAL_BELIEFS)
        self.stances = list(INITIAL_STANCES)
        self.llm_engine = tools.llm_engine
        self.session_id = None

    def set_session_id(self, session_id: str):
        """设置会话 ID"""
        self.session_id = session_id

    async def chat(self, request: ExpertChatRequest) -> AsyncGenerator[str, None]:
        """完整对话流程"""
        if request.session_id:
            self.set_session_id(request.session_id)

        logger.info(f"[{self.session_id}] 用户消息: {request.message}")

        # 1. 图谱召回 — 获取相关节点
        graph_context = self._graph_recall(request.message)
        logger.debug(f"图谱召回: {len(graph_context['nodes'])} 个节点")

        # 2. 记忆召回 — 获取相关信念和立场
        memory_context = self._memory_recall(request.message)
        logger.debug(f"记忆召回: {len(memory_context['beliefs'])} 个信念")

        # 3. 思考 — 决定是否需要工具调用
        think_output = await self._think(
            request.message,
            graph_context,
            memory_context,
        )
        logger.debug(f"思考输出: needs_data={think_output.needs_data}, tool_calls={len(think_output.tool_calls)}")

        # 4. 工具调用 — 执行必要的数据获取
        tool_results = {}
        if think_output.tool_calls:
            for tool_call in think_output.tool_calls:
                result = self.tools.execute_tool_call(tool_call)
                tool_results[f"{tool_call.engine}.{tool_call.action}"] = result
                logger.debug(f"工具调用结果: {tool_call.engine}.{tool_call.action}")

        # 5. 回复流 — 生成流式回复
        async for chunk in self._reply_stream(
            request.message,
            think_output,
            tool_results,
            memory_context,
        ):
            yield chunk

        # 6. 信念更新 — 基于新信息更新信念
        belief_update = await self._belief_update(
            request.message,
            tool_results,
        )
        if belief_update.updated:
            self._apply_belief_changes(belief_update)
            logger.info(f"信念已更新: {len(belief_update.changes)} 个变化")

        # 7. 记忆存储 — 保存图谱
        self.kg.save()
        logger.debug("知识图谱已保存")

    def _graph_recall(self, query: str) -> dict[str, Any]:
        """图谱召回 — BFS 获取相关节点"""
        # 简化实现：返回图谱统计信息
        stats = self.kg.stats()
        return {
            "nodes": [],
            "edges": [],
            "stats": stats,
        }

    def _memory_recall(self, query: str) -> dict[str, Any]:
        """记忆召回 — 获取相关信念和立场"""
        return {
            "beliefs": self.beliefs,
            "stances": self.stances,
        }

    async def _think(
        self,
        message: str,
        graph_context: dict,
        memory_context: dict,
    ) -> ThinkOutput:
        """思考 — 决定是否需要工具调用"""
        if not self.llm_engine:
            # 无 LLM 时返回默认思考
            return ThinkOutput(
                needs_data=True,
                tool_calls=[],
                reasoning="无 LLM 引擎，跳过思考",
            )

        beliefs_str = format_beliefs_for_prompt(memory_context["beliefs"])
        stances_str = format_stances_for_prompt(memory_context["stances"])

        prompt = f"""用户问题: {message}

当前信念:
{beliefs_str}

当前立场:
{stances_str}

{THINK_SYSTEM_PROMPT}"""

        try:
            response = await self.llm_engine.agenerate(prompt)
            # 尝试解析 JSON
            think_output = ThinkOutput.model_validate_json(response)
            return think_output
        except Exception as e:
            logger.warning(f"思考解析失败: {e}")
            return ThinkOutput(
                needs_data=True,
                tool_calls=[],
                reasoning=str(e),
            )

    async def _reply_stream(
        self,
        message: str,
        think_output: ThinkOutput,
        tool_results: dict,
        memory_context: dict,
    ) -> AsyncGenerator[str, None]:
        """回复流 — 生成流式回复"""
        if not self.llm_engine:
            yield "无 LLM 引擎，无法生成回复"
            return

        context = f"""用户问题: {message}

分析过程: {think_output.reasoning}

工具结果: {json.dumps(tool_results, ensure_ascii=False, indent=2)}

当前信念:
{format_beliefs_for_prompt(memory_context['beliefs'])}

当前立场:
{format_stances_for_prompt(memory_context['stances'])}"""

        try:
            async for chunk in self.llm_engine.astream(context):
                yield chunk
        except Exception as e:
            logger.error(f"回复流生成失败: {e}")
            yield f"生成回复失败: {e}"

    async def _belief_update(
        self,
        message: str,
        tool_results: dict,
    ) -> BeliefUpdateOutput:
        """信念更新 — 基于新信息更新信念"""
        if not self.llm_engine:
            return BeliefUpdateOutput(updated=False)

        beliefs_str = format_beliefs_for_prompt(self.beliefs)
        new_info = f"用户问题: {message}\n工具结果: {json.dumps(tool_results, ensure_ascii=False)}"

        prompt = BELIEF_UPDATE_PROMPT.format(
            current_beliefs=beliefs_str,
            new_information=new_info,
        )

        try:
            response = await self.llm_engine.agenerate(prompt)
            belief_update = BeliefUpdateOutput.model_validate_json(response)
            return belief_update
        except Exception as e:
            logger.warning(f"信念更新解析失败: {e}")
            return BeliefUpdateOutput(updated=False)

    def _apply_belief_changes(self, belief_update: BeliefUpdateOutput):
        """应用信念变化"""
        for change in belief_update.changes:
            # 找到并更新对应的信念
            for i, belief in enumerate(self.beliefs):
                if belief.id == change.old_belief_id:
                    self.beliefs[i] = BeliefNode(
                        content=change.new_content,
                        confidence=change.new_confidence,
                    )
                    logger.info(f"信念已更新: {change.old_belief_id}")
                    break

    def get_beliefs(self) -> list[BeliefNode]:
        """获取当前信念"""
        return self.beliefs

    def get_stances(self) -> list[StanceNode]:
        """获取当前立场"""
        return self.stances

    def get_knowledge_graph(self) -> KnowledgeGraph:
        """获取知识图谱"""
        return self.kg
