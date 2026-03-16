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
from agent.schemas import Blackboard, DebateEntry, DataRequest, JudgeVerdict, RoundEval, RoundEvalSide, IndustryCognition
from agent.personas import (
    build_debate_system_prompt,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_ROUND_EVAL_PROMPT,
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
    """从 LLM 输出提取 JSON（处理 <think> 标签 + markdown 代码块 + 中文引号 + 控制字符）"""
    # 0. 剥离 <think>...</think> 思考过程（DeepSeek/QwQ 等模型常见）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # 1. 尝试从 markdown 代码块提取
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    result = match.group(1).strip() if match else text.strip()
    # 2. 替换中文引号为英文引号
    result = result.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    # 3. 移除 JSON 字符串值以外的控制字符（保留 \n \r \t）
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
    extract_prompt = f"""请从以下辩论发言中提取结构化信息。

角色: {role}
发言内容:
<speech>
{argument}
</speech>

直接输出 JSON，不要包含 markdown 代码块、不要包含任何额外文字或思考过程。
{{
  "stance": "insist" | "partial_concede" | "concede",
  "confidence": 0.0-1.0,
  "inner_confidence": 0.0-1.0,
  "challenges": ["对对方的质疑1", "质疑2"],
  "retail_sentiment_score": null,
  "speak": true
}}

重要约束：
- confidence 是公开立场（可以嘴硬）
- inner_confidence 是内心真实想法——如果对方的某个论据确实让其动摇了，这里要诚实反映
- retail_sentiment_score 仅 retail_investor 角色填写（-1.0 到 +1.0），其他角色必须为 null
- 直接输出 JSON，不要任何其他文字"""

    try:
        # 流式收集：保持链路活跃，不设总超时
        chunks: list[str] = []
        async for token in llm.chat_stream([ChatMessage(role="user", content=extract_prompt)]):
            chunks.append(token)
        raw = "".join(chunks)
        parsed = _lenient_json_loads(raw)
        score = parsed.get("retail_sentiment_score")
        return {
            "stance": parsed.get("stance", "insist"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "inner_confidence": float(parsed.get("inner_confidence", parsed.get("confidence", 0.5))),
            "challenges": parsed.get("challenges", []),
            "data_requests": [],
            "retail_sentiment_score": _parse_sentiment_score(score),
            "speak": parsed.get("speak", True),
        }
    except Exception as e:
        logger.warning(f"extract_structure 解析失败，使用默认值: {e}")
        return {
            "stance": "insist", "confidence": 0.5,
            "inner_confidence": None,
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


def _format_fact(data: dict) -> str:
    """将 fact dict 格式化为 LLM 可读文本，不截断"""
    lines = []
    for k, v in data.items():
        if k in ("code", "error"):
            continue
        lines.append(f"  {k}: {v}")
    return "\n".join(lines) if lines else str(data)


def _build_context_for_role(blackboard: Blackboard) -> str:
    """将 Blackboard 核心内容序列化为 LLM 可读的上下文"""
    parts = []

    # 时间锚点
    if blackboard.as_of_date:
        parts.append(f"## 辩论时间基准\n当前讨论基于 {blackboard.as_of_date} 收盘后的市场环境。所有数据截止到该日期。\n")

    # 快速模式：用压缩摘要替代 facts + industry_cognition
    if blackboard.mode == "fast" and blackboard.facts_summary:
        parts.append("## 市场数据摘要（压缩版）")
        parts.append(blackboard.facts_summary)
        parts.append("")
    else:
        # 行业底层逻辑
        if blackboard.industry_cognition:
            ic = blackboard.industry_cognition
            parts.append(f"## 行业底层逻辑（{ic.industry}）")
            parts.append(f"\n### 产业链")
            parts.append(f"上游: {', '.join(ic.upstream)}")
            parts.append(f"下游: {', '.join(ic.downstream)}")
            parts.append(f"核心驱动变量: {', '.join(ic.core_drivers)}")
            parts.append(f"\n### 成本结构\n{ic.cost_structure}")
            parts.append(f"\n### 行业壁垒\n{ic.barriers}")
            parts.append(f"\n### 供需格局\n{ic.supply_demand}")
            if ic.common_traps:
                parts.append(f"\n### ⚠ 常见认知陷阱（务必注意）")
                for i, trap in enumerate(ic.common_traps, 1):
                    parts.append(f"{i}. {trap}")
            parts.append(f"\n### 周期定位\n{ic.cycle_position}：{ic.cycle_reasoning}")
            if ic.catalysts:
                parts.append(f"\n### 潜在催化剂")
                for c in ic.catalysts:
                    parts.append(f"- {c}")
            if ic.risks:
                parts.append(f"\n### 关键风险")
                for r in ic.risks:
                    parts.append(f"- {r}")
            parts.append("")

        # 资金构成（公共知识）
        capital = blackboard.facts.get("capital_structure")
        if capital and isinstance(capital, dict):
            parts.append("## 资金构成")
            if capital.get("main_force_net_inflow"):
                parts.append(f"- 主力净流入: {capital['main_force_net_inflow']}（占比{capital.get('main_force_ratio', '')}）")
            if capital.get("super_large_net_inflow"):
                parts.append(f"- 超大单净流入: {capital['super_large_net_inflow']}")
            if capital.get("large_net_inflow"):
                parts.append(f"- 大单净流入: {capital['large_net_inflow']}")
            if capital.get("small_net_inflow"):
                parts.append(f"- 小单净流入: {capital['small_net_inflow']}")
            if capital.get("northbound_ratio"):
                parts.append(f"- 北向持股占比: {capital['northbound_ratio']}，变化: {capital.get('northbound_change', '')}")
            if capital.get("margin_balance"):
                parts.append(f"- 融资余额: {capital['margin_balance']}，融资买入额: {capital.get('margin_buy', '')}")
            if capital.get("turnover_rate"):
                parts.append(f"- 换手率: {capital['turnover_rate']:.2f}%")
            if capital.get("structure_summary"):
                parts.append(f"\n综合判断: {capital['structure_summary']}")
            parts.append("")

        # 公用初始数据（facts）
        if blackboard.facts:
            parts.append("## 初始数据")
            for action, data in blackboard.facts.items():
                label = ACTION_TITLE_MAP.get(action, action)
                parts.append(f"\n### {label}")
                if isinstance(data, dict):
                    # 日线数据特殊处理：展示全部 recent 记录
                    if action == "get_daily_history" and "recent" in data:
                        parts.append(f"共 {data.get('days', '?')} 个交易日，最近 {len(data['recent'])} 条：")
                        for row in data["recent"]:
                            date_str = str(row.get("date", ""))[:10]
                            parts.append(
                                f"  {date_str} 开:{row.get('open','')} 高:{row.get('high','')} "
                                f"低:{row.get('low','')} 收:{row.get('close','')} "
                                f"涨跌:{row.get('pct_chg','')}% 换手:{row.get('turnover_rate','')}%"
                            )
                    # 新闻数据特殊处理：逐条展示标题和情感
                    elif action == "get_news" and isinstance(data, list):
                        for item in data:
                            if hasattr(item, "model_dump"):
                                item = item.model_dump()
                            title = item.get("title", "")
                            sentiment = item.get("sentiment", "")
                            source = item.get("source", "")
                            time_str = item.get("publish_time", "")
                            parts.append(f"  [{sentiment}] {title} ({source} {time_str})")
                    else:
                        parts.append(_format_fact(data))
                elif isinstance(data, list):
                    # 新闻/公告列表
                    for item in data:
                        if isinstance(item, dict):
                            title = item.get("title", "")
                            sentiment = item.get("sentiment", "")
                            parts.append(f"  [{sentiment}] {title}")
                        else:
                            parts.append(f"  {item}")
                else:
                    parts.append(str(data))

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
            label = ACTION_TITLE_MAP.get(r.action, r.action)
            parts.append(f"\n### {label} ({r.requested_by} 请求)")
            if isinstance(r.result, dict):
                parts.append(_format_fact(r.result))
            elif isinstance(r.result, list):
                for item in r.result:
                    if isinstance(item, dict):
                        parts.append(f"  {item}")
                    else:
                        parts.append(f"  {item}")
            else:
                parts.append(str(r.result))

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

    # Phase 1: 流式输出（支持 <think> 标签分离）
    tokens: list[str] = []       # 正文 token（不含 think）
    think_tokens: list[str] = [] # think 内容
    token_buf: list[str] = []
    seq = 0
    in_think = False             # 是否在 <think> 块内
    raw_buffer = ""              # 用于检测 <think> 和 </think> 标签的缓冲区

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
            raw_buffer += token

            # 检测 <think> 标签开始
            if not in_think and "<think>" in raw_buffer:
                # 将 <think> 之前的内容作为正文处理
                before = raw_buffer.split("<think>", 1)[0]
                if before:
                    tokens.append(before)
                    token_buf.append(before)
                in_think = True
                raw_buffer = raw_buffer.split("<think>", 1)[1]
                continue

            # 检测 </think> 标签结束
            if in_think and "</think>" in raw_buffer:
                think_content = raw_buffer.split("</think>", 1)[0]
                think_tokens.append(think_content)
                in_think = False
                remaining = raw_buffer.split("</think>", 1)[1]
                raw_buffer = remaining.lstrip("\n")  # 剥离 think 后的换行
                # 推送 think 完成事件
                yield sse("debate_think", {
                    "role": role, "round": blackboard.round,
                    "content": "".join(think_tokens),
                })
                continue

            # 在 think 块内：累积但不推送正文
            if in_think:
                # 保留缓冲区用于检测 </think>，但避免无限增长
                if len(raw_buffer) > 200:
                    think_tokens.append(raw_buffer[:-20])
                    raw_buffer = raw_buffer[-20:]
                continue

            # 正常正文：检查缓冲区是否可能是 <think> 的开始
            if "<" in raw_buffer and not raw_buffer.endswith(">"):
                # 可能是不完整的标签，继续缓冲
                if len(raw_buffer) < 10:
                    continue

            # 推送正文
            if raw_buffer:
                tokens.append(raw_buffer)
                token_buf.append(raw_buffer)
                raw_buffer = ""
            if len(token_buf) >= 5 or token in ("。", "\n", ".", "！", "？", "；"):
                ev = _flush()
                if ev:
                    yield ev

        # 处理残余缓冲区
        if raw_buffer and not in_think:
            tokens.append(raw_buffer)
            token_buf.append(raw_buffer)
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
    # 剥离残留的 think 标签（以防流式解析遗漏）
    argument = re.sub(r"<think>.*?</think>", "", argument, flags=re.DOTALL).strip()

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
        # 流式收集：保持链路活跃，不设总超时
        chunks: list[str] = []
        async for token in llm.chat_stream(messages):
            chunks.append(token)
        raw = "".join(chunks)
        entry = _parse_debate_entry(role, blackboard.round, raw)
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
        params: dict = {"code": blackboard.code or blackboard.target}
        if action in ("get_news", "get_announcements"):
            params["limit"] = 10  # 限制条数，避免情感分析超时
        req = DataRequest(
            requested_by="public", engine=engine,
            action=action, params=params, round=0,
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


# ── 行业认知（已迁移至 IndustryEngine） ─────────────────


async def generate_industry_cognition(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> AsyncGenerator[dict, None]:
    """调用 IndustryEngine 获取行业产业链认知"""
    stock_info = blackboard.facts.get("get_stock_info", {})
    industry = stock_info.get("industry", "")
    stock_name = stock_info.get("name", blackboard.target)

    if not industry:
        logger.info("未获取到行业信息，跳过行业认知生成")
        return

    yield sse("industry_cognition_start", {"industry": industry, "cached": False})

    try:
        from industry_engine import get_industry_engine
        ie = get_industry_engine()
        cognition = await ie.analyze(
            target=blackboard.code or blackboard.target,
            as_of_date=blackboard.as_of_date,
        )

        if cognition:
            blackboard.industry_cognition = cognition
            yield sse("industry_cognition_done", {
                "industry": industry,
                "summary": f"产业链: {' → '.join(cognition.upstream[:2])} → [{stock_name}] → {' → '.join(cognition.downstream[:2])}",
                "cycle_position": cognition.cycle_position,
                "traps_count": len(cognition.common_traps),
                "cached": False,
            })
        else:
            yield sse("industry_cognition_done", {
                "industry": industry,
                "summary": "行业认知生成失败",
                "cycle_position": "",
                "traps_count": 0,
                "cached": False,
                "error": True,
            })
    except Exception as e:
        logger.warning(f"行业认知生成失败: {type(e).__name__}: {e!r}")
        yield sse("industry_cognition_done", {
            "industry": industry,
            "summary": f"行业认知生成失败: {type(e).__name__}: {e}",
            "cycle_position": "",
            "traps_count": 0,
            "cached": False,
            "error": True,
        })


# ── 数据压缩（快速模式）──────────────────────────────────

FACTS_COMPRESSION_PROMPT = """你是金融数据分析师。请将以下原始市场数据压缩为结构化摘要，保留对多空辩论最关键的信息。

## 原始数据
{raw_facts}

## 压缩要求
输出一段结构化文本（非 JSON），包含：
1. 【标的概况】一句话（名称、行业、市值量级）
2. 【近期走势】区间涨跌幅、关键价位（支撑/压力）、成交量变化趋势（3-5句）
3. 【关键事件】最重要的 2-3 条新闻/公告及其情感倾向
4. 【行业背景】核心驱动变量、当前周期定位、最关键的认知陷阱（2-3句）

总字数控制在 500-800 字。只保留对投资决策有直接影响的信息。"""


def _serialize_facts_for_compression(blackboard: Blackboard) -> str:
    """将 facts + industry_cognition 序列化为压缩用的原始文本"""
    parts = []

    info = blackboard.facts.get("get_stock_info", {})
    if info:
        parts.append(f"## 股票信息\n{_format_fact(info)}")

    daily = blackboard.facts.get("get_daily_history", {})
    if daily and isinstance(daily, dict) and "recent" in daily:
        parts.append(f"## 日线行情（{daily.get('days', '?')}个交易日）")
        for row in daily["recent"]:
            date_str = str(row.get("date", ""))[:10]
            parts.append(
                f"  {date_str} 开:{row.get('open','')} 高:{row.get('high','')} "
                f"低:{row.get('low','')} 收:{row.get('close','')} "
                f"涨跌:{row.get('pct_chg','')}% 换手:{row.get('turnover_rate','')}%"
            )

    news = blackboard.facts.get("get_news")
    if news:
        parts.append("## 新闻")
        items = news if isinstance(news, list) else [news]
        for item in items:
            if isinstance(item, dict):
                parts.append(f"  [{item.get('sentiment','')}] {item.get('title','')} — {str(item.get('content',''))[:200]}")
            elif hasattr(item, "model_dump"):
                d = item.model_dump()
                parts.append(f"  [{d.get('sentiment','')}] {d.get('title','')} — {str(d.get('content',''))[:200]}")

    ic = blackboard.industry_cognition
    if ic:
        parts.append(f"## 行业认知（{ic.industry}）")
        parts.append(f"产业链: 上游={ic.upstream}, 下游={ic.downstream}")
        parts.append(f"核心驱动: {ic.core_drivers}")
        parts.append(f"成本结构: {ic.cost_structure}")
        parts.append(f"壁垒: {ic.barriers}")
        parts.append(f"供需: {ic.supply_demand}")
        parts.append(f"认知陷阱: {ic.common_traps}")
        parts.append(f"周期: {ic.cycle_position} — {ic.cycle_reasoning}")
        parts.append(f"催化剂: {ic.catalysts}")
        parts.append(f"风险: {ic.risks}")

    return "\n".join(parts)


async def compress_facts(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> AsyncGenerator[dict, None]:
    """快速模式：LLM 预压缩 facts + 行业认知为摘要"""
    yield sse("facts_compression_start", {"mode": "fast"})

    raw_facts = _serialize_facts_for_compression(blackboard)
    if not raw_facts.strip():
        logger.warning("无数据可压缩，跳过")
        blackboard.mode = "standard"
        yield sse("facts_compression_done", {"error": True, "fallback": "standard"})
        return

    prompt = FACTS_COMPRESSION_PROMPT.format(raw_facts=raw_facts)
    original_est = len(raw_facts) // 2

    try:
        chunks: list[str] = []
        async for token in llm.chat_stream([ChatMessage(role="user", content=prompt)]):
            chunks.append(token)
        summary = "".join(chunks).strip()

        if not summary or len(summary) < 50:
            raise ValueError(f"压缩结果过短: {len(summary)} 字符")

        blackboard.facts_summary = summary
        compressed_est = len(summary) // 2
        ratio = round(compressed_est / max(original_est, 1), 2)

        yield sse("facts_compression_done", {
            "original_tokens_est": original_est,
            "compressed_tokens_est": compressed_est,
            "compression_ratio": ratio,
        })
        logger.info(f"数据压缩完成: {original_est} → {compressed_est} tokens (ratio={ratio})")

    except Exception as e:
        logger.warning(f"数据压缩失败，降级为标准模式: {type(e).__name__}: {e}")
        blackboard.mode = "standard"
        blackboard.facts_summary = None
        yield sse("facts_compression_done", {"error": True, "fallback": "standard"})


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
        # 流式收集：只要后端还在产出 token，链路保持活跃
        chunks: list[str] = []
        async for token in llm.chat_stream([ChatMessage(role="user", content=prompt)]):
            chunks.append(token)
        raw = "".join(chunks)
        parsed = _lenient_json_loads(raw)
        if not isinstance(parsed, list):
            parsed = []
    except Exception as e:
        logger.warning(f"[{role}] 数据请求 LLM 调用失败: {type(e).__name__}: {e}，跳过")
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
        # 流式收集：保持链路活跃，不设总超时
        chunks: list[str] = []
        async for token in llm.chat_stream(messages):
            chunks.append(token)
        raw = "".join(chunks)
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

    # 评委历史评估
    eval_history = ""
    if blackboard.round_evals:
        eval_lines = []
        for ev in blackboard.round_evals:
            eval_lines.append(
                f"Round {ev.round}: 多头(公开={ev.bull.self_confidence:.2f}, "
                f"内心={ev.bull.inner_confidence:.2f}, 评委={ev.bull.judge_confidence:.2f}) "
                f"空头(公开={ev.bear.self_confidence:.2f}, "
                f"内心={ev.bear.inner_confidence:.2f}, 评委={ev.bear.judge_confidence:.2f})"
            )
        eval_history = "\n\n## 各轮评委评估\n" + "\n".join(eval_lines)

    judge_stream_prompt = (
        f"你是一位专业的股票辩论裁判。请对以下辩论做出裁决。\n"
        f"**重要：直接输出 JSON，不要输出自然语言、不要使用 markdown 代码块。**\n\n"
        f"{context}{memory_text}{eval_history}"
    )
    messages = [
        ChatMessage(role="system", content=JUDGE_SYSTEM_PROMPT),
        ChatMessage(role="user", content=judge_stream_prompt),
    ]

    # Phase 1: 流式输出 summary（支持 think 标签分离）
    tokens: list[str] = []       # 正文
    think_tokens: list[str] = [] # think 内容
    token_buf: list[str] = []
    seq = 0
    in_think = False
    raw_buffer = ""

    try:
        async for token in llm.chat_stream(messages):
            raw_buffer += token

            # 检测 <think> 标签开始
            if not in_think and "<think>" in raw_buffer:
                before = raw_buffer.split("<think>", 1)[0]
                if before:
                    tokens.append(before)
                    token_buf.append(before)
                in_think = True
                raw_buffer = raw_buffer.split("<think>", 1)[1]
                continue

            # 检测 </think> 标签结束
            if in_think and "</think>" in raw_buffer:
                think_content = raw_buffer.split("</think>", 1)[0]
                think_tokens.append(think_content)
                in_think = False
                remaining = raw_buffer.split("</think>", 1)[1]
                raw_buffer = remaining.lstrip("\n")
                # 推送 think 事件
                yield sse("judge_think", {
                    "role": "judge", "round": None,
                    "content": "".join(think_tokens),
                })
                continue

            if in_think:
                if len(raw_buffer) > 200:
                    think_tokens.append(raw_buffer[:-20])
                    raw_buffer = raw_buffer[-20:]
                continue

            # 正常正文
            if "<" in raw_buffer and not raw_buffer.endswith(">") and len(raw_buffer) < 10:
                continue

            if raw_buffer:
                tokens.append(raw_buffer)
                token_buf.append(raw_buffer)
                raw_buffer = ""
            if len(token_buf) >= 5 or token in ("。", "\n", ".", "！", "？", "；"):
                yield sse("judge_token", {
                    "role": "judge", "round": None,
                    "tokens": "".join(token_buf), "seq": seq,
                })
                seq += 1
                token_buf = []

        # 残余缓冲区
        if raw_buffer and not in_think:
            tokens.append(raw_buffer)
            token_buf.append(raw_buffer)
        if token_buf:
            yield sse("judge_token", {
                "role": "judge", "round": None,
                "tokens": "".join(token_buf), "seq": seq,
            })
    except Exception as e:
        logger.warning(f"裁判流式中断: {e}")
        tokens.append("(裁决中断)")

    summary_text = "".join(tokens)
    # 剥离残留 think 标签
    summary_text = re.sub(r"<think>.*?</think>", "", summary_text, flags=re.DOTALL).strip()

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
            verdict = await _extract_judge_verdict(summary_text, blackboard, llm)
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

    # Phase 3: 数据驱动 score 覆盖
    if blackboard.round_evals:
        last_eval = blackboard.round_evals[-1]
        calculated_score = last_eval.bull.judge_confidence - last_eval.bear.judge_confidence
        if verdict.score is not None:
            verdict.score = round(calculated_score * 0.7 + verdict.score * 0.3, 3)
        else:
            verdict.score = round(calculated_score, 3)
        # 根据 score 修正 signal
        if verdict.score > 0.1:
            verdict.signal = "bullish"
        elif verdict.score < -0.1:
            verdict.signal = "bearish"
        else:
            verdict.signal = "neutral"

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
    extract_prompt = f"""请从以下裁判总结中提取结构化裁决。直接输出 JSON，不要包含 markdown 代码块、不要包含任何额外文字或思考过程。

{summary}

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

    # 流式收集：保持链路活跃，不设总超时
    chunks: list[str] = []
    async for token in llm.chat_stream([ChatMessage(role="user", content=extract_prompt)]):
        chunks.append(token)
    raw = "".join(chunks)
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


async def judge_round_eval(
    round_num: int,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> RoundEval:
    """评委每轮小评——读取本轮双方发言，输出 RoundEval 并追加到 blackboard.round_evals。"""
    # 取本轮 bull/bear 发言
    round_entries = [e for e in blackboard.transcript if e.round == round_num]
    bull_entry = next((e for e in round_entries if e.role == "bull_expert"), None)
    bear_entry = next((e for e in round_entries if e.role == "bear_expert"), None)

    bull_conf = bull_entry.confidence if bull_entry else 0.5
    bull_inner = bull_entry.inner_confidence if bull_entry and bull_entry.inner_confidence is not None else bull_conf
    bear_conf = bear_entry.confidence if bear_entry else 0.5
    bear_inner = bear_entry.inner_confidence if bear_entry and bear_entry.inner_confidence is not None else bear_conf

    # 构建本轮上下文摘要
    bull_text = f"[{bull_entry.stance}] confidence={bull_conf:.2f}, inner={bull_inner:.2f}\n{bull_entry.argument}" if bull_entry else "（无发言）"
    bear_text = f"[{bear_entry.stance}] confidence={bear_conf:.2f}, inner={bear_inner:.2f}\n{bear_entry.argument}" if bear_entry else "（无发言）"

    # 观察员信息
    observer_lines = []
    for e in round_entries:
        if e.role in OBSERVERS and e.speak and e.argument:
            observer_lines.append(f"{e.role}: {e.argument}")
    observer_text = "\n".join(observer_lines) if observer_lines else "（无）"

    # 已到位的本轮数据
    done_data = [r for r in blackboard.data_requests if r.status == "done" and r.round == round_num]
    data_text = "\n".join(f"- {r.action} ({r.requested_by}): {str(r.result)}" for r in done_data) if done_data else "（无）"

    user_content = (
        f"## 第 {round_num} 轮辩论（标的：{blackboard.target}）\n\n"
        f"### 多头发言\n{bull_text}\n\n"
        f"### 空头发言\n{bear_text}\n\n"
        f"### 观察员信息\n{observer_text}\n\n"
        f"### 本轮补充数据\n{data_text}\n\n"
        "请按格式输出本轮评估 JSON。"
    )

    messages = [
        ChatMessage(role="system", content=JUDGE_ROUND_EVAL_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]

    fallback = RoundEval(
        round=round_num,
        bull=RoundEvalSide(self_confidence=bull_conf, inner_confidence=bull_inner, judge_confidence=bull_conf),
        bear=RoundEvalSide(self_confidence=bear_conf, inner_confidence=bear_inner, judge_confidence=bear_conf),
    )

    try:
        # 流式收集：保持链路活跃，不设总超时
        chunks: list[str] = []
        async for token in llm.chat_stream(messages):
            chunks.append(token)
        raw = "".join(chunks)
        parsed = json.loads(_extract_json(raw))

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
    except Exception as e:
        logger.warning(f"judge_round_eval 第 {round_num} 轮解析失败，使用默认值: {e}")
        eval_result = fallback

    blackboard.round_evals.append(eval_result)
    logger.info(f"评委小评 Round {round_num}: bull_judge={eval_result.bull.judge_confidence:.2f}, bear_judge={eval_result.bear.judge_confidence:.2f}")
    return eval_result


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


def _resolve_as_of_date(code: str) -> str:
    """确定辩论时间锚点 — 最新可用交易日

    优先从日线数据取最新交易日，fallback 到快照日期，最后用 today。
    """
    import datetime as _dt
    today = _dt.date.today().strftime("%Y-%m-%d")
    if not code:
        return today
    try:
        from data_engine import get_data_engine
        de = get_data_engine()
        # 尝试从日线历史取最新交易日
        start = (_dt.date.today() - _dt.timedelta(days=10)).strftime("%Y-%m-%d")
        df = de.get_daily_history(code, start, today)
        if hasattr(df, "empty") and not df.empty:
            # 日线数据中 trade_date 或 date 列的最大值
            for col in ("trade_date", "date"):
                if col in df.columns:
                    latest = str(df[col].max())[:10]
                    if latest:
                        return latest
        # fallback: 快照日期
        dates = de.store.get_snapshot_daily_dates()
        if dates:
            return dates[0]  # 已按 DESC 排序
    except Exception as e:
        logger.warning(f"_resolve_as_of_date 失败: {e}")
    return today


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

    # 确定辩论时间锚点（最新可用交易日）
    if not blackboard.as_of_date:
        blackboard.as_of_date = _resolve_as_of_date(blackboard.code)
        logger.info(f"辩论时间锚点: {blackboard.as_of_date}")

    # 同步时间锚点到 DataFetcher
    data_fetcher._as_of_date = blackboard.as_of_date

    yield sse("debate_start", {
        "debate_id": blackboard.debate_id,
        "target": blackboard.target,
        "as_of_date": blackboard.as_of_date,
        "max_rounds": blackboard.max_rounds,
        "mode": blackboard.mode,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"],
    })

    # 公用初始数据
    async for event in fetch_initial_data(blackboard, data_fetcher):
        yield event

    # 行业产业链认知
    async for event in generate_industry_cognition(blackboard, llm):
        yield event

    # 资金构成分析（写入黑板 facts 作为公共知识）
    if blackboard.code:
        yield sse("phase", {"name": "capital_structure", "status": "start"})
        try:
            from industry_engine import get_industry_engine
            ie = get_industry_engine()
            capital = await ie.get_capital_structure(
                blackboard.code, blackboard.as_of_date
            )
            blackboard.facts["capital_structure"] = capital.model_dump()
            yield sse("phase", {"name": "capital_structure", "status": "done",
                                "summary": capital.structure_summary})
        except Exception as e:
            logger.warning(f"资金构成分析失败: {e}")
            yield sse("phase", {"name": "capital_structure", "status": "error",
                                "error": str(e)})

    # 快速模式：LLM 预压缩
    if blackboard.mode == "fast":
        async for event in compress_facts(blackboard, llm):
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

        # 5. 数据请求逐个事件化
        pending = [r for r in blackboard.data_requests if r.status == "pending"]
        if pending and not is_final:
            success = 0
            failed = 0
            for req in pending:
                t0 = time.monotonic()
                req_id = f"{req.requested_by}_{req.action}_{req.round}"
                yield sse("data_request_start", {
                    "requested_by": req.requested_by,
                    "engine": req.engine,
                    "action": req.action,
                    "params": req.params,
                    "request_id": req_id,
                })
                try:
                    result = await data_fetcher.fetch_by_request(req)
                    req.result = result
                    req.status = "done"
                    success += 1
                    yield sse("data_request_done", {
                        "request_id": req_id, "engine": req.engine,
                        "action": req.action, "status": "done",
                        "result_summary": str(result)[:200] if result else "",
                        "duration_ms": int((time.monotonic() - t0) * 1000),
                    })
                except Exception as e:
                    req.status = "failed"
                    failed += 1
                    yield sse("data_request_done", {
                        "request_id": req_id, "engine": req.engine,
                        "action": req.action, "status": "failed",
                        "result_summary": (str(e) or type(e).__name__)[:200],
                        "duration_ms": int((time.monotonic() - t0) * 1000),
                    })
            yield sse("data_batch_complete", {
                "round": blackboard.round,
                "total": len(pending),
                "success": success,
                "failed": failed,
            })

        # 6. 评委每轮小评
        try:
            round_eval = await judge_round_eval(blackboard.round, blackboard, llm)
            yield sse("judge_round_eval", {
                "round": round_eval.round,
                "bull": round_eval.bull.model_dump(),
                "bear": round_eval.bear.model_dump(),
                "bull_reasoning": round_eval.bull_reasoning,
                "bear_reasoning": round_eval.bear_reasoning,
                "data_utilization": round_eval.data_utilization,
            })
        except Exception as e:
            logger.warning(f"评委小评失败，跳过: {e}")

        # 7. 轮次控制
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
