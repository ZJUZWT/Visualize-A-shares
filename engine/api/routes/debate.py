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
