"""
debate.py — 专家辩论系统核心逻辑

Blackboard 模式：
- run_debate(): async generator，驱动辩论主循环，推送 SSE 事件
- speak(): 单个角色发言（含超时/异常 fallback）
- judge_summarize(): 裁判总结
- fulfill_data_requests(): 执行专家的数据补充请求
- validate_data_requests(): 白名单过滤
- _fallback_entry(): LLM 失败时的默认发言
- _parse_debate_entry(): 解析 LLM JSON 输出为 DebateEntry
- _parse_judge_output(): 解析裁判 LLM 输出并注入元数据
- persist_debate(): 持久化到 DuckDB
"""

import asyncio
import json
import re
from datetime import datetime
from typing import AsyncGenerator
from zoneinfo import ZoneInfo

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from agent.memory import AgentMemory
from agent.data_fetcher import DataFetcher
from agent.schemas import Blackboard, DebateEntry, DataRequest, JudgeVerdict
from agent.personas import (
    build_debate_system_prompt,
    JUDGE_SYSTEM_PROMPT,
    DEBATE_DATA_WHITELIST,
    MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND,
)

# ── 常量 ──────────────────────────────────────────────

OBSERVERS = ["retail_investor", "smart_money"]


# ── 辅助函数 ──────────────────────────────────────────

def _extract_json(text: str) -> str:
    """从 LLM 输出提取 JSON（处理 markdown 代码块）"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def validate_data_requests(role: str, requests: list[DataRequest]) -> list[DataRequest]:
    """白名单过滤 + 数量截断。不抛出异常。"""
    allowed = DEBATE_DATA_WHITELIST.get(role, [])
    valid = []
    for req in requests:
        if req.action not in allowed:
            logger.warning(f"辩论角色 [{role}] 请求了不在白名单的 action: {req.action}，已过滤")
            continue
        valid.append(req)
        if len(valid) >= MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND:
            if len(requests) > MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND:
                logger.warning(f"辩论角色 [{role}] 请求数超限，截断至 {MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND} 条")
            break
    return valid


def _fallback_entry(role: str, round: int, reason: str) -> DebateEntry:
    """LLM 失败时的默认发言"""
    if role in OBSERVERS:
        return DebateEntry(role=role, round=round, speak=False, argument="")
    # 辩论者默认 insist
    return DebateEntry(
        role=role, round=round,
        stance="insist", speak=True,
        argument=f"（本轮发言暂时不可用：{reason}）",
        confidence=0.5,
    )


def _parse_debate_entry(role: str, round: int, raw: str) -> DebateEntry:
    """解析 LLM 输出为 DebateEntry，解析失败时返回 fallback"""
    try:
        json_str = _extract_json(raw)
        data = json.loads(json_str)
        data["role"] = role
        data["round"] = round
        # 将嵌套的 data_requests 列表转为 DataRequest 对象
        raw_reqs = data.pop("data_requests", [])
        data_requests = []
        for r in raw_reqs:
            if isinstance(r, dict):
                data_requests.append(DataRequest(
                    requested_by=role,
                    engine=r.get("engine", "quant"),
                    action=r.get("action", ""),
                    params=r.get("params", {}),
                    round=round,
                ))
        data["data_requests"] = data_requests
        return DebateEntry(**data)
    except Exception as e:
        logger.warning(f"解析辩论发言失败 [{role}]: {e}，使用 fallback")
        return _fallback_entry(role, round, reason=f"parse_error: {e}")


def _parse_judge_output(raw: str, blackboard: Blackboard) -> JudgeVerdict:
    """解析裁判 LLM 输出，注入 target/debate_id/termination_reason/timestamp"""
    json_str = _extract_json(raw)
    data = json.loads(json_str)
    # 注入元数据（LLM 不生成这 4 个字段）
    data["target"] = blackboard.target
    data["debate_id"] = blackboard.debate_id
    data["termination_reason"] = blackboard.termination_reason or "max_rounds"
    data["timestamp"] = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    return JudgeVerdict(**data)


def _build_context_for_role(blackboard: Blackboard) -> str:
    """将 Blackboard 核心内容序列化为 LLM 可读的上下文"""
    parts = []

    # Worker 初步判断
    if blackboard.worker_verdicts:
        parts.append("## Worker 分析师初步判断")
        for v in blackboard.worker_verdicts:
            parts.append(f"- {v.agent_role}: {v.signal} (score={v.score:.2f}, confidence={v.confidence:.2f})")

    # 分歧
    if blackboard.conflicts:
        parts.append("\n## 已检测到的分歧")
        for c in blackboard.conflicts:
            parts.append(f"- {c}")

    # 辩论记录
    if blackboard.transcript:
        parts.append("\n## 辩论记录")
        for entry in blackboard.transcript:
            if not entry.speak and entry.role in OBSERVERS:
                continue  # 沉默的观察员不出现在上下文
            stance_str = f" [{entry.stance}]" if entry.stance else ""
            parts.append(f"\n**Round {entry.round} - {entry.role}{stance_str}** (confidence={entry.confidence:.2f})")
            if entry.argument:
                parts.append(entry.argument)
            if entry.challenges:
                parts.append("质疑: " + "；".join(entry.challenges))

    # 已到位的补充数据
    done_reqs = [r for r in blackboard.data_requests if r.status == "done"]
    if done_reqs:
        parts.append("\n## 补充数据")
        for r in done_reqs:
            parts.append(f"- {r.action} ({r.requested_by} 请求): {str(r.result)[:200]}")

    return "\n".join(parts)


# ── 核心函数 ──────────────────────────────────────────

async def speak(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    is_final_round: bool,
) -> DebateEntry:
    """单个角色发言，含超时和异常 fallback"""
    memory_ctx = memory.recall(role, f"辩论 {blackboard.target}", top_k=3)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 你的历史辩论记忆\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )

    system_prompt = build_debate_system_prompt(role, blackboard.target, is_final_round)
    context = _build_context_for_role(blackboard)
    user_content = f"## 当前辩论状态（Round {blackboard.round}）\n\n{context}{memory_text}\n\n请发表你的观点。"

    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_content),
    ]

    try:
        raw = await asyncio.wait_for(llm.chat(messages), timeout=45.0)
        entry = _parse_debate_entry(role, blackboard.round, raw)
    except asyncio.TimeoutError:
        logger.warning(f"辩论角色 [{role}] LLM 超时，使用 fallback")
        entry = _fallback_entry(role, blackboard.round, reason="timeout")
    except Exception as e:
        logger.warning(f"辩论角色 [{role}] LLM 失败: {e}，使用 fallback")
        entry = _fallback_entry(role, blackboard.round, reason=str(e))

    if not is_final_round:
        validated = validate_data_requests(role, entry.data_requests)
        blackboard.data_requests.extend(validated)

    return entry


async def fulfill_data_requests(
    pending: list[DataRequest],
    data_fetcher: DataFetcher,
) -> None:
    """执行数据请求，结果就地写入 req.result/status。不抛出异常。"""
    for req in pending:
        try:
            # TODO: 合并 Claude A 后 DataFetcher 已有 fetch_by_request()
            result = await data_fetcher.fetch_by_request(req)
            req.result = result
            req.status = "done"
        except Exception as e:
            logger.warning(f"数据请求失败 [{req.action}]: {e}")
            req.result = f"获取失败: {e}"
            req.status = "failed"


async def judge_summarize(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
) -> JudgeVerdict:
    """裁判总结——读完整 Blackboard，输出 JudgeVerdict"""
    memory_ctx = memory.recall("judge", f"辩论 {blackboard.target}", top_k=3)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 你过去类似辩论的裁决记录\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )

    context = _build_context_for_role(blackboard)
    user_content = (
        f"## 完整辩论记录（标的：{blackboard.target}）\n\n{context}{memory_text}\n\n"
        f"辩论终止原因：{blackboard.termination_reason}，共进行 {blackboard.round} 轮。\n\n"
        "请做出你的最终裁决。"
    )

    messages = [
        ChatMessage("system", JUDGE_SYSTEM_PROMPT),
        ChatMessage("user", user_content),
    ]

    try:
        raw = await asyncio.wait_for(llm.chat(messages), timeout=60.0)
        verdict = _parse_judge_output(raw, blackboard)
    except Exception as e:
        logger.error(f"裁判总结失败: {e}，生成降级 verdict")
        verdict = JudgeVerdict(
            target=blackboard.target,
            debate_id=blackboard.debate_id,
            summary=f"裁判总结暂时不可用（{e}），请参考各方辩论记录自行判断。",
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

    # 存储裁判记忆
    try:
        memory.store(
            agent_role="judge",
            target=blackboard.target,
            content=f"裁决: {verdict.debate_quality}, signal={verdict.signal}",
            metadata={"debate_id": blackboard.debate_id, "signal": str(verdict.signal)},
        )
    except Exception as e:
        logger.warning(f"裁判记忆存储失败: {e}")

    return verdict


async def persist_debate(
    blackboard: Blackboard,
    judge_verdict: JudgeVerdict,
) -> None:
    """持久化到 DuckDB shared.debate_records。失败只记录 warning，不抛出。"""
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn

        con.execute("CREATE SCHEMA IF NOT EXISTS shared")
        con.execute("""
            CREATE TABLE IF NOT EXISTS shared.debate_records (
                id                  VARCHAR PRIMARY KEY,
                target              VARCHAR,
                max_rounds          INTEGER,
                rounds_completed    INTEGER,
                termination_reason  VARCHAR,
                blackboard_json     TEXT,
                judge_verdict_json  TEXT,
                created_at          TIMESTAMP,
                completed_at        TIMESTAMP
            )
        """)

        now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
        con.execute("""
            INSERT INTO shared.debate_records
                (id, target, max_rounds, rounds_completed, termination_reason,
                 blackboard_json, judge_verdict_json, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                rounds_completed   = excluded.rounds_completed,
                termination_reason = excluded.termination_reason,
                blackboard_json    = excluded.blackboard_json,
                judge_verdict_json = excluded.judge_verdict_json,
                completed_at       = excluded.completed_at
        """, [
            blackboard.debate_id,
            blackboard.target,
            blackboard.max_rounds,
            blackboard.round,
            blackboard.termination_reason,
            blackboard.model_dump_json(),
            judge_verdict.model_dump_json(),
            now,
            now,
        ])
        logger.info(f"辩论记录已持久化: {blackboard.debate_id}")
    except Exception as e:
        logger.warning(f"辩论记录持久化失败: {e}")


# ── 主循环 ────────────────────────────────────────────

async def run_debate(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """专家辩论主循环 — async generator，推送 SSE 事件"""

    def sse(event: str, data: dict) -> dict:
        return {"event": event, "data": data}

    yield sse("debate_start", {
        "debate_id": blackboard.debate_id,
        "target": blackboard.target,
        "max_rounds": blackboard.max_rounds,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"],
    })

    while blackboard.round < blackboard.max_rounds:
        blackboard.round += 1
        is_final = (blackboard.round == blackboard.max_rounds)

        if is_final:
            blackboard.status = "final_round"

        yield sse("debate_round_start", {
            "round": blackboard.round,
            "is_final": is_final,
        })

        # 1. 多头发言
        bull_entry = await speak("bull_expert", blackboard, llm, memory, is_final)
        blackboard.transcript.append(bull_entry)
        if bull_entry.stance == "concede":
            blackboard.bull_conceded = True
        yield sse("debate_entry", bull_entry.model_dump(mode="json"))

        # 2. 空头发言
        bear_entry = await speak("bear_expert", blackboard, llm, memory, is_final)
        blackboard.transcript.append(bear_entry)
        if bear_entry.stance == "concede":
            blackboard.bear_conceded = True
        yield sse("debate_entry", bear_entry.model_dump(mode="json"))

        # 3. 观察员
        for observer in OBSERVERS:
            entry = await speak(observer, blackboard, llm, memory, is_final)
            blackboard.transcript.append(entry)
            if entry.speak:
                yield sse("debate_entry", entry.model_dump(mode="json"))

        # 4. 执行数据请求
        pending = [r for r in blackboard.data_requests if r.status == "pending"]
        if pending and not is_final:
            for req in pending:
                yield sse("data_fetching", {
                    "requested_by": req.requested_by,
                    "engine": req.engine,
                    "action": req.action,
                })
            await fulfill_data_requests(pending, data_fetcher)
            yield sse("data_ready", {
                "count": len(pending),
                "result_summary": f"已获取 {len(pending)} 条补充数据",
            })

        # 5. 轮次控制
        if blackboard.bull_conceded and blackboard.bear_conceded:
            blackboard.termination_reason = "both_conceded"
            break
        elif blackboard.bull_conceded:
            blackboard.termination_reason = "bull_conceded"
            break
        elif blackboard.bear_conceded:
            blackboard.termination_reason = "bear_conceded"
            break
        elif is_final:
            blackboard.termination_reason = "max_rounds"
            break

    # 6. 裁判总结
    blackboard.status = "judging"
    yield sse("debate_end", {
        "reason": blackboard.termination_reason,
        "rounds_completed": blackboard.round,
    })

    judge_verdict = await judge_summarize(blackboard, llm, memory)
    blackboard.status = "completed"
    yield sse("judge_verdict", judge_verdict.model_dump(mode="json"))

    # 7. 持久化
    await persist_debate(blackboard, judge_verdict)
