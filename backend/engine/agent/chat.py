"""Agent chat persistence and streaming helpers."""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime
from typing import Any, AsyncIterator, Protocol

from engine.agent.db import AgentDB


AGENT_CHAT_EVENT_NAMES = {"reply_token", "reply_complete", "error"}


def _normalize_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_safe(item) for item in value]
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value.__class__.__name__ == "NaTType":
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except ValueError:
            return None
    return value


def _decode_json_field(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


class AgentChatRuntime(Protocol):
    async def stream_reply(
        self,
        *,
        portfolio_id: str,
        session_id: str,
        message: str,
        history: list[dict],
    ) -> AsyncIterator[dict]:
        ...


class DefaultAgentChatRuntime:
    async def stream_reply(
        self,
        *,
        portfolio_id: str,
        session_id: str,
        message: str,
        history: list[dict],
    ) -> AsyncIterator[dict]:
        reply = f"已收到你的问题：{message}"
        yield {"event": "reply_token", "data": {"content": reply}}
        yield {"event": "reply_complete", "data": {"full_text": reply}}


class AgentChatService:
    def __init__(
        self,
        db: AgentDB,
        chat_runtime: AgentChatRuntime | None = None,
    ):
        self.db = db
        self.chat_runtime = chat_runtime or DefaultAgentChatRuntime()

    async def _ensure_schema(self) -> None:
        await self.db.execute_write(
            """
            CREATE TABLE IF NOT EXISTS agent.chat_sessions (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                title VARCHAR NOT NULL DEFAULT '新对话',
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
            """
        )
        await self.db.execute_write(
            """
            CREATE TABLE IF NOT EXISTS agent.chat_messages (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                portfolio_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                thinking JSON,
                created_at TIMESTAMP DEFAULT now()
            )
            """
        )

    async def ensure_portfolio_exists(self, portfolio_id: str) -> None:
        rows = await self.db.execute_read(
            "SELECT id FROM agent.portfolio_config WHERE id = ?",
            [portfolio_id],
        )
        if not rows:
            raise ValueError(f"账户 {portfolio_id} 不存在")

    async def create_session(self, portfolio_id: str, title: str = "新对话") -> dict:
        await self._ensure_schema()
        await self.ensure_portfolio_exists(portfolio_id)
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.db.execute_write(
            """
            INSERT INTO agent.chat_sessions (id, portfolio_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [session_id, portfolio_id, title, now, now],
        )
        return {
            "id": session_id,
            "portfolio_id": portfolio_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }

    async def get_session(self, portfolio_id: str, session_id: str) -> dict:
        await self._ensure_schema()
        await self.ensure_portfolio_exists(portfolio_id)
        rows = await self.db.execute_read(
            """
            SELECT id, portfolio_id, title, created_at, updated_at
            FROM agent.chat_sessions
            WHERE id = ? AND portfolio_id = ?
            """,
            [session_id, portfolio_id],
        )
        if not rows:
            raise ValueError(f"会话 {session_id} 不存在")
        return rows[0]

    async def list_sessions(self, portfolio_id: str) -> list[dict]:
        await self._ensure_schema()
        await self.ensure_portfolio_exists(portfolio_id)
        rows = await self.db.execute_read(
            """
            SELECT s.id, s.portfolio_id, s.title, s.created_at, s.updated_at,
                   (
                       SELECT COUNT(*)
                       FROM agent.chat_messages m
                       WHERE m.session_id = s.id
                   ) AS message_count
            FROM agent.chat_sessions s
            WHERE s.portfolio_id = ?
            ORDER BY s.updated_at DESC, s.created_at DESC, s.id DESC
            """,
            [portfolio_id],
        )
        return [
            {
                "id": row["id"],
                "portfolio_id": row["portfolio_id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"],
            }
            for row in rows
        ]

    async def delete_session(self, portfolio_id: str, session_id: str) -> None:
        await self._ensure_schema()
        await self.get_session(portfolio_id, session_id)
        await self.db.execute_transaction(
            [
                (
                    "DELETE FROM agent.chat_messages WHERE session_id = ? AND portfolio_id = ?",
                    [session_id, portfolio_id],
                ),
                (
                    "DELETE FROM agent.chat_sessions WHERE id = ? AND portfolio_id = ?",
                    [session_id, portfolio_id],
                ),
            ]
        )

    async def list_messages(self, portfolio_id: str, session_id: str) -> list[dict]:
        await self._ensure_schema()
        await self.get_session(portfolio_id, session_id)
        rows = await self.db.execute_read(
            """
            SELECT id, session_id, portfolio_id, role, content, thinking, created_at
            FROM agent.chat_messages
            WHERE session_id = ? AND portfolio_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            [session_id, portfolio_id],
        )
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "portfolio_id": row["portfolio_id"],
                "role": row["role"],
                "content": row["content"],
                "thinking": _normalize_json_safe(_decode_json_field(row.get("thinking"))),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def validate_chat_target(self, portfolio_id: str, session_id: str | None) -> None:
        await self._ensure_schema()
        await self.ensure_portfolio_exists(portfolio_id)
        if session_id is not None:
            await self.get_session(portfolio_id, session_id)

    async def prepare_chat(
        self,
        portfolio_id: str,
        session_id: str | None,
        title: str,
    ) -> tuple[dict, list[dict]]:
        if session_id:
            session = await self.get_session(portfolio_id, session_id)
        else:
            session = await self.create_session(portfolio_id, title=title)
        history = await self.list_messages(portfolio_id, session["id"])
        return session, history

    async def persist_message(
        self,
        *,
        portfolio_id: str,
        session_id: str,
        role: str,
        content: str,
        thinking: Any = None,
    ) -> dict:
        await self._ensure_schema()
        message_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        thinking_payload = _normalize_json_safe(thinking)
        await self.db.execute_transaction(
            [
                (
                    """
                    INSERT INTO agent.chat_messages
                    (id, session_id, portfolio_id, role, content, thinking, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        message_id,
                        session_id,
                        portfolio_id,
                        role,
                        content,
                        json.dumps(thinking_payload, ensure_ascii=False) if thinking_payload is not None else None,
                        created_at,
                    ],
                ),
                (
                    """
                    UPDATE agent.chat_sessions
                    SET updated_at = ?
                    WHERE id = ? AND portfolio_id = ?
                    """,
                    [created_at, session_id, portfolio_id],
                ),
            ]
        )
        return {
            "id": message_id,
            "session_id": session_id,
            "portfolio_id": portfolio_id,
            "role": role,
            "content": content,
            "thinking": thinking_payload,
            "created_at": created_at,
        }

    async def stream_chat_events(
        self,
        *,
        portfolio_id: str,
        message: str,
        session_id: str | None = None,
        title: str = "新对话",
    ) -> AsyncIterator[dict]:
        session, history = await self.prepare_chat(portfolio_id, session_id, title=title)
        await self.persist_message(
            portfolio_id=portfolio_id,
            session_id=session["id"],
            role="user",
            content=message,
        )

        reply_parts: list[str] = []
        full_text = ""
        reply_thinking = None

        async for event in self.chat_runtime.stream_reply(
            portfolio_id=portfolio_id,
            session_id=session["id"],
            message=message,
            history=history,
        ):
            event_type = event.get("event", "error")
            event_data = _normalize_json_safe(event.get("data") or {})
            normalized = {"event": event_type, "data": event_data}

            if event_type not in AGENT_CHAT_EVENT_NAMES:
                yield {"event": "error", "data": {"message": f"unsupported event: {event_type}"}}
                continue

            if event_type == "reply_token":
                token = event_data.get("content", "")
                if token:
                    reply_parts.append(token)
            elif event_type == "reply_complete":
                full_text = event_data.get("full_text", "")
                if "thinking" in event_data:
                    reply_thinking = event_data.get("thinking")

            yield normalized

        if not full_text:
            full_text = "".join(reply_parts)

        await self.persist_message(
            portfolio_id=portfolio_id,
            session_id=session["id"],
            role="assistant",
            content=full_text,
            thinking=reply_thinking,
        )
