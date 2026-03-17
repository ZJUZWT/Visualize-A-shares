"""Orchestrator — Agent 编排入口"""

import asyncio
from datetime import datetime
from typing import AsyncGenerator
from zoneinfo import ZoneInfo

from loguru import logger

from llm.capability import LLMCapability
from .schemas import AnalysisRequest, AgentVerdict, Blackboard
from .personas import AGENT_PERSONAS
from .runner import run_agent, AgentRunError
from .aggregator import aggregate_verdicts
from .memory import AgentMemory
from .data_fetcher import DataFetcher
from .debate import run_debate, persist_debate


class Orchestrator:
    """编排器 — 驱动 PreScreen → 并行分析 → 聚合 流水线"""

    ANALYSIS_AGENTS = ["fundamental", "info", "quant"]
    AGENT_TIMEOUT = 30

    def __init__(
        self,
        llm_capability: LLMCapability,
        memory: AgentMemory,
        data_fetcher: DataFetcher | None = None,
        rag_store=None,   # RAGStore | None
    ):
        self._llm = llm_capability
        self._memory = memory
        self._data = data_fetcher or DataFetcher()
        self._rag = rag_store

    async def analyze(
        self, request: AnalysisRequest
    ) -> AsyncGenerator[dict, None]:
        """执行分析流水线，通过 async generator 推送 SSE 事件"""
        target = request.target
        calibrations = self._get_calibrations()

        # PreScreen（depth=quick 跳过）
        if request.depth != "quick":
            yield {"event": "phase", "data": {"step": "prescreen", "status": "running"}}
            # Phase 1: 默认放行，Phase 2 接入 InfoEngine 后启用短路逻辑
            yield {"event": "phase", "data": {"step": "prescreen", "status": "done", "result": "continue"}}

        # 并行分析
        yield {"event": "phase", "data": {
            "step": "parallel_analysis", "status": "running",
            "agents": self.ANALYSIS_AGENTS,
        }}

        # 异步获取数据（不阻塞事件循环）
        data_map = await self._data.fetch_all(target)

        # RAG 注入：检索历史报告，注入 data_map
        if self._rag:
            try:
                from config import settings
                historical = self._rag.search(target, top_k=settings.rag.search_top_k)
                data_map["historical_reports"] = historical
            except Exception as e:
                logger.warning(f"RAG 检索失败 [{target}]: {e}")

        verdicts: list[AgentVerdict] = []
        tasks = []
        for role in self.ANALYSIS_AGENTS:
            memory_ctx = self._memory.recall(role, f"分析 {target}", top_k=3)
            tasks.append(self._run_with_timeout(
                role, target, data_map.get(role, {}), memory_ctx, calibrations
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for role, result in zip(self.ANALYSIS_AGENTS, results):
            if isinstance(result, Exception):
                logger.warning(f"Agent [{role}] 失败: {result}")
                yield {"event": "agent_done", "data": {
                    "agent": role, "status": "failed", "error": str(result),
                }}
            else:
                verdicts.append(result)
                yield {"event": "agent_done", "data": {
                    "agent": role, "signal": result.signal,
                    "confidence": result.confidence, "score": result.score,
                }}

        # 全部失败 → 返回 error
        if not verdicts:
            yield {"event": "error", "data": {"message": "所有分析 Agent 均失败，无法生成报告"}}
            return

        # 聚合
        yield {"event": "phase", "data": {"step": "aggregation", "status": "running"}}
        report = aggregate_verdicts(target, verdicts, calibrations)

        # 持久化记忆
        for v in verdicts:
            try:
                self._memory.store(
                    agent_role=v.agent_role,
                    target=target,
                    content=f"signal={v.signal}, score={v.score:.2f}, confidence={v.confidence:.2f}",
                    metadata={"signal": v.signal, "confidence": v.confidence},
                )
            except Exception as e:
                logger.warning(f"记忆存储失败 [{v.agent_role}]: {e}")

        yield {"event": "result", "data": {"report": report.model_dump(mode="json")}}

        # 专家辩论（仅 depth=deep 且 LLM 可用时触发）
        judge_verdict = None
        if request.depth == "deep" and self._llm.enabled:
            try:
                now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
                blackboard = Blackboard(
                    target=target,
                    debate_id=f"{target}_{now.strftime('%Y%m%d%H%M%S')}",
                    worker_verdicts=verdicts,
                    conflicts=report.conflicts,
                    max_rounds=3,
                )
                async for event in run_debate(
                    blackboard=blackboard,
                    llm=self._llm._provider,
                    memory=self._memory,
                    data_fetcher=self._data,
                ):
                    yield event
                    # 捕获裁判结果用于 RAG 存储
                    if event.get("event") == "judge_verdict":
                        judge_verdict = event.get("data")
            except Exception as e:
                logger.error(f"专家辩论异常 [{target}]: {e}")
                yield {"event": "debate_error", "data": {"error": str(e)}}

        # RAG 写入：将分析报告存入向量库供后续检索
        if self._rag and report:
            try:
                from engine.arena.rag.schemas import ReportRecord
                from engine.arena.rag.store import RAGStore
                now_utc = datetime.now(tz=ZoneInfo("UTC"))
                self._rag.store(ReportRecord(
                    report_id=RAGStore.make_report_id(target, "agent_analysis", now_utc),
                    code=target,
                    summary=report.summary,
                    signal=report.overall_signal,
                    score=report.score,
                    report_type="agent_analysis",
                    created_at=now_utc,
                ))
                # 辩论裁决也存入 RAG
                if judge_verdict and judge_verdict.get("summary"):
                    self._rag.store(ReportRecord(
                        report_id=RAGStore.make_report_id(target, "debate", now_utc),
                        code=target,
                        summary=judge_verdict["summary"],
                        signal=judge_verdict.get("signal"),
                        score=judge_verdict.get("score"),
                        report_type="debate",
                        created_at=now_utc,
                    ))
            except Exception as e:
                logger.warning(f"RAG 报告存储失败 [{target}]: {e}")

    async def _run_with_timeout(
        self, role: str, target: str, data_ctx: dict,
        memory_ctx: list, calibrations: dict,
    ) -> AgentVerdict:
        cal = calibrations.get(role, 0.5)
        return await asyncio.wait_for(
            run_agent(
                agent_role=role, target=target, data_context=data_ctx,
                memory_context=memory_ctx, calibration_weight=cal,
                llm_capability=self._llm,
            ),
            timeout=self.AGENT_TIMEOUT,
        )

    def _get_calibrations(self) -> dict[str, float]:
        return {
            role: persona["confidence_calibration"]
            for role, persona in AGENT_PERSONAS.items()
        }
