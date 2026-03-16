"""辩论 API — 独立的专家辩论端点，SSE 流式推送辩论过程"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from agent.schemas import Blackboard

router = APIRouter(prefix="/api/v1", tags=["debate"])


class DebateRequest(BaseModel):
    code: str = Field(description="股票代码，如 '001896'")
    max_rounds: int = Field(default=3, ge=1, le=5)
    mode: str = Field(default="standard", description="辩论模式: standard | fast")
    as_of_date: str = Field(default="", description="回测日期，如 '2025-06-30'，空字符串表示使用最新数据")


@router.post("/debate")
async def start_debate(req: DebateRequest):
    """发起专家辩论，SSE 流式返回辩论过程

    SSE 事件类型:
    - debate_start: 辩论开始
    - debate_round_start: 新一轮开始
    - debate_entry: 角色发言
    - data_fetching / data_ready: 数据请求
    - debate_end: 辩论结束
    - judge_verdict: 裁判最终裁决
    """
    from llm.config import llm_settings
    if not llm_settings.api_key:
        raise HTTPException(status_code=503, detail="LLM 未配置，请先设置 API Key")

    now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    blackboard = Blackboard(
        target=req.code,
        debate_id=f"{req.code}_{now.strftime('%Y%m%d%H%M%S')}",
        max_rounds=req.max_rounds,
        mode=req.mode if req.mode in ("standard", "fast") else "standard",
        as_of_date=req.as_of_date,  # 回测模式：用户指定历史日期
    )

    async def event_stream():
        try:
            from agent import get_orchestrator
            from agent.debate import run_debate

            orch = get_orchestrator()
            async for event in run_debate(
                blackboard=blackboard,
                llm=orch._llm._provider,
                memory=orch._memory,
                data_fetcher=orch._data,
            ):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.error(f"辩论流程错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


from fastapi import Query


@router.get("/debate/history")
async def get_debate_history(limit: int = Query(default=20, ge=1, le=100)):
    """返回最近 N 条辩论记录摘要"""
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn

        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='shared' AND table_name='debate_records'"
        ).fetchall()
        if not tables:
            return []

        rows = con.execute("""
            SELECT
                id AS debate_id,
                target,
                rounds_completed,
                termination_reason,
                created_at,
                json_extract_string(judge_verdict_json, '$.signal') AS signal,
                json_extract_string(judge_verdict_json, '$.debate_quality') AS debate_quality
            FROM shared.debate_records
            ORDER BY created_at DESC
            LIMIT ?
        """, [limit]).fetchall()

        cols = ["debate_id", "target", "rounds_completed", "termination_reason",
                "created_at", "signal", "debate_quality"]
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        logger.error(f"查询辩论历史失败: {e}")
        return []


@router.get("/debate/{debate_id}")
async def get_debate_record(debate_id: str):
    """返回单条辩论完整记录（用于回放）"""
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn

        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='shared' AND table_name='debate_records'"
        ).fetchall()
        if not tables:
            raise HTTPException(status_code=404, detail=f"辩论记录不存在: {debate_id}")

        row = con.execute(
            "SELECT id, target, blackboard_json, judge_verdict_json, "
            "rounds_completed, termination_reason, created_at "
            "FROM shared.debate_records WHERE id = ?",
            [debate_id]
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"辩论记录不存在: {debate_id}")

        cols = ["debate_id", "target", "blackboard_json", "judge_verdict_json",
                "rounds_completed", "termination_reason", "created_at"]
        return dict(zip(cols, row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询辩论记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TranscriptEntry(BaseModel):
    role: str
    round: int = 0
    argument: str = ""


class SummarizeRequest(BaseModel):
    target: str = Field(description="股票代码")
    transcript: list[TranscriptEntry] = Field(min_length=1, description="已有辩论记录")


@router.post("/debate/summarize")
async def summarize_debate(req: SummarizeRequest):
    """对中途终止的辩论生成简短总结"""
    from llm.config import llm_settings
    if not llm_settings.api_key:
        raise HTTPException(status_code=503, detail="LLM 未配置")

    try:
        from agent import get_orchestrator
        orch = get_orchestrator()
        llm = orch._llm._provider

        # 构建 transcript 文本
        lines = []
        for entry in req.transcript:
            role_label = "多头" if entry.role == "bull_expert" else ("空头" if entry.role == "bear_expert" else entry.role)
            lines.append(f"[{role_label} 第{entry.round}轮] {entry.argument}")
        transcript_text = "\n\n".join(lines)

        prompt = f"""以下是关于股票 {req.target} 的多空辩论记录（辩论被用户中途终止）：

{transcript_text}

请基于已有内容，给出：
1. 一段简短总结（100字以内），概括双方核心分歧
2. 当前倾向：bullish（看多）/ bearish（看空）/ neutral（中性）

以 JSON 格式返回：{{"summary": "...", "signal": "bullish|bearish|neutral"}}"""

        response = await llm.chat([{"role": "user", "content": prompt}])
        # 提取 JSON
        text = response.strip()
        if "```" in text:
            # Handle ```json or ```JSON or ``` with optional whitespace
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
                # Strip language identifier (json, JSON, etc.)
                first_newline = text.find("\n")
                if first_newline > 0:
                    lang = text[:first_newline].strip().lower()
                    if lang in ("json", ""):
                        text = text[first_newline:]
        try:
            result = json.loads(text.strip())
        except json.JSONDecodeError as parse_err:
            logger.error(f"LLM 返回内容无法解析为 JSON: {parse_err}\n原始内容: {response!r}")
            raise HTTPException(status_code=500, detail="LLM 返回格式错误，无法解析总结")
        return {
            "summary": result.get("summary", ""),
            "signal": result.get("signal") if result.get("signal") in ("bullish", "bearish", "neutral") else None,
        }
    except Exception as e:
        logger.error(f"生成总结失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成总结失败: {str(e)}")
