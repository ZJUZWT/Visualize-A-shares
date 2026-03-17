"""分析 API — SSE 流式推送 Agent 分析进度和结果"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from engine.arena.schemas import AnalysisRequest

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analysis")
async def analyze(req: AnalysisRequest):
    """触发 Multi-Agent 分析流水线，SSE 流式返回进度和结果

    SSE 事件类型:
    - phase: {"step": "prescreen"|"parallel_analysis"|"aggregation", "status": "running"|"done"}
    - agent_done: {"agent": "fundamental"|"info"|"quant", "signal": "...", "confidence": 0.x}
    - result: {"report": {...AggregatedReport...}}
    - error: {"message": "..."}
    """
    from llm.config import llm_settings
    if not llm_settings.api_key:
        raise HTTPException(status_code=503, detail="LLM 未配置，请先设置 API Key")

    async def event_stream():
        try:
            from engine.arena import get_orchestrator
            orch = get_orchestrator()
            async for event in orch.analyze(req):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"分析流水线错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
