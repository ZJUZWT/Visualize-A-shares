"""Agent chat routes."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from engine.agent.chat import AgentChatRuntime, AgentChatService
from engine.agent.db import AgentDB


class ChatSessionCreateRequest(BaseModel):
    portfolio_id: str
    title: str = "新对话"


class AgentChatRequest(BaseModel):
    portfolio_id: str
    session_id: str | None = None
    title: str = "新对话"
    message: str = Field(min_length=1)


def create_agent_chat_router(chat_runtime: AgentChatRuntime | None = None) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["agent-chat"])

    def _get_service() -> AgentChatService:
        db = AgentDB.get_instance()
        return AgentChatService(db=db, chat_runtime=chat_runtime)

    @router.get("/sessions")
    async def list_chat_sessions(portfolio_id: str = Query(...)):
        svc = _get_service()
        try:
            return await svc.list_sessions(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/sessions")
    async def create_chat_session(req: ChatSessionCreateRequest):
        svc = _get_service()
        try:
            return await svc.create_session(req.portfolio_id, req.title)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/sessions/{session_id}")
    async def delete_chat_session(session_id: str, portfolio_id: str = Query(...)):
        svc = _get_service()
        try:
            await svc.delete_session(portfolio_id, session_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/sessions/{session_id}/messages")
    async def list_chat_messages(session_id: str, portfolio_id: str = Query(...)):
        svc = _get_service()
        try:
            return await svc.list_messages(portfolio_id, session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("")
    async def chat(req: AgentChatRequest):
        svc = _get_service()
        try:
            await svc.validate_chat_target(req.portfolio_id, req.session_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        async def event_stream():
            try:
                async for event in svc.stream_chat_events(
                    portfolio_id=req.portfolio_id,
                    message=req.message,
                    session_id=req.session_id,
                    title=req.title,
                ):
                    yield (
                        f"event: {event['event']}\n"
                        f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                    )
            except Exception as e:
                yield (
                    "event: error\n"
                    f"data: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
                )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
