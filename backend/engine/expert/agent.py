"""投资专家 Agent — 完整对话流程"""

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from loguru import logger

from engine.expert.knowledge_graph import KnowledgeGraph
from engine.expert.personas import (
    INITIAL_BELIEFS,
    SHORT_TERM_BELIEFS,
    BELIEF_UPDATE_PROMPT,
    build_reply_system,
    build_think_prompt,
    format_graph_context,
    format_memory_context,
    format_beliefs_context,
    get_current_date_context,
)
from engine.expert.schemas import (
    BeliefNode,
    BeliefUpdateOutput,
    ClarificationOption,
    ClarificationOutput,
    ClarificationRoundSelection,
    ClarificationSelection,
    ClarificationSubChoice,
    GraphEdge,
    MaterialNode,
    RegionNode,
    SelfCritiqueOutput,
    SectorNode,
    StockNode,
    ThinkOutput,
    ToolCall,
)
from engine.expert.tools import ExpertTools
from engine.expert.engine_experts import TRADE_PLAN_PROMPT
from engine.runtime import ExecutionContext, ProgressiveEmitter, QueryPrefetcher, ToolExecutionPlanner
from llm.context_guard import ContextGuard
from llm import ModelRouter


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
        self._model_router = ModelRouter.from_provider(tools.llm_engine)
        self._llm = self._model_router.get("quality")
        self._lock = asyncio.Lock()
        self._context_guard = ContextGuard()
        self._planner = ToolExecutionPlanner()
        self._emitter = ProgressiveEmitter()
        self._prefetcher = QueryPrefetcher(
            getattr(tools, "data_engine", None),
            stock_name_lookup=self._get_stock_name_map_for_runtime,
        )

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

    def _get_stock_name_map_for_runtime(self) -> dict[str, str]:
        stock_name_map = getattr(self, "_stock_name_map", None)
        if isinstance(stock_name_map, dict):
            return stock_name_map
        return type(self)._get_stock_name_map()

    def _get_fast_llm(self):
        return self._model_router.get("fast") if self._model_router else self._llm

    def _get_quality_llm(self):
        return self._model_router.get("quality") if self._model_router else self._llm

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

    @staticmethod
    def _is_open_recommendation(query: str) -> bool:
        """检测是否为开放式推荐问题（没有指定具体股票，只问推荐/选股/买什么）

        用于：
        1. 图谱召回时过滤历史股票节点，避免锚定效应
        2. 澄清环节增加"范围偏好"引导
        """
        # 先检测是否有具体股票（6位代码或常见股票名）
        has_specific_stock = bool(re.search(r'\d{6}', query))
        if has_specific_stock:
            return False
        # 开放式推荐关键词
        open_patterns = [
            r"推荐", r"选股", r"选.*股", r"有什么好", r"买什么", r"配置",
            r"看好.*什么", r"投资.*建议", r"哪些.*值得", r"好股", r"有什么机会",
            r"什么.*值得买", r"什么.*可以买", r"有没有.*推荐", r"帮我选",
            r"今天.*做什么", r"有什么.*题材", r"什么.*机会",
        ]
        return any(re.search(p, query) for p in open_patterns)

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

        # ── 开放式推荐：过滤历史股票节点，避免锚定效应 ──
        # 保留 belief/sector/event 等方向性节点，去掉具体 stock 节点
        # 这样 LLM 在 think 时不会被之前聊过的个股锚定，能真正发散扫描
        if self._is_open_recommendation(query):
            before_count = len(recalled_nodes)
            recalled_nodes = [
                n for n in recalled_nodes
                if n.get("type") != "stock"
            ]
            filtered = before_count - len(recalled_nodes)
            if filtered > 0:
                logger.info(f"🔓 开放式推荐：过滤 {filtered} 个历史股票节点，避免锚定")
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

    @staticmethod
    def _detect_tool_error(result_text: str, is_expert: bool = False) -> bool:
        """判断工具结果是否为错误

        区分两种场景：
        - 专家回复(is_expert=True)：LLM 生成的自然语言，需要严格匹配结构化错误前缀，
          避免正文中出现"⚠️ 风险提示"或"XX失败"等字眼被误判。
        - 普通工具调用(is_expert=False)：通常是 JSON 或短文本，可以用关键词匹配。
        """
        if not result_text:
            return True

        if is_expert:
            # 专家回复 — 仅匹配明确的调用层错误前缀
            expert_error_prefixes = [
                "专家 ", "调用专家 ", "缺少 question",
            ]
            expert_error_keywords = [
                "连接超时", "连接中断", "读取失败", "请求失败",
                "未返回有效内容",
            ]
            text_start = result_text[:200]
            for prefix in expert_error_prefixes:
                if text_start.startswith(prefix) and any(
                    kw in text_start for kw in ["错误:", "失败:", "超时"]
                ):
                    return True
            return any(kw in text_start for kw in expert_error_keywords)
        else:
            # 普通工具调用 — 结果短，关键词匹配
            error_keywords = [
                "工具调用失败", "error", "未找到", "无快照数据",
                "无法解析", "无法识别", "需要具体股票代码",
            ]
            text_lower = result_text[:300].lower()
            # JSON error 字段检测
            try:
                data = json.loads(result_text)
                if isinstance(data, dict) and "error" in data:
                    return True
            except (json.JSONDecodeError, Exception):
                pass
            return any(kw.lower() in text_lower for kw in error_keywords)

    async def execute_tools(self, tool_calls: list[ToolCall], context: ExecutionContext | None = None) -> list[dict]:
        """并行执行工具调用，返回 tool_results（兼容旧接口）"""
        if not tool_calls:
            return []
        results: list[dict] = []
        async for r in self.execute_tools_streaming(tool_calls, context=context):
            results.append(r)
        return results

    async def execute_tools_streaming(
        self,
        tool_calls: list[ToolCall],
        context: ExecutionContext | None = None,
    ) -> AsyncGenerator[dict, None]:
        """基于依赖规划并行执行工具调用，逐个完成时 yield 结果。"""
        if not tool_calls:
            return

        async def _exec(idx: int, tc: ToolCall) -> tuple[int, dict]:
            result = await self._tools.execute(tc.engine, tc.action, tc.params)
            return idx, {
                "engine": tc.engine,
                "action": tc.action,
                "result": result,
                "is_expert": tc.engine == "expert",
            }
        phases = self._planner.plan(tool_calls, context=context)
        if len(phases) > 1:
            logger.info(f"📋 依赖规划执行: " + " -> ".join(str(len(phase)) for phase in phases))

        for phase in phases:
            tasks = [asyncio.create_task(_exec(i, tc)) for i, tc in enumerate(phase)]
            for coro in asyncio.as_completed(tasks):
                _idx, result = await coro
                yield result

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
        enable_trade_plan: bool = False,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复，yield (token, full_text)"""
        async for token, full_text in self._reply_stream(
            message, nodes, memories, tool_results, history or [],
            persona=persona, enable_trade_plan=enable_trade_plan,
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

    @staticmethod
    def _merge_clarification_selection(
        message: str,
        clarification_selection: ClarificationSelection | dict | None,
    ) -> str:
        if not clarification_selection:
            return message
        selection = (
            clarification_selection
            if isinstance(clarification_selection, ClarificationSelection)
            else ClarificationSelection(**clarification_selection)
        )
        if selection.skip:
            return message
        return (
            f"{message}\n\n"
            "【用户已确认的分析方向】\n"
            f"- 选项：{selection.label}. {selection.title}\n"
            f"- 重点：{selection.focus}\n"
            "请优先围绕这个重点组织拆题、证据和最终回答。"
        )

    @staticmethod
    def _merge_clarification_chain(
        message: str,
        clarification_chain: list[ClarificationRoundSelection | dict] | None,
    ) -> str:
        """将多轮澄清选择合并为上下文，注入到用户消息中（支持多选 + 子选项）"""
        if not clarification_chain:
            return message

        all_lines: list[str] = []
        for raw_sel in clarification_chain:
            if isinstance(raw_sel, dict):
                sel = ClarificationRoundSelection(**raw_sel)
            else:
                sel = raw_sel

            # 优先使用 selections 列表（多选模式），否则从旧字段构建单条
            if sel.selections:
                for s in sel.selections:
                    if s.skip:
                        continue
                    desc = f"{s.label}. {s.title}"
                    if s.sub_choice_id and s.sub_choice_text:
                        desc += f"（{s.sub_choice_text}）"
                    all_lines.append(f"- 第{sel.round}轮：{desc}（重点：{s.focus}）")
            elif sel.option_id and not sel.skip:
                # 向后兼容旧字段
                all_lines.append(f"- 第{sel.round}轮：{sel.label}. {sel.title}（重点：{sel.focus}）")

        if not all_lines:
            return message

        return (
            f"{message}\n\n"
            "【用户已确认的分析方向（多轮澄清）】\n"
            + "\n".join(all_lines) + "\n"
            "请综合以上所有用户选择的分析重点，组织拆题、证据和最终回答。"
        )

    async def clarify(
        self,
        message: str,
        history: list[dict] | None = None,
        persona: str = "rag",
        previous_selections: list[ClarificationRoundSelection | dict] | None = None,
    ) -> ClarificationOutput:
        """为深度思考模式生成 clarification 选项 — 经 LLM 动态生成。

        支持多轮澄清：previous_selections 包含之前轮次的用户选择，
        LLM 根据这些选择决定是否需要继续追问。
        """
        conv_history = history or []
        clean_message = (message or "").strip() or "当前问题"
        prev_sels = previous_selections or []
        # 规范化为 ClarificationRoundSelection 对象
        normalized_sels: list[ClarificationRoundSelection] = []
        for sel in prev_sels:
            if isinstance(sel, dict):
                normalized_sels.append(ClarificationRoundSelection(**sel))
            else:
                normalized_sels.append(sel)
        current_round = len(normalized_sels) + 1
        max_rounds = 3

        if persona == "short_term":
            role_desc = "你是一位经验丰富的短线交易专家"
            fallback_options = [
                ClarificationOption(id="timing", label="A", title="先看买点与节奏",
                    description="确认现在能不能上、什么时候上。", focus="买点、节奏、执行窗口"),
                ClarificationOption(id="technical", label="B", title="先看量价与技术位",
                    description="判断支撑阻力、量能和技术信号。", focus="量价、技术位、支撑阻力"),
                ClarificationOption(id="theme", label="C", title="先看板块与龙头",
                    description="确认题材强弱和龙头辨识。", focus="板块强弱、龙头地位、题材发酵"),
                ClarificationOption(id="risk", label="D", title="先看止损与撤退条件",
                    description="先定义做错了怎么退。", focus="止损位、失效条件、风险控制"),
            ]
        else:
            role_desc = "你是一位专业的投资顾问"
            fallback_options = [
                ClarificationOption(id="valuation", label="A", title="先看估值与安全边际",
                    description="判断值不值、贵不贵、赔率够不够。", focus="估值、安全边际、风险收益比"),
                ClarificationOption(id="fundamental", label="B", title="先看基本面与行业逻辑",
                    description="判断生意质量和行业周期。", focus="基本面、行业周期、核心逻辑"),
                ClarificationOption(id="position", label="C", title="先看仓位与操作策略",
                    description="判断该不该买、怎么买、配多少。", focus="仓位管理、买入策略、持有计划"),
                ClarificationOption(id="catalyst", label="D", title="先看催化与观察清单",
                    description="先看需要继续确认什么，再决定出手。", focus="催化剂、验证点、观察清单"),
            ]

        # 构建之前选择的上下文（支持多选 selections）
        prev_context = ""
        if normalized_sels:
            lines = []
            for sel in normalized_sels:
                if sel.selections:
                    # 多选模式：列出本轮所有选择
                    sel_descs = []
                    for s in sel.selections:
                        if s.skip:
                            continue
                        desc = f"{s.label}. {s.title}"
                        if s.sub_choice_id and s.sub_choice_text:
                            desc += f"（{s.sub_choice_text}）"
                        sel_descs.append(desc)
                    if sel_descs:
                        lines.append(f"  第{sel.round}轮用户选了：{' + '.join(sel_descs)}（重点：{', '.join(s.focus for s in sel.selections if not s.skip)}）")
                elif sel.option_id and not sel.skip:
                    lines.append(f"  第{sel.round}轮用户选了：{sel.label}. {sel.title}（重点：{sel.focus}）")
            if lines:
                prev_context = (
                    "\n\n之前的澄清轮次中，用户已经做了以下选择：\n"
                    + "\n".join(lines) + "\n"
                )

        # 第3轮强制结束
        if current_round >= max_rounds:
            force_end_hint = "\n\n注意：这是最后一轮澄清，你必须设置 needs_more=false，不再继续追问。\n"
        else:
            force_end_hint = (
                "\n\n你需要判断是否还需要继续追问用户。"
                "如果前面的选择已经足够明确分析方向，设置 needs_more=false；"
                "如果某个维度还需要进一步细化，设置 needs_more=true 并生成下一轮选项。"
                "不要为了多轮而多轮——如果一轮就够了，直接 needs_more=false。\n"
            )

        # ── 开放式推荐：第1轮时引导 LLM 生成"范围偏好"选项 ──
        open_reco_hint = ""
        if current_round == 1 and self._is_open_recommendation(clean_message):
            open_reco_hint = (
                "\n\n【特别注意 — 开放式推荐问题】\n"
                "用户没有指定具体股票，而是想要推荐/选股。你的选项中应该包含**范围维度**的选择，例如：\n"
                "- 全市场发散扫描（不限行业，从量价、资金、题材等多维度挖掘）\n"
                "- 聚焦某个行业/板块（如新能源、半导体、消费等）\n"
                "- 某种投资风格（如低估值价值股、高成长股、高股息防御股等）\n"
                "不要默认只扫描之前聊过的股票，用户通常希望发现新的机会。\n"
                "你可以把范围选择和分析维度混合在同一组选项中，让用户同时表达偏好。\n"
            )

        prompt = (
            f"{role_desc}。用户向你提问：\n\n「{clean_message}」\n"
            f"{prev_context}"
            f"{open_reco_hint}"
            f"{force_end_hint}\n"
            f"当前是第 {current_round} 轮澄清（最多 {max_rounds} 轮）。\n\n"
            "请你根据问题内容和之前的选择，生成 3-4 个分析方向选项，帮助用户进一步聚焦。\n"
            "每个选项要贴合用户的具体问题（不要千篇一律的通用选项），让用户选择最关心的维度。\n\n"
            "【关键规则 — 必须遵守】\n"
            "- 你的输出必须是纯 JSON 格式，不要在 JSON 外面写任何自然语言\n"
            "- options 数组必须包含 3-4 个选项，绝对不能为空\n"
            "- 即使你想问用户一个问题，也必须通过 question_summary + options 结构来承载，不能只返回一句问话\n"
            "- question_summary 里可以包含问句，但必须同时提供 options 让用户选择\n\n"
            "字段说明：\n"
            "1. question_summary: 用一句话重述当前轮次要确认的问题核心（自然、口语化）\n"
            "2. multi_select: 是否允许用户多选（true/false）。**默认应该设为 true**，除非选项之间是严格互斥的（如「短线 vs 长线」只能选一个）。大多数分析维度之间不冲突，用户可能同时关心多个维度\n"
            "3. options: 3-4个选项，每个包含 id(英文标识)、label(A/B/C/D)、title(8字以内)、description(一句话说明)、focus(分析关键词)\n"
            "   - 如果某个选项本质上是一个「二选一/三选一」的子问题（如「你是短线还是长线？」），给它加 sub_choices 字段\n"
            "   - sub_choices 示例: [{\"id\": \"short\", \"label\": \"①\", \"text\": \"短线（1-5日）\"}, ...]\n"
            "   - 普通选项不需要 sub_choices\n"
            "4. reasoning: 一句话解释为什么需要这轮确认\n"
            "5. needs_more: true 表示还需要继续追问，false 表示这轮选完就够了\n\n"
            "严格返回 JSON 格式（不要有任何其他文字）：\n"
            "```json\n"
            "{\n"
            '  "question_summary": "...",\n'
            '  "multi_select": true,\n'
            '  "options": [\n'
            '    {"id": "style", "label": "A", "title": "先确认投资风格", "description": "...", "focus": "...",\n'
            '     "sub_choices": [{"id": "short", "label": "①", "text": "短线"}, {"id": "mid", "label": "②", "text": "中线"}, {"id": "long", "label": "③", "text": "长线"}]},\n'
            '    {"id": "valuation", "label": "B", "title": "看估值", "description": "...", "focus": "..."},\n'
            '    {"id": "risk", "label": "C", "title": "风险评估", "description": "...", "focus": "..."},\n'
            '    {"id": "catalyst", "label": "D", "title": "催化剂", "description": "...", "focus": "..."}\n'
            '  ],\n'
            '  "reasoning": "...",\n'
            '  "needs_more": true\n'
            "}\n"
            "```"
        )

        try:
            from llm.providers import ChatMessage
            t0 = time.monotonic()
            chunks: list[str] = []
            async for token in self._llm.chat_stream([ChatMessage("user", prompt)]):
                chunks.append(token)
            raw = "".join(chunks)
            elapsed = time.monotonic() - t0
            logger.info(f"⏱️ clarify LLM 耗时 {elapsed:.1f}s (第{current_round}轮)")

            import re, json as json_mod
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                parsed = json_mod.loads(json_match.group())
                options = []
                labels = ["A", "B", "C", "D"]
                for i, opt in enumerate(parsed.get("options", [])[:4]):
                    # 解析子选项
                    sub_choices = []
                    for sc in opt.get("sub_choices", []):
                        sub_choices.append(ClarificationSubChoice(
                            id=sc.get("id", f"sc_{i}"),
                            label=sc.get("label", ""),
                            text=sc.get("text", ""),
                        ))
                    options.append(ClarificationOption(
                        id=opt.get("id", f"opt_{i}"),
                        label=labels[i] if i < len(labels) else opt.get("label", str(i)),
                        title=opt.get("title", ""),
                        description=opt.get("description", ""),
                        focus=opt.get("focus", ""),
                        sub_choices=sub_choices,
                    ))
                # 第3轮强制 needs_more=false
                needs_more = parsed.get("needs_more", True) if current_round < max_rounds else False
                multi_select = bool(parsed.get("multi_select", True))
                # 兜底：如果没有任何选项带 sub_choices（互斥子选项），强制多选
                # 只有带 sub_choices 的选项才可能是互斥的（如"短线 vs 长线"）
                has_exclusive_option = any(opt.get("sub_choices") for opt in parsed.get("options", []))
                if not has_exclusive_option:
                    multi_select = True
                if options:
                    return ClarificationOutput(
                        should_clarify=True,
                        question_summary=parsed.get("question_summary", f"你在问：{clean_message[:60]}"),
                        options=options,
                        reasoning=parsed.get("reasoning", ""),
                        skip_option=ClarificationOption(
                            id="skip", label="S", title="跳过，直接分析",
                            description="不做澄清，直接进入完整分析。", focus="完整分析",
                        ),
                        needs_more=needs_more,
                        round=current_round,
                        max_rounds=max_rounds,
                        multi_select=multi_select,
                    )
        except Exception as e:
            logger.warning(f"clarify LLM 生成失败，降级到预设选项: {e}")

        # 降级：使用预设选项（第1轮才用预设，后续轮降级直接结束）
        if current_round > 1:
            return ClarificationOutput(
                should_clarify=False,
                question_summary="已收集足够信息，开始分析。",
                options=[],
                reasoning="澄清降级，直接进入分析。",
                skip_option=ClarificationOption(
                    id="skip", label="S", title="跳过，直接分析",
                    description="不做澄清，直接进入完整分析。", focus="完整分析",
                ),
                needs_more=False,
                round=current_round,
                max_rounds=max_rounds,
            )
        question_summary = (
            f"你在问：{clean_message[:80]}"
            + ("，想先明确分析重点再展开。" if persona == "rag" else "，想先明确这笔交易最该盯的短线焦点。")
        )
        reasoning = (
            "投资顾问视角下，这类问题通常同时涉及价值、风险和执行方式，先确认分析重点能避免一股脑给结论。"
            if persona != "short_term"
            else "短线问题通常有多个执行维度，先确认你最关心节奏、技术、板块还是风控，后续回答会更聚焦。"
        )
        return ClarificationOutput(
            should_clarify=True,
            question_summary=question_summary,
            options=fallback_options,
            reasoning=reasoning,
            skip_option=ClarificationOption(
                id="skip", label="S", title="跳过，直接分析",
                description="不做澄清，直接进入完整分析。", focus="完整分析",
            ),
            needs_more=True,
            round=current_round,
            max_rounds=max_rounds,
            multi_select=True,
        )

    async def _self_critique(
        self,
        message: str,
        reply: str,
        tool_results: list[dict],
        persona: str = "rag",
    ) -> SelfCritiqueOutput:
        """在最终回复前补一段轻量自我质疑。"""
        _ = (message, reply, tool_results)
        if persona == "short_term":
            return SelfCritiqueOutput(
                summary="短线判断更依赖盘中节奏，若量能和承接不配合，执行质量会明显下降。",
                risks=["量能不足时，突破很容易失败。"],
                missing_data=["盘中承接和次日情绪还未验证。"],
                counterpoints=["如果龙头强度不够，跟风股更容易先掉队。"],
                confidence_note="短线结论对执行时点敏感。",
            )
        return SelfCritiqueOutput(
            summary="结论仍依赖后续基本面和市场验证，若安全边际不足，操作节奏应更保守。",
            risks=["行业逻辑若继续走弱，原判断会被削弱。"],
            missing_data=["关键验证点还需要后续财务或行业数据确认。"],
            counterpoints=["如果价格已经提前透支预期，风险收益比会变差。"],
            confidence_note="更适合结合仓位管理分步判断。",
        )

    async def chat(
        self, message: str, history: list[dict] | None = None, persona: str = "rag",
        deep_think: bool = False, max_rounds: int = 3,
        clarification_selection: ClarificationSelection | dict | None = None,
        clarification_chain: list[ClarificationRoundSelection | dict] | None = None,
        enable_trade_plan: bool = False,
    ) -> AsyncGenerator[dict, None]:
        """完整对话流程，yield 结构化事件 dict

        Args:
            message: 用户消息
            history: 对话历史 [{"role": "user"|"expert", "content": "..."}]
            persona: 人格类型 "rag"(投资顾问) 或 "short_term"(短线专家)
            deep_think: 多轮渐进模式 — 每轮工具执行完后 LLM 可以决定是否继续补查
            max_rounds: deep_think 模式下最大工具调用轮数
            clarification_chain: 多轮澄清选择链（优先使用）
            clarification_selection: 单轮澄清选择（向后兼容）
        """
        conv_history = history or []
        # 优先使用多轮澄清链，其次降级到单轮选择
        if clarification_chain:
            analysis_message = self._merge_clarification_chain(message, clarification_chain)
        else:
            analysis_message = self._merge_clarification_selection(message, clarification_selection)
        agent_role = "short_term" if persona == "short_term" else "expert"
        t0_chat = time.monotonic()
        runtime_context = ExecutionContext(
            message=analysis_message,
            module="expert",
            history=conv_history,
            persona=persona,
        )
        prefetch_task = asyncio.create_task(self._prefetcher.prefetch(analysis_message, runtime_context))
        yield {"event": "thinking_start", "data": {}}

        # 1-3. 图谱召回 + 记忆召回 + think
        recalled_nodes, memories, think_output = await self.recall_and_think(analysis_message, conv_history, persona=persona)
        runtime_context = await prefetch_task
        prefetch_event = self._emitter.build_prefetch_ready(runtime_context)
        if prefetch_event:
            yield prefetch_event
        yield {"event": "graph_recall", "data": {"nodes": [
            {
                "id": n["id"],
                "type": n.get("type"),
                "label": n.get("name") or n.get("content", "")[:40],
                "confidence": n.get("confidence"),
            }
            for n in recalled_nodes
        ]}}
        if think_output.reasoning.strip():
            yield {"event": "reasoning_summary", "data": {"summary": think_output.reasoning.strip()}}

        # ══════════════════════════════════════════════════════
        # 多轮渐进工具调用循环
        # ══════════════════════════════════════════════════════
        effective_max_rounds = max_rounds if deep_think else 1
        all_tool_results: list[dict] = []
        round_num = 0
        current_tool_calls = think_output.tool_calls if think_output.needs_data else []
        early_insight_emitted = False

        while round_num < effective_max_rounds:
            round_num += 1

            if deep_think and round_num > 1:
                yield {"event": "thinking_round", "data": {
                    "round": round_num,
                    "max_rounds": effective_max_rounds,
                }}

            tool_calls = current_tool_calls

            # ── 去重：当已有 expert.data 调用时，过滤掉多余的 data.get_daily_history ──
            has_data_expert = any(tc.engine == "expert" and tc.action == "data" for tc in tool_calls)
            if has_data_expert:
                before_len = len(tool_calls)
                tool_calls = [tc for tc in tool_calls if not (tc.engine == "data" and tc.action == "get_daily_history")]
                if len(tool_calls) < before_len:
                    logger.info(f"已过滤 {before_len - len(tool_calls)} 个多余的 data.get_daily_history 调用（已有 expert.data）")

            if not tool_calls:
                break

            # 4. 工具调用（并行执行所有专家）
            for tc in tool_calls:
                if tc.engine == "expert":
                    q = (tc.params.get("question") or "").strip()
                    if not q or len(q) < 4:
                        tc.params["question"] = analysis_message
                is_expert_call = tc.engine == "expert"
                expert_label = EXPERT_NAMES.get(tc.action, tc.action) if is_expert_call else ""
                yield {"event": "tool_call", "data": {
                    "engine": tc.engine, "action": tc.action, "params": tc.params,
                    "label": f"咨询{expert_label}" if is_expert_call else f"{tc.engine}.{tc.action}",
                    "round": round_num if deep_think else None,
                }}

            round_results: list[dict] = []
            async for r in self.execute_tools_streaming(tool_calls, context=runtime_context):
                round_results.append(r)
                is_expert = r.get("is_expert")
                expert_label = EXPERT_NAMES.get(r["action"], r["action"]) if is_expert else ""
                result_text = r.get("result", "")
                has_error = self._detect_tool_error(result_text, is_expert=bool(is_expert))
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
                    "round": round_num if deep_think else None,
                    **chart_data,
                }}
                if not early_insight_emitted:
                    early_insight = self._emitter.build_early_insight(r)
                    if early_insight:
                        yield early_insight
                        early_insight_emitted = True

            all_tool_results.extend(round_results)

            # 单轮模式直接跳出
            if not deep_think:
                break

            # deep_think 模式：让 LLM 基于已有数据决定是否继续补查
            logger.info(
                f"🔄 [{persona}] deep_think 第{round_num}轮完成, "
                f"本轮 {len(round_results)} 条, 累计 {len(all_tool_results)} 条"
            )
            next_think = await self._think_with_results(
                analysis_message, recalled_nodes, memories, all_tool_results, conv_history, persona, round_num
            )
            if not next_think.needs_data or not next_think.tool_calls:
                logger.info(f"🏁 [{persona}] deep_think 第{round_num}轮后 LLM 认为数据充足，停止补查")
                break
            current_tool_calls = next_think.tool_calls

        tool_results = all_tool_results

        # 5. 图谱自动学习
        await self.learn_from_context(message, tool_results)

        # 6. 流式回复
        expert_reply = ""
        if self._llm:
            logger.debug(f"开始 _reply_stream, tool_results={len(tool_results)}条, "
                         f"expert={len([r for r in tool_results if r.get('is_expert')])}条")
            async for token, full_text in self.generate_reply_stream(
                analysis_message, recalled_nodes, memories, tool_results, conv_history,
                persona=persona, enable_trade_plan=enable_trade_plan,
            ):
                expert_reply = full_text
                yield {"event": "reply_token", "data": {"token": token}}
            logger.debug(f"_reply_stream 完成, 回复长度={len(expert_reply)}")
        else:
            expert_reply = "LLM 未配置，无法生成回复。"

        if self._llm and expert_reply:
            critique = await self._self_critique(
                analysis_message,
                expert_reply,
                tool_results,
                persona=persona,
            )
            if not isinstance(critique, SelfCritiqueOutput):
                critique = SelfCritiqueOutput(**critique)
            yield {"event": "self_critique", "data": critique.model_dump()}

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
                        self._detect_tool_error(r.get("result", ""), is_expert=r.get("is_expert", False))
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

    async def _think_with_results(
        self,
        message: str,
        nodes: list[dict],
        memories: list[dict],
        tool_results: list[dict],
        history: list[dict],
        persona: str,
        round_num: int,
    ) -> ThinkOutput:
        """多轮渐进模式：带上之前工具结果，让 LLM 决定是否需要继续补查"""
        from llm.providers import ChatMessage
        llm = self._get_fast_llm()
        if not llm:
            return ThinkOutput(needs_data=False)

        # 构建已有工具结果摘要
        results_summary_parts = []
        for r in tool_results:
            engine = r.get("engine", "?")
            action = r.get("action", "?")
            result_text = r.get("result", "")[:500]
            results_summary_parts.append(f"[{engine}.{action}]: {result_text}")
        results_summary = "\n---\n".join(results_summary_parts)

        base_prompt = build_think_prompt(
            persona,
            current_date=get_current_date_context(),
            graph_context=format_graph_context(nodes),
            memory_context=format_memory_context(memories),
        )

        supplement = f"""

═══ 多轮渐进模式（第{round_num + 1}轮决策） ═══

你已经进行了 {round_num} 轮数据查询，获得了以下数据：
{results_summary}

请判断：
1. 如果已有数据足够给出全面分析 → "needs_data": false
2. 如果还需要补充关键数据 → "needs_data": true, 并给出需要补查的 tool_calls
   - 不要重复查询已有的数据
   - 最多补查 2-3 个工具
"""
        prompt = base_prompt + supplement

        try:
            messages = [ChatMessage("system", prompt)]
            for h in (history or []):
                role = "assistant" if h["role"] == "expert" else h["role"]
                messages.append(ChatMessage(role, h.get("content", "")))
            messages.append(ChatMessage("user", message))

            chunks: list[str] = []
            async for token in llm.chat_stream(messages):
                chunks.append(token)
            raw_text = "".join(chunks).strip()

            if not raw_text:
                return ThinkOutput(needs_data=False)

            # 复用 _think 的解析逻辑
            import re
            text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()

            candidates = [text]
            md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw_text, re.DOTALL)
            if md_match:
                candidates.insert(0, md_match.group(1).strip())
            candidates.append(raw_text)

            for candidate in candidates:
                json_str = self._extract_outermost_json(candidate)
                if json_str:
                    result = self._try_parse_think_json(json_str)
                    if result is not None:
                        logger.info(
                            f"🧠 [{persona}] R{round_num + 1} think_with_results: "
                            f"needs_data={result.needs_data}, tool_calls={len(result.tool_calls)}"
                        )
                        return result

        except Exception as e:
            logger.warning(f"_think_with_results R{round_num + 1} 异常: {e}")

        return ThinkOutput(needs_data=False)

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
        llm = self._get_fast_llm()
        if not llm:
            return ThinkOutput(needs_data=False)
        # 根据 persona 选择 system prompt
        prompt = build_think_prompt(
            persona,
            current_date=get_current_date_context(),
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
            async for token in llm.chat_stream(messages):
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
        决定需要咨询哪些专家，并为每个专家生成精准的子问题。
        """
        tool_calls: list[dict] = []
        # 拼合所有可用上下文：LLM 输出 + 用户原始消息
        combined = text + "\n" + user_message

        # ── 提取所有股票信息用于生成精准问题 ──
        # 1) 提取所有 6 位代码
        detected_codes: list[str] = re.findall(r'\b(\d{6})\b', combined)
        # 去重但保持顺序
        seen_codes: set[str] = set()
        unique_codes: list[str] = []
        for c in detected_codes:
            if c not in seen_codes:
                seen_codes.add(c)
                unique_codes.append(c)

        # 2) 从用户消息中提取股票名称（可能没有代码）
        name_map = self._get_stock_name_map()
        detected_names: dict[str, str] = {}  # name → code
        for name in sorted(name_map, key=len, reverse=True):  # 长名优先避免子串误匹配
            if len(name) >= 2 and name in user_message and name not in detected_names:
                code = name_map[name]
                detected_names[name] = code
                if code not in seen_codes:
                    seen_codes.add(code)
                    unique_codes.append(code)

        # 3) 构建股票提示字符串
        # 反向映射 code → name
        code_to_name: dict[str, str] = {v: k for k, v in name_map.items()}
        for name, code in detected_names.items():
            code_to_name[code] = name

        stock_hints: list[str] = []
        for code in unique_codes:
            name = code_to_name.get(code, "")
            if name:
                stock_hints.append(f"{name}({code})")
            else:
                stock_hints.append(f"({code})")

        # 兼容旧逻辑的单股票变量
        stock_hint = "、".join(stock_hints) if stock_hints else ""
        detected_code = unique_codes[0] if unique_codes else ""

        if len(unique_codes) > 1:
            logger.info(f"容错解析检测到多只股票: {stock_hints}")

        # ── 为不同专家生成精准问题的辅助函数 ──
        def _make_single_stock_question(expert_type: str, single_hint: str) -> str:
            """为单只股票生成精准问题"""
            if expert_type == "data":
                return f"查询{single_hint}最近30天行情走势、成交量变化和涨跌幅"
            elif expert_type == "quant":
                return f"分析{single_hint}的技术指标(RSI/MACD/KDJ)，给出支撑位和阻力位"
            elif expert_type == "info":
                return f"查询{single_hint}最近的新闻和公告，评估消息面利好利空"
            elif expert_type == "industry":
                return f"分析{single_hint}所在行业的产业链位置和行业周期阶段"
            return user_message

        def make_question(expert_type: str) -> str:
            base = user_message
            if stock_hint:
                # 有具体股票：围绕股票做多维度分析
                if expert_type == "data":
                    return f"查询{stock_hint}最近30天行情走势、成交量变化和涨跌幅"
                elif expert_type == "quant":
                    return f"分析{stock_hint}的技术指标(RSI/MACD/KDJ)，给出支撑位和阻力位"
                elif expert_type == "info":
                    return f"查询{stock_hint}最近的新闻和公告，评估消息面利好利空"
                elif expert_type == "industry":
                    return f"分析{stock_hint}所在行业的产业链位置和行业周期阶段"
            else:
                # 无具体股票：发散式全市场扫描（核心改动）
                if expert_type == "data":
                    return ("扫描全市场行情概览，找出今日成交量较近期显著放大、"
                            "涨幅在3%~7%之间的强势股；同时关注近5天连续放量上涨的个股，按涨幅排序列出前10只")
                elif expert_type == "quant":
                    return ("用条件选股筛选技术面强势的股票：换手率大于3%、涨幅为正的股票，"
                            "列出前10只；额外关注近期MACD金叉、RSI脱离超卖区的个股")
                elif expert_type == "info":
                    return ("扫描近期A股最重大的新闻、政策和行业动态，"
                            "找出有明确利好催化的板块和受益个股，按消息重要性排序")
                elif expert_type == "industry":
                    return ("分析当前A股哪些行业板块处于景气上行期或有新的政策催化，"
                            "推荐最具投资价值的2-3个板块，给出每个板块的龙头股")
            return base

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
            # 多只股票时：为每只股票分别创建独立的专家调用
            if len(stock_hints) > 1:
                for single_hint in stock_hints:
                    for expert_type in ["data", "quant", "info", "industry"]:
                        q = _make_single_stock_question(expert_type, single_hint)
                        tool_calls.append({
                            "engine": "expert",
                            "action": expert_type,
                            "params": {"question": q},
                        })
                logger.info(
                    f"think 容错解析: 综合分析问题，{len(stock_hints)}只股票 × 4个专家"
                    f" = {len(tool_calls)}个调用 ({stock_hints})"
                )
            else:
                for expert_type in ["data", "quant", "info", "industry"]:
                    tool_calls.append({
                        "engine": "expert",
                        "action": expert_type,
                        "params": {"question": make_question(expert_type)},
                    })
                logger.info("think 容错解析: 综合分析问题，调用全部4个专家（精准子问题）")
            return ThinkOutput(
                needs_data=True,
                tool_calls=[ToolCall(**tc) for tc in tool_calls],
                reasoning=f"容错解析: 综合分析问题，{len(stock_hints)}只股票×4个专家",
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
            # 多只股票时：为每只股票分别创建独立的专家调用
            if len(stock_hints) > 1:
                for single_hint in stock_hints:
                    for expert_type in detected_experts:
                        q = _make_single_stock_question(expert_type, single_hint)
                        tool_calls.append({
                            "engine": "expert",
                            "action": expert_type,
                            "params": {"question": q},
                        })
            else:
                for expert_type in detected_experts:
                    tool_calls.append({
                        "engine": "expert",
                        "action": expert_type,
                        "params": {"question": make_question(expert_type)},
                    })

            logger.info(
                f"think 容错解析: 检测到需要咨询 {list(detected_experts)}"
                f"{'，' + str(len(stock_hints)) + '只股票' if len(stock_hints) > 1 else ''}（精准子问题）"
            )
            return ThinkOutput(
                needs_data=True,
                tool_calls=[ToolCall(**tc) for tc in tool_calls],
                reasoning=f"容错解析: 检测到需要咨询{','.join(detected_experts)}",
            )

        # ── 检测直接数据查询（仅用于非常简单的请求）──
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
        updated_existing = False  # 是否更新了已有节点的 updated_at

        for code, name in candidates.items():
            profile = profiles.get(code, {})
            industry = profile.get("industry", "")
            zjh_industry = profile.get("zjh_industry", "")
            scope = profile.get("scope", "")

            # ── Step 1: 创建 StockNode（或更新已有节点的 updated_at） ──
            if code in existing_stocks:
                stock_node_id = existing_stocks[code]
                # 更新 updated_at — 让模糊召回的时间排序反映真实活跃度
                self._graph.graph.nodes[stock_node_id]["updated_at"] = datetime.now().isoformat()
                updated_existing = True
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
                    # 更新 updated_at
                    self._graph.graph.nodes[sector_node_id]["updated_at"] = datetime.now().isoformat()
                    updated_existing = True
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
                        # 更新 updated_at
                        self._graph.graph.nodes[mat_node_id]["updated_at"] = datetime.now().isoformat()
                        updated_existing = True
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
        has_changes = added_stocks or added_sectors or added_edges or added_materials or updated_existing
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
        enable_trade_plan: bool = False,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复（含 <think> 标签过滤），yield (token, accumulated_text)"""
        from llm.providers import ChatMessage
        llm = self._get_quality_llm()
        if not llm:
            return

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

        # ── 构建数据就绪声明（防止 LLM 幻觉式调用工具）──
        expert_count = len([r for r in tool_results if r.get("is_expert")])
        data_ready_notice = ""
        if expert_count > 0:
            data_ready_notice = (
                f"\n\n## ⚠️ 重要：所有数据已就绪\n"
                f"你的 {expert_count} 位专家已经全部返回了分析结果，数据就在上面。\n"
                f"**请直接基于上面的专家分析报告进行综合研判，不要说「我在等数据」「让我查一下」之类的话。**\n"
                f"**禁止输出任何工具调用格式（如 [tool:...]、<tool_call>、```tool 等），你不需要也不能调用任何工具。**\n"
                f"**你的唯一任务是：阅读专家报告 → 综合分析 → 给出你的判断和建议。**\n"
                f"\n"
                f"## 📋 回复格式要求\n"
                f"你必须在回复中**大量引用专家报告中的具体数据**，包括但不限于：\n"
                f"- 📊 数据专家提供的行情数据（价格、涨跌幅、成交量、市值等）\n"
                f"- 🔬 量化专家提供的技术指标（RSI、MACD、布林带、因子评分等）\n"
                f"- 📰 资讯专家提供的新闻和情感分析结果\n"
                f"- 🏭 产业链专家提供的行业分析和资金流向\n"
                f"不要只给结论——每个判断都要附上来自专家报告的原始数据作为证据。\n"
                f"输出应为**详细的研判报告**，而非简短的三两句结论。\n"
            )
        elif not tool_results:
            data_ready_notice = (
                "\n\n## 提示\n"
                "本次没有调用专家团队（可能是闲聊或简单问题），请直接回复用户。\n"
                "**禁止输出任何工具调用格式。**\n"
            )

        # 根据 persona 选择 system prompt
        system = build_reply_system(
            persona,
            current_date=get_current_date_context(),
        ) + "\n\n" + "\n\n".join(context_parts) + data_ready_notice

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

        # 统一声明：数据来自实时工具，不受 LLM 训练截止限制
        system += (
            "\n\n⚠️ 重要：专家团队的所有数据通过工具从 AKShare/EastMoney 等数据源实时拉取，"
            "不受模型训练截止日期限制。绝对不要提及「知识截止」「训练数据截止」等字眼。"
        )

        # 注入交易计划格式约定（仅当用户开启策略卡片开关时）
        trade_plan_reminder = ""
        if enable_trade_plan:
            system += TRADE_PLAN_PROMPT
            trade_plan_reminder = (
                "\n\n📌 提醒：用户已开启「策略卡片」功能。如果你的分析涉及具体股票且有操作建议，"
                "请务必在回复末尾用【交易计划】...【/交易计划】格式输出交易计划卡片。"
            )

        # 构建消息列表（含对话历史）
        messages = [ChatMessage("system", system)]
        for h in (history or []):
            role = "assistant" if h["role"] == "expert" else h["role"]
            content = h.get("content", "")
            messages.append(ChatMessage(role, content))
        messages.append(ChatMessage("user", message + trade_plan_reminder))

        # 上下文窗口保护
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
        msg_dicts = self._context_guard.guard_messages(msg_dicts)
        messages = [ChatMessage(m["role"], m["content"]) for m in msg_dicts]

        accumulated = ""
        in_skip = False          # 跳过区域（内容被丢弃）
        skip_end_tag = ""        # 当前跳过区域的结束标签
        raw_buffer = ""

        # 内容被丢弃的标签（对用户无意义的工具调用 + LLM 思考过程）
        SKIP_TAGS = {
            "<think>": "</think>",
            "<minimax:tool_call>": "</minimax:tool_call>",
            "<minimax:search_result>": "</minimax:search_result>",
            "<tool_call>": "</tool_call>",
            "<tool_code>": "</tool_code>",
            "[TOOL_CALL]": "[/TOOL_CALL]",
        }
        # 正则过滤：LLM 可能幻觉出 [tool:xxx]...[/tool] 格式
        HALLUCINATED_TOOL_RE = re.compile(r'\[tool:[^\]]*\].*?\[/tool\]', re.DOTALL)

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
                    # 保护：如果 skip 区域累积超过 50000 字节还未关闭，强制退出
                    if skip_bytes > 50000:
                        logger.warning(f"skip 区域未关闭(>{skip_bytes}B)，强制退出: {skip_end_tag}")
                        in_skip = False
                        raw_buffer = ""
                        skip_end_tag = ""
                        skip_bytes = 0
                    elif len(raw_buffer) > 200:
                        raw_buffer = raw_buffer[-20:]
                    continue

                # 正常正文：检查是否可能是不完整的标签开头
                # 仅当 buffer 以 "<" 开头且很短时才等待（避免误判正文中的 < 符号）
                if raw_buffer.startswith("<") and not raw_buffer.endswith(">") and len(raw_buffer) < 30:
                    continue
                # 安全阀：buffer 超过 30 字符仍未闭合，说明不是标签，直接输出
                if len(raw_buffer) >= 30 and "<" in raw_buffer and ">" not in raw_buffer:
                    pass  # 不 continue，直接往下走输出

                if raw_buffer:
                    # 清洗幻觉工具调用 [tool:xxx]...[/tool]
                    cleaned = HALLUCINATED_TOOL_RE.sub("", raw_buffer)
                    if cleaned:
                        accumulated += cleaned
                        yield cleaned, accumulated
                    raw_buffer = ""

            if raw_buffer and not in_skip:
                cleaned = HALLUCINATED_TOOL_RE.sub("", raw_buffer)
                if cleaned:
                    accumulated += cleaned
                    yield cleaned, accumulated

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
