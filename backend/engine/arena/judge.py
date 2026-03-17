"""JudgeRAG — 基于 ExpertAgent 的 RAG 裁判"""

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, AsyncGenerator
from zoneinfo import ZoneInfo

from loguru import logger

from engine.arena.schemas import Blackboard, JudgeVerdict, RoundEval, RoundEvalSide

if TYPE_CHECKING:
    from engine.expert.agent import ExpertAgent


class JudgeRAG:
    """RAG 裁判 — 基于 ExpertAgent 的辩论裁判

    薄编排层：不复制 ExpertAgent 逻辑，只组合调用其公开方法。
    """

    def __init__(self, expert: "ExpertAgent"):
        self._expert = expert

    # ── 内部辅助 ──────────────────────────────────────────

    def _build_topic_query(self, topic: str) -> str:
        return f"分析辩论题目：{topic}，梳理多空双方的核心论点、相关股票标的、关键数据指标和潜在风险"

    def _build_verdict_query(self, blackboard: Blackboard) -> str:
        rounds = blackboard.round
        target = blackboard.target
        bull_entries = [e for e in blackboard.transcript if e.role == "bull_expert"]
        bear_entries = [e for e in blackboard.transcript if e.role == "bear_expert"]
        bull_summary = bull_entries[-1].argument[:300] if bull_entries else ""
        bear_summary = bear_entries[-1].argument[:300] if bear_entries else ""
        return (
            f"对股票 {target} 进行了 {rounds} 轮辩论。"
            f"多头最终论点：{bull_summary}。"
            f"空头最终论点：{bear_summary}。"
            f"请综合评判，给出最终裁决。"
        )

    def _rename_event(self, event: dict, phase: str) -> dict:
        """将 ExpertAgent 产出的事件重命名为 judge_ 前缀并注入 phase"""
        name_map = {
            "graph_recall": "judge_graph_recall",
            "tool_call": "judge_tool_call",
            "tool_result": "judge_tool_result",
        }
        ev = event.get("event", "")
        new_ev = name_map.get(ev, ev)
        data = dict(event.get("data", {}))
        data["phase"] = phase
        return {"event": new_ev, "data": data}

    def _parse_briefing(self, reply: str) -> dict:
        """从 ExpertAgent 回复中提取 briefing dict"""
        # 尝试提取 JSON
        json_match = re.search(r'\{[^{}]{20,}\}', reply, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
        # fallback: 构造简单 briefing
        return {
            "summary": reply[:500] if reply else "预分析完成",
            "focus_areas": [],
            "related_stocks": [],
            "key_data": [],
        }

    # ── 公开方法 ──────────────────────────────────────────

    async def analyze_topic(self, topic: str) -> AsyncGenerator[dict, None]:
        """预分析辩论题目

        完整 ExpertAgent 流程：recall → think → tools → learn → reply → belief_update
        yield SSE 事件：topic_analysis_start, judge_graph_recall,
                       judge_tool_call, judge_tool_result, topic_analysis_complete
        """
        yield {"event": "topic_analysis_start", "data": {"target": topic, "phase": "topic_analysis"}}

        try:
            query = self._build_topic_query(topic)

            # 1. recall + think
            recalled_nodes, memories, think_output = await self._expert.recall_and_think(query)

            # 发送图谱召回事件
            yield self._rename_event(
                {"event": "graph_recall", "data": {"nodes": [
                    {
                        "id": n["id"],
                        "type": n.get("type"),
                        "label": n.get("name") or n.get("content", "")[:40],
                        "confidence": n.get("confidence"),
                    }
                    for n in recalled_nodes
                ]}},
                phase="topic_analysis",
            )

            # 2. 工具调用
            tool_calls = think_output.tool_calls if think_output.needs_data else []
            for tc in tool_calls:
                if tc.engine == "expert":
                    q = (tc.params.get("question") or "").strip()
                    if not q or len(q) < 4:
                        tc.params["question"] = query
                yield self._rename_event(
                    {"event": "tool_call", "data": {
                        "engine": tc.engine, "action": tc.action,
                        "params": tc.params, "label": f"{tc.engine}.{tc.action}",
                    }},
                    phase="topic_analysis",
                )

            tool_results = await self._expert.execute_tools(tool_calls)

            for r in tool_results:
                result_text = r.get("result", "")
                yield self._rename_event(
                    {"event": "tool_result", "data": {
                        "engine": r["engine"], "action": r["action"],
                        "summary": result_text[:300],
                        "hasError": any(kw in result_text[:200] for kw in ["失败", "error", "超时"]),
                    }},
                    phase="topic_analysis",
                )

            # 3. 图谱学习
            await self._expert.learn_from_context(query, tool_results)

            # 4. 流式回复（收集完整文本）
            full_reply = ""
            async for _token, full_text in self._expert.generate_reply_stream(
                query, recalled_nodes, memories, tool_results
            ):
                full_reply = full_text

            # 5. 信念更新
            if full_reply:
                await self._expert.belief_update(query, full_reply)

            briefing = self._parse_briefing(full_reply)
            yield {"event": "topic_analysis_complete", "data": {
                "briefing": briefing,
                "phase": "topic_analysis",
            }}

        except Exception as e:
            logger.warning(f"JudgeRAG.analyze_topic 失败，跳过预分析: {e}")
            yield {"event": "topic_analysis_complete", "data": {
                "briefing": {"summary": "", "focus_areas": [], "related_stocks": [], "key_data": []},
                "phase": "topic_analysis",
                "error": str(e),
            }}

    async def round_eval(self, round_num: int, blackboard: Blackboard) -> RoundEval:
        """每轮小评 — 轻量级：只走 recall + LLM

        失败时 fallback 使用辩手自报 confidence。
        """
        from engine.arena.personas import JUDGE_ROUND_EVAL_PROMPT
        from llm.providers import ChatMessage

        round_entries = [e for e in blackboard.transcript if e.round == round_num]
        bull_entry = next((e for e in round_entries if e.role == "bull_expert"), None)
        bear_entry = next((e for e in round_entries if e.role == "bear_expert"), None)

        bull_conf = bull_entry.confidence if bull_entry else 0.5
        bull_inner = bull_entry.inner_confidence if bull_entry and bull_entry.inner_confidence is not None else bull_conf
        bear_conf = bear_entry.confidence if bear_entry else 0.5
        bear_inner = bear_entry.inner_confidence if bear_entry and bear_entry.inner_confidence is not None else bear_conf

        fallback = RoundEval(
            round=round_num,
            bull=RoundEvalSide(self_confidence=bull_conf, inner_confidence=bull_inner, judge_confidence=bull_conf),
            bear=RoundEvalSide(self_confidence=bear_conf, inner_confidence=bear_inner, judge_confidence=bear_conf),
        )

        try:
            # 构造 recall query（截断到 500 字）
            bull_arg = bull_entry.argument[:250] if bull_entry else ""
            bear_arg = bear_entry.argument[:250] if bear_entry else ""
            recall_query = f"{bull_arg} {bear_arg}".strip()[:500]

            # 图谱召回
            recalled_nodes = self._expert._graph.recall(recall_query)

            # 构建上下文
            from engine.arena.personas import format_graph_context  # type: ignore
            graph_ctx = ""
            try:
                from engine.expert.personas import format_graph_context as _fgc
                graph_ctx = _fgc(recalled_nodes)
            except Exception:
                pass

            observer_lines = [
                f"{e.role}: {e.argument}"
                for e in round_entries
                if e.role in ("retail_investor", "smart_money") and e.speak and e.argument
            ]
            observer_text = "\n".join(observer_lines) if observer_lines else "（无）"
            done_data = [r for r in blackboard.data_requests if r.status == "done" and r.round == round_num]
            data_text = "\n".join(f"- {r.action}: {str(r.result)[:200]}" for r in done_data) if done_data else "（无）"

            bull_text = f"[{bull_entry.stance}] confidence={bull_conf:.2f}\n{bull_entry.argument}" if bull_entry else "（无发言）"
            bear_text = f"[{bear_entry.stance}] confidence={bear_conf:.2f}\n{bear_entry.argument}" if bear_entry else "（无发言）"

            user_content = (
                f"## 第 {round_num} 轮辩论（标的：{blackboard.target}）\n\n"
                f"### 图谱上下文\n{graph_ctx}\n\n"
                f"### 多头发言\n{bull_text}\n\n"
                f"### 空头发言\n{bear_text}\n\n"
                f"### 观察员信息\n{observer_text}\n\n"
                f"### 本轮补充数据\n{data_text}\n\n"
                "请按格式输出本轮评估 JSON。"
            )

            llm = self._expert._llm
            if not llm:
                return fallback

            chunks: list[str] = []
            async for token in llm.chat_stream([
                ChatMessage(role="system", content=JUDGE_ROUND_EVAL_PROMPT),
                ChatMessage(role="user", content=user_content),
            ]):
                chunks.append(token)
            raw = "".join(chunks)

            # 提取 JSON
            raw_clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw_clean, re.DOTALL)
            json_str = md_match.group(1).strip() if md_match else raw_clean
            parsed = json.loads(json_str)

            def _side(key: str, self_c: float, inner_c: float) -> RoundEvalSide:
                d = parsed.get(key, {})
                return RoundEvalSide(
                    self_confidence=float(d.get("self_confidence", self_c)),
                    inner_confidence=float(d.get("inner_confidence", inner_c)),
                    judge_confidence=float(d.get("judge_confidence", self_c)),
                )

            eval_result = RoundEval(
                round=round_num,
                bull=_side("bull", bull_conf, bull_inner),
                bear=_side("bear", bear_conf, bear_inner),
                bull_reasoning=parsed.get("bull_reasoning", ""),
                bear_reasoning=parsed.get("bear_reasoning", ""),
                data_utilization=parsed.get("data_utilization", {}),
            )
            blackboard.round_evals.append(eval_result)
            logger.info(
                f"JudgeRAG 小评 Round {round_num}: "
                f"bull_judge={eval_result.bull.judge_confidence:.2f}, "
                f"bear_judge={eval_result.bear.judge_confidence:.2f}"
            )
            return eval_result

        except Exception as e:
            logger.warning(f"JudgeRAG.round_eval 第 {round_num} 轮失败，使用 fallback: {e}")
            blackboard.round_evals.append(fallback)
            return fallback

    async def final_verdict_stream(self, blackboard: Blackboard) -> AsyncGenerator[dict, None]:
        """最终裁决 — 完整 ExpertAgent 流程

        recall → think → tools → learn → reply → belief_update
        yield SSE 事件：judge_token, judge_graph_recall, judge_tool_call,
                       judge_tool_result, judge_verdict
        """
        from engine.arena.debate import _parse_judge_output  # type: ignore

        try:
            query = self._build_verdict_query(blackboard)

            # 1. recall + think
            recalled_nodes, memories, think_output = await self._expert.recall_and_think(query)

            yield self._rename_event(
                {"event": "graph_recall", "data": {"nodes": [
                    {
                        "id": n["id"],
                        "type": n.get("type"),
                        "label": n.get("name") or n.get("content", "")[:40],
                        "confidence": n.get("confidence"),
                    }
                    for n in recalled_nodes
                ]}},
                phase="final_verdict",
            )

            # 2. 工具调用
            tool_calls = think_output.tool_calls if think_output.needs_data else []
            for tc in tool_calls:
                if tc.engine == "expert":
                    q = (tc.params.get("question") or "").strip()
                    if not q or len(q) < 4:
                        tc.params["question"] = query
                yield self._rename_event(
                    {"event": "tool_call", "data": {
                        "engine": tc.engine, "action": tc.action,
                        "params": tc.params, "label": f"{tc.engine}.{tc.action}",
                    }},
                    phase="final_verdict",
                )

            tool_results = await self._expert.execute_tools(tool_calls)

            for r in tool_results:
                result_text = r.get("result", "")
                yield self._rename_event(
                    {"event": "tool_result", "data": {
                        "engine": r["engine"], "action": r["action"],
                        "summary": result_text[:300],
                        "hasError": any(kw in result_text[:200] for kw in ["失败", "error", "超时"]),
                    }},
                    phase="final_verdict",
                )

            # 3. 图谱学习
            await self._expert.learn_from_context(query, tool_results)

            # 4. 流式回复（逐 token 推送 judge_token）
            full_reply = ""
            seq = 0
            async for token, full_text in self._expert.generate_reply_stream(
                query, recalled_nodes, memories, tool_results
            ):
                full_reply = full_text
                yield {"event": "judge_token", "data": {
                    "role": "judge", "round": None,
                    "tokens": token, "seq": seq,
                }}
                seq += 1

            # 5. 信念更新
            if full_reply:
                await self._expert.belief_update(query, full_reply)

            # 6. 构建 JudgeVerdict
            verdict = _parse_judge_output(full_reply, blackboard)

            # 数据驱动 score 覆盖
            if blackboard.round_evals:
                last_eval = blackboard.round_evals[-1]
                calculated_score = last_eval.bull.judge_confidence - last_eval.bear.judge_confidence
                if verdict.score is not None:
                    verdict.score = round(calculated_score * 0.7 + verdict.score * 0.3, 3)
                else:
                    verdict.score = round(calculated_score, 3)
                if verdict.score > 0.1:
                    verdict.signal = "bullish"
                elif verdict.score < -0.1:
                    verdict.signal = "bearish"
                else:
                    verdict.signal = "neutral"

            yield {"event": "judge_verdict", "data": verdict.model_dump(mode="json")}

        except Exception as e:
            logger.error(f"JudgeRAG.final_verdict_stream 失败，降级为普通裁决: {e}")
            # 降级：使用现有 judge_summarize_stream
            from engine.arena.debate import judge_summarize_stream
            from engine.arena.memory import AgentMemory
            # 构造一个最小 memory 对象用于降级
            try:
                memory = self._expert._memory or AgentMemory.__new__(AgentMemory)
            except Exception:
                memory = None

            if memory:
                async for event in judge_summarize_stream(
                    blackboard, self._expert._llm, memory
                ):
                    yield event
            else:
                # 最终兜底
                verdict = JudgeVerdict(
                    target=blackboard.target,
                    debate_id=blackboard.debate_id,
                    summary=f"裁判服务异常（{e}），请参考各方辩论记录自行判断。",
                    signal=None, score=None,
                    key_arguments=[],
                    bull_core_thesis="（不可用）",
                    bear_core_thesis="（不可用）",
                    retail_sentiment_note="（不可用）",
                    smart_money_note="（不可用）",
                    risk_warnings=["裁判服务异常，请谨慎参考"],
                    debate_quality="strong_disagreement",
                    termination_reason=blackboard.termination_reason or "max_rounds",
                    timestamp=datetime.now(tz=ZoneInfo("Asia/Shanghai")),
                )
                yield {"event": "judge_verdict", "data": verdict.model_dump(mode="json")}
