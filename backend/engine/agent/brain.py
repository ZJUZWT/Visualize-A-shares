"""
AgentBrain — Main Agent 决策大脑

每次运行流程：
1. 标的筛选（watchlist + 量化筛选 + 已有持仓）
2. 逐标的分析（调用专家工具层获取数据）
3. LLM 综合决策
4. 自动执行（生成 trade_plan → execute_trade）
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import date
from loguru import logger

from engine.agent.db import AgentDB
from engine.agent.data_hunger import DataHungerService
from engine.agent.decision_quality import (
    build_decision_context,
    build_output_contract,
    build_system_prompt,
    gate_decisions,
    parse_decision_payload,
)
from engine.agent.execution import ExecutionCoordinator
from engine.agent.memory import MemoryManager
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator


class AgentBrain:
    """Agent 决策大脑"""

    def __init__(self, portfolio_id: str):
        self.portfolio_id = portfolio_id
        self.db = AgentDB.get_instance()
        self.service = AgentService(db=self.db, validator=TradeValidator())
        self.execution = ExecutionCoordinator(portfolio_id, self.service)
        self.memory = MemoryManager(self.db)
        self.data_hunger = DataHungerService(db=self.db, agent_service=self.service)

    async def execute(self, run_id: str):
        """执行一次完整的分析→决策→执行流程"""
        start = time.monotonic()
        logger.info(f"🧠 AgentBrain 运行开始: run_id={run_id}")

        try:
            state_before = await self.service.get_agent_state(self.portfolio_id)
            await self.service.update_brain_run(run_id, {
                "state_before": state_before,
            })
            config = await self.service.get_brain_config()
            signal_hits = await self._scan_watch_signals()
            triggered_signal_ids = self._collect_triggered_signal_ids(signal_hits)

            # Step 1: 标的筛选
            candidates = await self._select_candidates(config)
            candidates = self._merge_signal_candidates(candidates, signal_hits)
            await self.service.update_brain_run(run_id, {
                "candidates": candidates,
                "triggered_signal_ids": triggered_signal_ids,
            })
            logger.info(f"🧠 候选标的: {len(candidates)} 只")

            if not candidates:
                elapsed = time.monotonic() - start
                state_after = await self.service.get_agent_state(self.portfolio_id)
                await self.service.update_brain_run(run_id, {
                    "status": "completed",
                    "decisions": [],
                    "state_after": state_after,
                    "info_digest_ids": [],
                    "triggered_signal_ids": triggered_signal_ids,
                    "execution_summary": {
                        "candidate_count": 0,
                        "analysis_count": 0,
                        "decision_count": 0,
                        "plan_count": 0,
                        "trade_count": 0,
                        "elapsed_seconds": round(elapsed, 4),
                    },
                })
                return

            # Step 2: 逐标的分析
            analysis_results = await self._analyze_candidates(candidates, config)
            await self.service.update_brain_run(run_id, {
                "analysis_results": analysis_results,
            })
            logger.info(f"🧠 分析完成: {len(analysis_results)} 只")

            digest_results = await self._digest_candidates(run_id, candidates, signal_hits)
            info_digest_ids = [
                digest["id"] for digest in digest_results
                if isinstance(digest, dict) and digest.get("id")
            ]
            self._current_digests = digest_results
            self._current_triggered_signals = signal_hits
            await self.service.update_brain_run(run_id, {
                "info_digest_ids": info_digest_ids,
                "triggered_signal_ids": triggered_signal_ids,
            })

            # Step 3: LLM 综合决策
            portfolio = await self.service.get_portfolio(self.portfolio_id)
            decisions = await self._make_decisions(analysis_results, portfolio, config, run_id)
            await self.service.update_brain_run(run_id, {
                "decisions": decisions,
            })
            logger.info(f"🧠 决策完成: {len(decisions)} 个操作")

            # Step 4: 自动执行
            self._active_run_id = run_id
            plan_ids, trade_ids = await self._execute_decisions(decisions)
            elapsed = time.monotonic() - start
            state_after = await self.service.get_agent_state(self.portfolio_id)
            await self.service.update_brain_run(run_id, {
                "status": "completed",
                "plan_ids": plan_ids,
                "trade_ids": trade_ids,
                "info_digest_ids": info_digest_ids,
                "triggered_signal_ids": triggered_signal_ids,
                "state_after": state_after,
                "execution_summary": {
                    "candidate_count": len(candidates),
                    "analysis_count": len(analysis_results),
                    "digest_count": len(digest_results),
                    "triggered_signal_count": len(triggered_signal_ids),
                    "decision_count": len(decisions),
                    "plan_count": len(plan_ids),
                    "trade_count": len(trade_ids),
                    "elapsed_seconds": round(elapsed, 4),
                },
            })
            logger.info(f"🧠 AgentBrain 运行完成: {elapsed:.1f}s, {len(plan_ids)} plans, {len(trade_ids)} trades")

        except Exception as e:
            logger.error(f"🧠 AgentBrain 运行失败: {e}\n{traceback.format_exc()}")
            await self.service.update_brain_run(run_id, {
                "status": "failed",
                "error_message": str(e),
            })

    # ── Step 1: 标的筛选 ──────────────────────────────

    async def _select_candidates(self, config: dict) -> list[dict]:
        """合并 watchlist + 量化筛选 + 已有持仓"""
        watchlist = await self.service.list_watchlist()
        quant_top = await self._quant_screen(config.get("quant_top_n", 20))
        positions = await self.service.get_positions(self.portfolio_id, "open")

        return self._merge_candidates(
            watchlist, quant_top, positions,
            max_n=config.get("max_candidates", 30),
        )

    def _merge_candidates(
        self,
        watchlist: list[dict],
        quant_top: list[dict],
        positions: list[dict],
        max_n: int = 30,
    ) -> list[dict]:
        """合并去重候选标的"""
        seen = set()
        result = []

        # 已有持仓优先
        for p in positions:
            code = p["stock_code"]
            if code not in seen:
                seen.add(code)
                result.append({
                    "stock_code": code,
                    "stock_name": p.get("stock_name", code),
                    "source": "position",
                })

        # 关注列表
        for w in watchlist:
            code = w["stock_code"]
            if code not in seen:
                seen.add(code)
                result.append({
                    "stock_code": code,
                    "stock_name": w.get("stock_name", code),
                    "source": "watchlist",
                })

        # 量化筛选
        for q in quant_top:
            code = q["stock_code"]
            if code not in seen:
                seen.add(code)
                result.append({
                    "stock_code": code,
                    "stock_name": q.get("stock_name", code),
                    "source": "quant",
                    "score": q.get("score"),
                })

        return result[:max_n]

    async def _quant_screen(self, top_n: int = 20) -> list[dict]:
        """量化筛选 — 调用 QuantEngine 因子打分"""
        try:
            from engine.quant import get_quant_engine
            from engine.data import get_data_engine

            de = get_data_engine()
            snapshot_df = de.get_snapshot()
            if snapshot_df is None or snapshot_df.empty:
                logger.warning("🧠 量化筛选: snapshot 为空")
                return []

            qe = get_quant_engine()
            result = qe.predict(snapshot_df)

            sorted_preds = sorted(
                result.predictions.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:top_n]

            return [
                {"stock_code": code, "score": round(score, 4), "stock_name": code}
                for code, score in sorted_preds
            ]
        except Exception as e:
            logger.warning(f"🧠 量化筛选失败: {e}")
            return []

    # ── Step 2: 逐标的分析 ────────────────────────────

    async def _analyze_candidates(self, candidates: list[dict], config: dict) -> list[dict]:
        """对每个候选标的调用专家工具层获取数据"""
        results = []
        for c in candidates:
            code = c["stock_code"]
            try:
                analysis = await self._analyze_single(code)
                analysis["stock_code"] = code
                analysis["stock_name"] = c.get("stock_name", code)
                analysis["source"] = c.get("source", "unknown")
                results.append(analysis)
            except Exception as e:
                logger.warning(f"🧠 分析 {code} 失败: {e}")
                results.append({
                    "stock_code": code,
                    "stock_name": c.get("stock_name", code),
                    "source": c.get("source", "unknown"),
                    "error": str(e),
                })
        return results

    async def _scan_watch_signals(self) -> list[dict]:
        hunger = getattr(self, "data_hunger", None)
        if hunger is None:
            return []
        return await hunger.scan_watch_signals(self.portfolio_id)

    def _collect_triggered_signal_ids(self, signal_hits: list[dict]) -> list[str]:
        signal_ids: list[str] = []
        for hit in signal_hits:
            signal_id = hit.get("signal_id")
            if signal_id and signal_id not in signal_ids:
                signal_ids.append(signal_id)
        return signal_ids

    def _merge_signal_candidates(self, candidates: list[dict], signal_hits: list[dict]) -> list[dict]:
        merged = list(candidates)
        seen = {candidate.get("stock_code") for candidate in candidates if candidate.get("stock_code")}
        for hit in signal_hits:
            stock_code = hit.get("stock_code")
            if not stock_code or stock_code in seen:
                continue
            seen.add(stock_code)
            merged.append({
                "stock_code": stock_code,
                "stock_name": hit.get("stock_name", stock_code),
                "source": "watch_signal",
            })
        return merged

    async def _digest_candidates(
        self,
        run_id: str,
        candidates: list[dict],
        signal_hits: list[dict],
    ) -> list[dict]:
        hunger = getattr(self, "data_hunger", None)
        if hunger is None:
            return []

        hits_by_stock: dict[str, list[dict]] = {}
        for hit in signal_hits:
            stock_code = hit.get("stock_code")
            if not stock_code:
                continue
            hits_by_stock.setdefault(stock_code, []).append(hit)

        digests: list[dict] = []
        for candidate in candidates:
            stock_code = candidate.get("stock_code")
            if not stock_code:
                continue
            try:
                digest = await hunger.execute_and_digest(
                    self.portfolio_id,
                    run_id,
                    stock_code,
                    triggers=hits_by_stock.get(stock_code, []),
                )
            except Exception as e:
                logger.warning(f"🧠 digest {stock_code} 失败: {e}")
                continue
            if isinstance(digest, dict):
                digests.append(digest)
        return digests

    async def _analyze_single(self, code: str) -> dict:
        """分析单个标的"""
        from engine.expert.tools import ExpertTools
        from engine.data import get_data_engine
        from engine.cluster import get_cluster_engine
        from llm import LLMProviderFactory, llm_settings

        de = get_data_engine()
        ce = get_cluster_engine()
        llm = LLMProviderFactory.create(llm_settings)
        tools = ExpertTools(de, ce, llm)

        analysis = {}

        try:
            analysis["daily"] = await tools.execute("data", "get_daily_history", {"code": code, "days": 30})
        except Exception as e:
            analysis["daily"] = f"获取失败: {e}"

        try:
            analysis["indicators"] = await tools.execute("quant", "get_technical_indicators", {"code": code})
        except Exception as e:
            analysis["indicators"] = f"获取失败: {e}"

        return analysis

    # ── Step 3: LLM 综合决策 ──────────────────────────

    async def _make_decisions(
        self, analysis_results: list[dict], portfolio: dict, config: dict, run_id: str
    ) -> list[dict]:
        """LLM 综合决策"""
        from llm import LLMProviderFactory, llm_settings
        from llm.providers import ChatMessage

        llm = LLMProviderFactory.create(llm_settings)
        memory_rules = await self._get_active_rules()
        current_digests = getattr(self, "_current_digests", [])
        current_triggered_signals = getattr(self, "_current_triggered_signals", [])

        system_prompt = build_system_prompt()
        decision_context = build_decision_context(
            analysis_results=analysis_results,
            portfolio=portfolio,
            config=config,
            memory_rules=memory_rules,
            digests=current_digests,
            signal_hits=current_triggered_signals,
        )
        output_contract = build_output_contract()
        user_prompt = f"{decision_context}\n\n## 输出要求\n{output_contract}"

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        # 流式收集
        chunks: list[str] = []
        async for token in llm.chat_stream(messages):
            chunks.append(token)
        raw = "".join(chunks)

        parsed_payload = parse_decision_payload(raw)
        gate_result = gate_decisions(
            parsed_payload,
            min_confidence=float(config.get("min_decision_confidence", 0.65)),
        )
        decisions = gate_result.accepted

        await self.service.update_brain_run(run_id, {
            "thinking_process": {
                "system_prompt": system_prompt,
                "decision_context": decision_context,
                "output_contract": output_contract,
                "raw_output": raw,
                "parsed_payload": parsed_payload,
                "assessment": gate_result.assessment,
                "self_critique": gate_result.self_critique,
                "follow_up_questions": gate_result.follow_up_questions,
                "gate_result": {
                    "requires_wait": gate_result.requires_wait,
                    "accepted_count": len(gate_result.accepted),
                    "rejected_count": len(gate_result.rejected),
                    "rejections": [
                        {
                            "reason": item["reason"],
                            "stock_code": (
                                item.get("decision", {}).get("stock_code")
                                if isinstance(item.get("decision"), dict)
                                else None
                            ),
                        }
                        for item in gate_result.rejected
                    ],
                },
                "parsed_decisions": gate_result.accepted,
                "digests": current_digests,
                "triggered_signals": current_triggered_signals,
            },
        })

        return decisions

    async def _get_active_rules(self) -> list[dict]:
        memory_manager = getattr(self, "memory", None)
        if memory_manager is None:
            return []
        return await memory_manager.get_active_rules(limit=20)

    def _format_memory_rules(self, rules: list[dict]) -> str:
        if not rules:
            return ""

        lines = [
            "",
            "## 历史经验",
            "以下是你从过去交易中积累的经验规则，请在决策时参考：",
        ]
        for idx, rule in enumerate(rules, start=1):
            confidence = float(rule.get("confidence", 0))
            lines.append(f"{idx}. {rule['rule_text']} (置信度: {confidence:.0%})")
        return "\n".join(lines)

    def _format_digest_context(self, digests: list[dict], signal_hits: list[dict]) -> str:
        if not digests and not signal_hits:
            return ""

        lines = ["", "## 信息消化摘要"]
        if signal_hits:
            lines.append("观察信号命中：")
            for hit in signal_hits:
                stock_code = hit.get("stock_code", "unknown")
                matched_keywords = ",".join(hit.get("matched_keywords") or [])
                lines.append(f"- {stock_code}: 关键词 [{matched_keywords}]")
        if digests:
            lines.append("Digest：")
            for digest in digests:
                stock_code = digest.get("stock_code", "unknown")
                impact = digest.get("impact_assessment", "none")
                summary = digest.get("summary") or digest.get("strategy_relevance") or ""
                evidence = digest.get("key_evidence") or []
                evidence_text = ", ".join(str(item) for item in evidence)
                lines.append(f"- {stock_code}: {summary}")
                lines.append(f"  impact={impact}")
                if evidence_text:
                    lines.append(f"  evidence={evidence_text}")
        return "\n".join(lines)

    # ── Step 4: 自动执行 ──────────────────────────────

    async def _execute_decisions(
        self,
        decisions: list[dict] | str,
        run_id: str | list[dict] | None = None,
    ) -> tuple[list[str], list[str]]:
        """执行决策：brain 只调 execution 协调器"""
        plan_ids: list[str] = []
        trade_ids: list[str] = []
        execution = getattr(self, "execution", ExecutionCoordinator(self.portfolio_id, self.service))
        if isinstance(decisions, str):
            effective_run_id = decisions
            actual_decisions = run_id if isinstance(run_id, list) else []
        else:
            actual_decisions = decisions
            effective_run_id = run_id if isinstance(run_id, str) else getattr(self, "_active_run_id", "manual")

        for d in actual_decisions:
            action = d.get("action", "")
            if action in ("hold", "ignore", ""):
                continue

            try:
                plan = await execution.create_plan_from_decision(effective_run_id, d)
                plan_ids.append(plan["id"])

                result = await execution.execute_plan(effective_run_id, plan["id"], d)
                if result.get("trade_id"):
                    trade_ids.append(result["trade_id"])

                logger.info(f"🧠 执行: {action} {d['stock_code']} x{d.get('quantity', 100)}")

            except Exception as e:
                logger.warning(f"🧠 执行 {d['stock_code']} 失败: {e}")

        return plan_ids, trade_ids
