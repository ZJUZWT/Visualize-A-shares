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
import time
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
    """从 LLM 输出提取 JSON（处理 markdown 代码块 + 中文引号 + 控制字符）"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    result = match.group(1).strip() if match else text.strip()
    # 替换中文引号为英文引号
    result = result.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    # 移除 JSON 字符串值以外的控制字符（保留 \n \r \t）
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)
    return result


def _lenient_json_loads(text: str) -> dict | list:
    """宽松 JSON 解析：先尝试标准解析，失败后修复常见 LLM 格式问题"""
    raw = _extract_json(text)
    # 1. 标准解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 2. 移除尾逗号（}, ] 前的逗号）
    fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # 3. 单引号替换为双引号
    fixed2 = fixed.replace("'", '"')
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass
    # 4. 尝试提取第一个 { ... } 或 [ ... ] 块
    m = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[.*\])', fixed, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("宽松解析也失败", raw, 0)


def _parse_sentiment_score(value) -> float | None:
    """将 LLM 返回的情感分数转为 float，支持数字和字符串格式"""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return None


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
<speech>
{argument}
</speech>

返回格式:
{{
  "stance": "insist" | "partial_concede" | "concede",
  "confidence": 0.0-1.0,
  "challenges": ["对对方的质疑1", "质疑2"],
  "retail_sentiment_score": null,
  "speak": true
}}

重要约束：
- retail_sentiment_score 仅 retail_investor 角色填写（-1.0 到 +1.0），其他角色必须为 null
- 只返回 JSON，不要任何其他文字"""

    try:
        raw = await asyncio.wait_for(
            llm.chat([ChatMessage(role="user", content=extract_prompt)]),
            timeout=10.0,
        )
        parsed = _lenient_json_loads(raw)
        score = parsed.get("retail_sentiment_score")
        return {
            "stance": parsed.get("stance", "insist"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "challenges": parsed.get("challenges", []),
            "data_requests": [],
            "retail_sentiment_score": _parse_sentiment_score(score),
            "speak": parsed.get("speak", True),
        }
    except Exception as e:
        logger.warning(f"extract_structure 解析失败，使用默认值: {e}")
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

        # 2. 提取【质疑】块
        challenges: list[str] = []
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

async def speak_stream(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    is_final_round: bool,
) -> AsyncGenerator[dict, None]:
    """流式辩论发言：逐 token 推送 debate_token，最后推送 debate_entry_complete"""
    memory_ctx = memory.recall(role, f"辩论 {blackboard.target}", top_k=3)
    system_prompt = build_debate_system_prompt(role, blackboard.target, is_final_round)
    context = _build_context_for_role(blackboard)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 你的历史辩论记忆\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )
    user_content = (
        f"## 当前辩论状态（Round {blackboard.round}）\n\n"
        f"{context}{memory_text}\n\n请发表你的观点。"
    )
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_content),
    ]

    # Phase 1: 流式输出
    tokens: list[str] = []
    token_buf: list[str] = []
    seq = 0

    def _flush() -> dict | None:
        nonlocal seq
        if token_buf:
            ev = sse("debate_token", {
                "role": role, "round": blackboard.round,
                "tokens": "".join(token_buf), "seq": seq,
            })
            seq += 1
            token_buf.clear()
            return ev
        return None

    try:
        async for token in llm.chat_stream(messages):
            tokens.append(token)
            token_buf.append(token)
            if len(token_buf) >= 5 or token in ("。", "\n", ".", "！", "？", "；"):
                ev = _flush()
                if ev:
                    yield ev
        ev = _flush()
        if ev:
            yield ev
    except Exception as e:
        logger.warning(f"流式中断 ({role}): {e}")
        tokens.append("(发言中断)")
        ev = _flush()
        if ev:
            yield ev

    argument = "".join(tokens)

    # Phase 2: 提取结构化字段
    structure = await extract_structure(argument, role, blackboard, llm)

    entry = DebateEntry(
        role=role, round=blackboard.round,
        argument=argument, **structure,
    )

    # Phase 3: blackboard 更新
    blackboard.transcript.append(entry)

    yield sse("debate_entry_complete", entry.model_dump(mode="json"))


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


async def fetch_initial_data(
    blackboard: Blackboard,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """拉取公用初始数据，推送 blackboard_update 事件"""
    INITIAL_ACTIONS = [
        ("get_stock_info",    "data", "股票基本信息"),
        ("get_daily_history", "data", "日线行情"),
        ("get_news",          "info", "最新新闻"),
    ]
    success = 0
    failed = 0
    for action, engine, title in INITIAL_ACTIONS:
        req_id = f"public_{action}"
        yield sse("blackboard_update", {
            "request_id": req_id, "source": "public",
            "engine": engine, "action": action, "title": title,
            "status": "pending", "result_summary": "", "round": 0,
        })
        req = DataRequest(
            requested_by="public", engine=engine,
            action=action, params={"code": blackboard.code or blackboard.target}, round=0,
        )
        try:
            result = await asyncio.wait_for(
                data_fetcher.fetch_by_request(req), timeout=30.0
            )
            # 判断是否有实质内容
            has_content = bool(result) and result != {"error": None}
            is_error = isinstance(result, dict) and "error" in result
            if is_error:
                summary = result["error"]
                status = "failed"
                failed += 1
            else:
                summary = str(result)[:300] if has_content else "（无数据）"
                status = "done"
                blackboard.facts[action] = result
                success += 1
            yield sse("blackboard_update", {
                "request_id": req_id, "source": "public",
                "engine": engine, "action": action, "title": title,
                "status": status, "result_summary": summary, "round": 0,
            })
        except Exception as e:
            logger.warning(f"公用数据拉取失败 [{action}]: {type(e).__name__}: {e}")
            failed += 1
            err_msg = str(e) or type(e).__name__
            yield sse("blackboard_update", {
                "request_id": req_id, "source": "public",
                "engine": engine, "action": action, "title": title,
                "status": "failed", "result_summary": err_msg[:200], "round": 0,
            })
    yield sse("initial_data_complete", {
        "total": len(INITIAL_ACTIONS), "success": success, "failed": failed,
    })


ACTION_TITLE_MAP = {
    "get_stock_info": "股票基本信息", "get_daily_history": "日线行情",
    "get_news": "最新新闻", "get_announcements": "公告",
    "get_factor_scores": "因子评分", "get_technical_indicators": "技术指标",
    "get_money_flow": "资金流向", "get_northbound_holding": "北向持仓",
    "get_margin_balance": "融资融券", "get_turnover_rate": "换手率",
    "get_cluster_for_stock": "聚类分析", "get_financials": "财务数据",
    "get_restrict_stock_unlock": "限售解禁", "get_signal_history": "信号历史",
}


async def request_data_for_round(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """专家本轮数据请求：LLM 决策 → fetch → 推送 blackboard_update"""
    from agent.personas import build_data_request_prompt
    context = _build_context_for_role(blackboard)
    prompt = build_data_request_prompt(role, blackboard.target, blackboard.round, context)

    try:
        raw = await asyncio.wait_for(
            llm.chat([ChatMessage(role="user", content=prompt)]),
            timeout=15.0,
        )
        parsed = _lenient_json_loads(raw)
        if not isinstance(parsed, list):
            parsed = []
    except Exception as e:
        logger.warning(f"[{role}] 数据请求 LLM 调用失败: {e}，跳过")
        return

    requests = [
        DataRequest(
            requested_by=role, engine=dr.get("engine", "data"),
            action=dr.get("action", ""), params=dr.get("params", {}),
            round=blackboard.round,
        )
        for dr in parsed if dr.get("action")
    ]
    requests = validate_data_requests(role, requests)

    for req in requests:
        req_id = f"{role}_{req.action}_{blackboard.round}"
        title = ACTION_TITLE_MAP.get(req.action, req.action)
        yield sse("blackboard_update", {
            "request_id": req_id, "source": role,
            "engine": req.engine, "action": req.action, "title": title,
            "status": "pending", "result_summary": "", "round": blackboard.round,
        })
        try:
            result = await asyncio.wait_for(
                data_fetcher.fetch_by_request(req), timeout=30.0
            )
            is_error = isinstance(result, dict) and "error" in result
            if is_error:
                req.status = "failed"
                yield sse("blackboard_update", {
                    "request_id": req_id, "source": role,
                    "engine": req.engine, "action": req.action, "title": title,
                    "status": "failed", "result_summary": result["error"],
                    "round": blackboard.round,
                })
            else:
                req.result = result
                req.status = "done"
                blackboard.data_requests.append(req)
                yield sse("blackboard_update", {
                    "request_id": req_id, "source": role,
                    "engine": req.engine, "action": req.action, "title": title,
                    "status": "done", "result_summary": str(result)[:300] if result else "（无数据）",
                    "round": blackboard.round,
                })
        except Exception as e:
            logger.warning(f"[{role}] 数据请求失败 [{req.action}]: {type(e).__name__}: {e}")
            req.status = "failed"
            yield sse("blackboard_update", {
                "request_id": req_id, "source": role,
                "engine": req.engine, "action": req.action, "title": title,
                "status": "failed", "result_summary": (str(e) or type(e).__name__)[:200],
                "round": blackboard.round,
            })

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


async def judge_summarize_stream(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
) -> AsyncGenerator[dict, None]:
    """流式裁判总结：逐 token 推送 judge_token，最后推送 judge_verdict"""
    memory_ctx = memory.recall("judge", f"辩论 {blackboard.target}", top_k=3)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 历史裁决参考\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )

    context = _build_context_for_role(blackboard)
    judge_stream_prompt = (
        f"你是一位专业的股票辩论裁判。请对以下辩论做出总结评价，"
        f"直接用自然语言阐述你的裁决。\n\n{context}{memory_text}"
    )
    messages = [
        ChatMessage(role="system", content=JUDGE_SYSTEM_PROMPT),
        ChatMessage(role="user", content=judge_stream_prompt),
    ]

    # Phase 1: 流式输出 summary
    tokens: list[str] = []
    token_buf: list[str] = []
    seq = 0
    try:
        async for token in llm.chat_stream(messages):
            tokens.append(token)
            token_buf.append(token)
            if len(token_buf) >= 5 or token in ("。", "\n", ".", "！", "？", "；"):
                yield sse("judge_token", {
                    "role": "judge", "round": None,
                    "tokens": "".join(token_buf), "seq": seq,
                })
                seq += 1
                token_buf = []
        if token_buf:
            yield sse("judge_token", {
                "role": "judge", "round": None,
                "tokens": "".join(token_buf), "seq": seq,
            })
    except Exception as e:
        logger.warning(f"裁判流式中断: {e}")
        tokens.append("(裁决中断)")

    summary_text = "".join(tokens)

    # Phase 2: 提取结构化裁决
    # 裁判 system prompt 要求直接输出 JSON，先尝试直接解析 summary_text
    # 失败时才回退到二次 LLM 提取
    try:
        json_str = _extract_json(summary_text)
        if json_str:
            verdict = await asyncio.wait_for(
                _parse_judge_json(json_str, blackboard),
                timeout=5.0,
            )
        else:
            verdict = await asyncio.wait_for(
                _extract_judge_verdict(summary_text, blackboard, llm),
                timeout=30.0,
            )
    except Exception as e:
        logger.error(f"裁判结构化提取失败: {e}，生成降级 verdict")
        verdict = JudgeVerdict(
            target=blackboard.target,
            debate_id=blackboard.debate_id,
            summary=summary_text or f"裁判总结暂时不可用（{e}）",
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

    yield sse("judge_verdict", verdict.model_dump(mode="json"))


async def _parse_judge_json(json_str: str, blackboard: Blackboard) -> JudgeVerdict:
    """直接从 JSON 字符串构建 JudgeVerdict"""
    data = json.loads(json_str)
    data["target"] = blackboard.target
    data["debate_id"] = blackboard.debate_id
    data["termination_reason"] = blackboard.termination_reason or "max_rounds"
    data["timestamp"] = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    return JudgeVerdict(**data)


async def _extract_judge_verdict(
    summary: str, blackboard: Blackboard, llm: BaseLLMProvider
) -> JudgeVerdict:
    """从 summary 文本提取结构化 JudgeVerdict"""
    extract_prompt = f"""请从以下裁判总结中提取结构化裁决，只返回 JSON，不要其他内容。

{summary}

返回格式:
{{
  "summary": "总结文本",
  "signal": "bullish" | "bearish" | "neutral",
  "score": -1.0到1.0,
  "key_arguments": ["关键论据1", ...],
  "bull_core_thesis": "多头核心论点",
  "bear_core_thesis": "空头核心论点",
  "retail_sentiment_note": "散户情绪说明",
  "smart_money_note": "主力资金说明",
  "risk_warnings": ["风险1", ...],
  "debate_quality": "strong_disagreement" | "consensus" | "one_sided"
}}"""

    raw = await llm.chat([ChatMessage(role="user", content=extract_prompt)])
    json_str = _extract_json(raw)
    data = json.loads(json_str)
    data["target"] = blackboard.target
    data["debate_id"] = blackboard.debate_id
    data["termination_reason"] = blackboard.termination_reason or "max_rounds"
    data["timestamp"] = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    try:
        return JudgeVerdict(**data)
    except Exception as e:
        logger.warning(f"JudgeVerdict 构建失败: {e}，data keys: {list(data.keys())}")
        raise


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

def resolve_stock_code(target: str) -> str:
    """从 target 解析股票代码。
    - 如果 target 本身是 6 位数字代码，直接返回
    - 否则在公司概况里按名称模糊匹配，返回最佳匹配的代码
    - 找不到返回空字符串
    """
    import re
    if re.fullmatch(r"\d{6}", target.strip()):
        return target.strip()
    try:
        from data_engine import get_data_engine
        profiles = get_data_engine().get_profiles()
        target_lower = target.lower()
        for code, info in profiles.items():
            name = info.get("name", "")
            if name and (name in target or target_lower in name.lower()):
                return code
    except Exception as e:
        logger.warning(f"resolve_stock_code 失败: {e}")
    return ""


async def run_debate(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """专家辩论主循环 — async generator，推送 SSE 事件"""

    # 解析股票代码（target 可能是自由文本）
    if not blackboard.code:
        blackboard.code = resolve_stock_code(blackboard.target)
        if blackboard.code:
            logger.info(f"target '{blackboard.target}' 解析为股票代码: {blackboard.code}")
        else:
            logger.info(f"target '{blackboard.target}' 未匹配到股票代码，数据拉取将降级")

    yield sse("debate_start", {
        "debate_id": blackboard.debate_id,
        "target": blackboard.target,
        "max_rounds": blackboard.max_rounds,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"],
    })

    # 公用初始数据
    async for event in fetch_initial_data(blackboard, data_fetcher):
        yield event

    while blackboard.round < blackboard.max_rounds:
        blackboard.round += 1
        is_final = (blackboard.round == blackboard.max_rounds)

        if is_final:
            blackboard.status = "final_round"

        yield sse("debate_round_start", {
            "round": blackboard.round,
            "is_final": is_final,
        })

        # 1. 专家数据请求（发言前，最终轮跳过）
        if not is_final:
            async for event in request_data_for_round("bull_expert", blackboard, llm, data_fetcher):
                yield event
            async for event in request_data_for_round("bear_expert", blackboard, llm, data_fetcher):
                yield event

        # 2. 多头发言（流式）
        last_bull: dict | None = None
        async for event in speak_stream("bull_expert", blackboard, llm, memory, is_final):
            yield event
            if event["event"] == "debate_entry_complete":
                last_bull = event["data"]

        # 3. 空头发言（流式）
        last_bear: dict | None = None
        async for event in speak_stream("bear_expert", blackboard, llm, memory, is_final):
            yield event
            if event["event"] == "debate_entry_complete":
                last_bear = event["data"]

        # 4. 观察员（直接流式输出，不再缓冲）
        for observer in OBSERVERS:
            async for event in speak_stream(observer, blackboard, llm, memory, is_final):
                yield event

        # 5. concede 检查
        if last_bull and last_bull.get("stance") == "concede":
            blackboard.bull_conceded = True
        if last_bear and last_bear.get("stance") == "concede":
            blackboard.bear_conceded = True

        # 6. 轮次控制
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

    # 7. 裁判总结
    blackboard.status = "judging"
    yield sse("debate_end", {
        "reason": blackboard.termination_reason,
        "rounds_completed": blackboard.round,
    })

    judge_verdict = None
    async for event in judge_summarize_stream(blackboard, llm, memory):
        yield event
        if event["event"] == "judge_verdict":
            from agent.schemas import JudgeVerdict as _JV
            judge_verdict = _JV(**{
                k: v for k, v in event["data"].items()
            })
    blackboard.status = "completed"

    # 8. 持久化
    if judge_verdict:
        await persist_debate(blackboard, judge_verdict)
