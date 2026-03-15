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


def sse(event: str, data: dict) -> dict:
    """统一 SSE 事件格式"""
    return {"event": event, "data": data}


# ── 辅助函数 ──────────────────────────────────────────


def _extract_json(text: str) -> str:
    """从 LLM 输出提取 JSON（处理 markdown 代码块）"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


async def extract_structure(
    argument: str,
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> dict:
    """从 argument 正文提取结构化字段，返回可解包到 DebateEntry 的 dict。"""
    extract_prompt = f"""请从以下辩论发言中提取结构化信息，只返回 JSON，不要其他内容。

角色: {role}
发言内容:
{argument}

返回格式:
{{
  "stance": "insist" | "partial_concede" | "concede",
  "confidence": 0.0-1.0,
  "challenges": ["对对方的质疑1", "质疑2"],
  "data_requests": [{{"engine": "quant|data|info", "action": "动作名", "params": {{}}}}],
  "retail_sentiment_score": null,
  "speak": true
}}"""

    try:
        raw = await asyncio.wait_for(
            llm.chat([ChatMessage(role="user", content=extract_prompt)]),
            timeout=10.0,
        )
        parsed = json.loads(_extract_json(raw))
        return {
            "stance": parsed.get("stance", "insist"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "challenges": parsed.get("challenges", []),
            "data_requests": [
                DataRequest(
                    requested_by=role, round=blackboard.round,
                    status="pending", engine=dr.get("engine", ""),
                    action=dr.get("action", ""), params=dr.get("params", {}),
                )
                for dr in parsed.get("data_requests", [])
            ],
            "retail_sentiment_score": parsed.get("retail_sentiment_score"),
            "speak": parsed.get("speak", True),
        }
    except Exception:
        return {
            "stance": "insist", "confidence": 0.5,
            "challenges": [], "data_requests": [],
            "retail_sentiment_score": None, "speak": True,
        }


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
    """解析自然语言 LLM 输出为 DebateEntry

    辩论者格式：
      开头一行声明立场（含"坚持"/"部分让步"/"认输"关键词）
      正文为 argument
      【质疑】标记后每行一条 challenge
      【数据请求】标记后每行一条请求（格式：引擎.动作(参数) 或 引擎.动作）

    观察员格式：
      仅含"【沉默】"时 speak=False
      否则 speak=True，全文为 argument
    """
    text = raw.strip()

    # ── 观察员 ──────────────────────────────────────────
    if role in OBSERVERS:
        if "【沉默】" in text:
            return DebateEntry(role=role, round=round, speak=False, argument="")
        # 去掉沉默标记后剩余内容作为 argument
        argument = text.replace("【沉默】", "").strip()
        return DebateEntry(role=role, round=round, speak=True, argument=argument, confidence=0.5)

    # ── 辩论者 ──────────────────────────────────────────
    try:
        # 1. 识别立场
        stance = "insist"
        first_line = text.split("\n")[0]
        if any(k in first_line for k in ("认输", "concede", "放弃", "承认失败")):
            stance = "concede"
        elif any(k in first_line for k in ("部分让步", "partial", "承认", "部分同意")):
            stance = "partial_concede"

        # 2. 分割【质疑】和【数据请求】块
        challenges: list[str] = []
        data_requests: list[DataRequest] = []

        # 提取【数据请求】块
        data_req_match = re.search(r"【数据请求】(.*?)(?=【|$)", text, re.DOTALL)
        if data_req_match:
            for line in data_req_match.group(1).strip().splitlines():
                line = line.strip().lstrip("-•·").strip()
                if not line:
                    continue
                # 格式：引擎.动作(参数json) 或 引擎.动作
                m = re.match(r"(\w+)\.(\w+)(?:\((.+)\))?", line)
                if m:
                    engine, action = m.group(1), m.group(2)
                    params: dict = {}
                    if m.group(3):
                        try:
                            params = json.loads(m.group(3))
                        except Exception:
                            params = {"raw": m.group(3)}
                    data_requests.append(DataRequest(
                        requested_by=role, engine=engine,
                        action=action, params=params, round=round,
                    ))
            text = text[:data_req_match.start()].strip()

        # 提取【质疑】块
        challenge_match = re.search(r"【质疑】(.*?)(?=【|$)", text, re.DOTALL)
        if challenge_match:
            for line in challenge_match.group(1).strip().splitlines():
                line = line.strip().lstrip("-•·").strip()
                if line:
                    challenges.append(line)
            text = text[:challenge_match.start()].strip()

        # 剩余内容为 argument（去掉立场声明行可选，保留更完整）
        argument = text.strip()

        return DebateEntry(
            role=role, round=round,
            stance=stance, speak=True,
            argument=argument,
            challenges=challenges,
            confidence=0.5,
            data_requests=data_requests,
        )
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
