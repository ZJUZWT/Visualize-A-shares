"""Orchestrator — Agent 编排入口"""

import asyncio
from typing import AsyncGenerator

from loguru import logger

from llm.providers import BaseLLMProvider
from .schemas import AnalysisRequest, AgentVerdict
from .personas import AGENT_PERSONAS
from .runner import run_agent, AgentRunError
from .aggregator import aggregate_verdicts
from .memory import AgentMemory
from .data_fetcher import DataFetcher


class Orchestrator:
    """编排器 — 驱动 PreScreen → 并行分析 → 聚合 流水线"""

    ANALYSIS_AGENTS = ["fundamental", "info", "quant"]
    AGENT_TIMEOUT = 30

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        memory: AgentMemory,
        data_fetcher: DataFetcher | None = None,
    ):
        self._llm = llm_provider
        self._memory = memory
        self._data = data_fetcher or DataFetcher()

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

    async def _run_with_timeout(
        self, role: str, target: str, data_ctx: dict,
        memory_ctx: list, calibrations: dict,
    ) -> AgentVerdict:
        cal = calibrations.get(role, 0.5)
        return await asyncio.wait_for(
            run_agent(
                agent_role=role, target=target, data_context=data_ctx,
                memory_context=memory_ctx, calibration_weight=cal,
                llm_provider=self._llm,
            ),
            timeout=self.AGENT_TIMEOUT,
        )

    def _get_calibrations(self) -> dict[str, float]:
        return {
            role: persona["confidence_calibration"]
            for role, persona in AGENT_PERSONAS.items()
        }
