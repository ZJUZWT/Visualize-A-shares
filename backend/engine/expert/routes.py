"""投资专家 Agent 路由 — 多专家统一入口 + Session 管理"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from loguru import logger

from auth import DEFAULT_ADMIN_USER, get_current_user

from config import settings, DB_PATH, DATA_DIR
from engine.expert.agent import ExpertAgent
from engine.expert.engine_experts import EngineExpert, ExpertType, get_expert_profiles
from engine.expert.schemas import (
    ClarifyRequest,
    ExpertChatRequest,
    ExpertResumeRequest,
    FeedbackReportDetail,
    FeedbackReportSummary,
    FeedbackReportCreateRequest,
    FeedbackResolveResponse,
    FeedbackResolveRequest,
    FeedbackSubmitResponse,
    ScheduledTaskRequest,
    SessionCreateRequest,
)
from engine.expert.scheduler import ScheduledTaskManager
from engine.expert.tools import ExpertTools
from engine.expert.tool_tracker import ToolOutcomeTracker
from engine.expert.user_profile import UserProfileTracker
from llm.config import llm_settings
from llm.providers import LLMProviderFactory

router = APIRouter(prefix="/api/v1/expert", tags=["expert"])

# 全局 Agent 实例
_expert_agent: ExpertAgent | None = None
_engine_experts: dict[str, EngineExpert] = {}
_tool_tracker: ToolOutcomeTracker | None = None
_user_profile_tracker: UserProfileTracker | None = None
_task_manager: ScheduledTaskManager | None = None

# WebSocket 通知客户端集合
_ws_notify_clients: set[WebSocket] = set()

# 专家对话历史使用独立数据库，避免与 stockterrain.duckdb 的 WAL 冲突
EXPERT_DB_PATH = DATA_DIR / "expert_chat.duckdb"

# 最近 N 轮对话注入 LLM 上下文
MAX_CONTEXT_TURNS = 10


def _get_db():
    return duckdb.connect(str(EXPERT_DB_PATH))


async def _init_db():
    """初始化 DuckDB expert schema 和表"""
    con = None
    try:
        con = _get_db()
        con.execute("CREATE SCHEMA IF NOT EXISTS expert")

        # Session 表
        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.sessions (
                id VARCHAR PRIMARY KEY,
                expert_type VARCHAR NOT NULL DEFAULT 'rag',
                title VARCHAR NOT NULL DEFAULT '新对话',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 对话消息表（每条消息一行，替代旧的 conversation_log）
        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.messages (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                content VARCHAR NOT NULL DEFAULT '',
                thinking JSON,
                status VARCHAR DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 迁移：为已有表添加 status 列
        try:
            con.execute("ALTER TABLE expert.messages ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'completed'")
        except Exception:
            pass

        # 保留旧表兼容
        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.conversation_log (
                id VARCHAR PRIMARY KEY,
                expert_type VARCHAR DEFAULT 'rag',
                session_id VARCHAR,
                user_message VARCHAR,
                expert_reply VARCHAR,
                belief_changes JSON,
                tools_used JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("expert.sessions + expert.messages 表初始化完成")

        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.feedback_reports (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                session_id VARCHAR NOT NULL,
                message_id VARCHAR NOT NULL,
                expert_type VARCHAR NOT NULL,
                report_source VARCHAR NOT NULL,
                issue_type VARCHAR NOT NULL,
                user_note VARCHAR DEFAULT '',
                user_message VARCHAR NOT NULL,
                assistant_content VARCHAR NOT NULL,
                message_status VARCHAR DEFAULT 'completed',
                thinking_json JSON,
                context_json JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                resolver VARCHAR,
                resolution_note VARCHAR DEFAULT ''
            )
        """)
        logger.info("expert.feedback_reports 表初始化完成")

        # ── Phase 2: 用户隔离 — 顶级资源表加 user_id ──
        try:
            con.execute("""
                ALTER TABLE expert.sessions
                ADD COLUMN IF NOT EXISTS user_id VARCHAR DEFAULT 'anonymous'
            """)
            try:
                con.execute("CREATE INDEX idx_sessions_user_id ON expert.sessions(user_id)")
            except Exception:
                pass
            logger.info("expert.sessions user_id 列已就绪")
        except Exception as e:
            logger.debug(f"expert.sessions user_id 迁移跳过: {e}")
    except Exception as e:
        logger.error(f"expert DB 初始化失败: {e}")
    finally:
        if con:
            con.close()

    # 初始化 RAG Agent 实例
    global _expert_agent
    try:
        from engine.data import get_data_engine
        from engine.cluster import get_cluster_engine

        data_engine = get_data_engine()
        cluster_engine = get_cluster_engine()

        # 复用 .env 全局 LLM 配置
        llm_provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None

        tools = ExpertTools(
            data_engine=data_engine,
            cluster_engine=cluster_engine,
            llm_engine=llm_provider,
        )

        kg_path = str(DATA_DIR / "expert_kg.json")
        Path(kg_path).parent.mkdir(parents=True, exist_ok=True)

        chromadb_dir = str(settings.chromadb.persist_dir)

        _expert_agent = ExpertAgent(tools, kg_path=kg_path, chromadb_dir=chromadb_dir)
        logger.info("投资专家 Agent 已初始化")

    except Exception as e:
        logger.error(f"投资专家 Agent 初始化失败: {e}")

    # 初始化 4 个引擎专家
    global _engine_experts
    try:
        llm_provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None
        for expert_type in ("data", "quant", "info", "industry"):
            _engine_experts[expert_type] = EngineExpert(expert_type, llm_provider)
        logger.info(f"引擎专家已初始化: {list(_engine_experts.keys())}")
    except Exception as e:
        logger.error(f"引擎专家初始化失败: {e}")

    # 初始化工具使用追踪器
    global _tool_tracker
    _tool_tracker = ToolOutcomeTracker(str(EXPERT_DB_PATH))
    logger.info("ToolOutcomeTracker 已初始化")

    # 初始化用户偏好追踪器
    global _user_profile_tracker
    _user_profile_tracker = UserProfileTracker(str(EXPERT_DB_PATH))
    logger.info("UserProfileTracker 已初始化")

    # 初始化定时任务管理器
    global _task_manager
    _task_manager = ScheduledTaskManager(
        db_path=str(EXPERT_DB_PATH),
        agent=_expert_agent,
        engine_experts=_engine_experts,
        on_complete=_broadcast_task_complete,
    )
    _task_manager.start_scheduler()
    logger.info("ScheduledTaskManager 已初始化")


def get_expert_agent() -> ExpertAgent:
    """获取 RAG Agent 实例"""
    if _expert_agent is None:
        raise RuntimeError("Expert Agent 未初始化")
    return _expert_agent


def get_tool_tracker() -> ToolOutcomeTracker | None:
    """获取工具使用追踪器"""
    return _tool_tracker


def get_user_profile_tracker() -> UserProfileTracker | None:
    """获取用户偏好追踪器"""
    return _user_profile_tracker


# ══════════════════════════════════════════════════════════
# Session CRUD
# ══════════════════════════════════════════════════════════


@router.get("/sessions")
async def list_sessions(expert_type: str = Query(default=None), user_id: str = Depends(get_current_user)):
    """列出所有 session（可按 expert_type 过滤，按 user_id 隔离）"""
    con = None
    try:
        con = _get_db()
        if expert_type:
            rows = con.execute(
                "SELECT s.id, s.expert_type, s.title, s.created_at, s.updated_at, "
                "(SELECT COUNT(*) FROM expert.messages m WHERE m.session_id = s.id) as msg_count "
                "FROM expert.sessions s WHERE s.expert_type = ? AND s.user_id = ? ORDER BY s.updated_at DESC",
                [expert_type, user_id],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT s.id, s.expert_type, s.title, s.created_at, s.updated_at, "
                "(SELECT COUNT(*) FROM expert.messages m WHERE m.session_id = s.id) as msg_count "
                "FROM expert.sessions s WHERE s.user_id = ? ORDER BY s.updated_at DESC",
                [user_id],
            ).fetchall()
        return [
            {"id": r[0], "expert_type": r[1], "title": r[2],
             "created_at": str(r[3]), "updated_at": str(r[4]), "message_count": r[5]}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取 session 列表失败: {e}")
        return []
    finally:
        if con:
            con.close()


@router.post("/sessions")
async def create_session(req: SessionCreateRequest, user_id: str = Depends(get_current_user)):
    """创建新 session（接收 JSON body: {expert_type, title}）"""
    con = None
    sid = str(uuid.uuid4())
    expert_type = req.expert_type
    title = req.title
    try:
        con = _get_db()
        now = datetime.now()
        con.execute(
            "INSERT INTO expert.sessions (id, expert_type, title, created_at, updated_at, user_id) VALUES (?,?,?,?,?,?)",
            [sid, expert_type, title, now, now, user_id],
        )
        return {"id": sid, "expert_type": expert_type, "title": title,
                "created_at": now.isoformat(), "updated_at": now.isoformat(), "message_count": 0}
    except Exception as e:
        logger.error(f"创建 session 失败: {e}")
        return {"error": str(e)}
    finally:
        if con:
            con.close()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = Depends(get_current_user)):
    """删除 session 及其所有消息"""
    con = None
    try:
        con = _get_db()
        # 校验归属
        row = con.execute("SELECT user_id FROM expert.sessions WHERE id = ?", [session_id]).fetchone()
        if row and row[0] != user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="无权删除此会话")
        con.execute("DELETE FROM expert.messages WHERE session_id = ?", [session_id])
        con.execute("DELETE FROM expert.sessions WHERE id = ?", [session_id])
        return {"ok": True}
    except Exception as e:
        logger.error(f"删除 session 失败: {e}")
        return {"error": str(e)}
    finally:
        if con:
            con.close()


@router.patch("/sessions/{session_id}")
async def update_session_title(session_id: str, title: str = ""):
    """更新 session 标题"""
    con = None
    try:
        con = _get_db()
        con.execute(
            "UPDATE expert.sessions SET title = ?, updated_at = ? WHERE id = ?",
            [title, datetime.now(), session_id],
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"更新 session 失败: {e}")
        return {"error": str(e)}
    finally:
        if con:
            con.close()


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取指定 session 的所有消息（按时间正序），含 status 字段"""
    con = None
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT id, role, content, thinking, status, created_at "
            "FROM expert.messages WHERE session_id = ? ORDER BY created_at ASC",
            [session_id],
        ).fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2],
             "thinking": json.loads(r[3]) if r[3] else [],
             "status": r[4] or "completed",
             "created_at": str(r[5])}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取 session 消息失败: {e}")
        return []
    finally:
        if con:
            con.close()


@router.post("/sessions/{session_id}/messages/save-user")
async def save_user_message(session_id: str, body: dict):
    """前端发送时立即将用户消息写入 DB（确保 session message_count 及时更新）"""
    content = body.get("content", "")
    if not content:
        return {"ok": False, "error": "content is empty"}
    _save_message(session_id, "user", content)
    _auto_title(session_id, content)
    return {"ok": True}


@router.post("/feedback", response_model=FeedbackSubmitResponse)
async def submit_feedback(req: FeedbackReportCreateRequest, user_id: str = Depends(get_current_user)):
    """提交 expert 对话问题反馈。"""
    con = None
    try:
        con = _get_db()
        session_row = con.execute(
            "SELECT user_id FROM expert.sessions WHERE id = ?",
            [req.session_id],
        ).fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="会话不存在")
        session_owner = session_row[0] or "anonymous"
        if user_id != DEFAULT_ADMIN_USER and session_owner != user_id:
            raise HTTPException(status_code=403, detail="无权反馈此会话")

        msg_row = con.execute(
            "SELECT role, content, thinking, status, created_at FROM expert.messages WHERE id = ? AND session_id = ?",
            [req.message_id, req.session_id],
        ).fetchone()
        if not msg_row:
            raise HTTPException(status_code=404, detail="消息不存在")
        role, assistant_content, thinking_json, status, created_at = msg_row
        if role != "expert":
            raise HTTPException(status_code=400, detail="仅支持反馈 expert 消息")

        user_row = con.execute(
            "SELECT content FROM expert.messages WHERE session_id = ? AND role = 'user' AND created_at <= ? "
            "ORDER BY created_at DESC LIMIT 1",
            [req.session_id, created_at],
        ).fetchone()
        user_message = user_row[0] if user_row else ""

        feedback_id = str(uuid.uuid4())
        con.execute(
            """
            INSERT INTO expert.feedback_reports
            (id, user_id, session_id, message_id, expert_type, report_source, issue_type,
             user_note, user_message, assistant_content, message_status, thinking_json, context_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                feedback_id, user_id, req.session_id, req.message_id, req.expert_type, req.report_source,
                req.issue_type, req.user_note, user_message, assistant_content, status or "completed",
                thinking_json or "[]", json.dumps(req.context, ensure_ascii=False), datetime.now(),
            ],
        )
        return FeedbackSubmitResponse(ok=True, feedback_id=feedback_id)
    finally:
        if con:
            con.close()


@router.get("/feedback/admin", response_model=list[FeedbackReportSummary])
async def list_feedback_reports(
    unresolved_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(get_current_user),
):
    """管理员查看反馈列表。"""
    _require_admin(user_id)
    con = None
    try:
        con = _get_db()
        where_sql = "WHERE resolved_at IS NULL" if unresolved_only else ""
        rows = con.execute(
            f"""
            SELECT id, user_id, session_id, message_id, expert_type, report_source, issue_type,
                   user_note, message_status, created_at, resolved_at, resolver
            FROM expert.feedback_reports
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [
            FeedbackReportSummary(
                id=r[0],
                user_id=r[1],
                session_id=r[2],
                message_id=r[3],
                expert_type=r[4],
                report_source=r[5],
                issue_type=r[6],
                user_note=r[7],
                message_status=r[8],
                created_at=str(r[9]),
                resolved_at=str(r[10]) if r[10] else None,
                resolver=r[11],
            )
            for r in rows
        ]
    finally:
        if con:
            con.close()


@router.get("/feedback/admin/{feedback_id}", response_model=FeedbackReportDetail)
async def get_feedback_report(feedback_id: str, user_id: str = Depends(get_current_user)):
    """管理员查看反馈详情。"""
    _require_admin(user_id)
    con = None
    try:
        con = _get_db()
        row = con.execute(
            """
            SELECT id, user_id, session_id, message_id, expert_type, report_source, issue_type, user_note,
                   user_message, assistant_content, message_status, thinking_json, context_json,
                   created_at, resolved_at, resolver, resolution_note
            FROM expert.feedback_reports
            WHERE id = ?
            """,
            [feedback_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return FeedbackReportDetail(
            id=row[0],
            user_id=row[1],
            session_id=row[2],
            message_id=row[3],
            expert_type=row[4],
            report_source=row[5],
            issue_type=row[6],
            user_note=row[7],
            user_message=row[8],
            assistant_content=row[9],
            message_status=row[10],
            thinking_json=json.loads(row[11]) if row[11] else [],
            context_json=json.loads(row[12]) if row[12] else {},
            created_at=str(row[13]),
            resolved_at=str(row[14]) if row[14] else None,
            resolver=row[15],
            resolution_note=row[16] or "",
        )
    finally:
        if con:
            con.close()


@router.post("/feedback/admin/{feedback_id}/resolve", response_model=FeedbackResolveResponse)
async def resolve_feedback_report(
    feedback_id: str,
    req: FeedbackResolveRequest,
    user_id: str = Depends(get_current_user),
):
    """管理员标记反馈为已处理。"""
    _require_admin(user_id)
    con = None
    try:
        con = _get_db()
        exists = con.execute(
            "SELECT 1 FROM expert.feedback_reports WHERE id = ?",
            [feedback_id],
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="反馈不存在")
        con.execute(
            "UPDATE expert.feedback_reports SET resolved_at = ?, resolver = ?, resolution_note = ? WHERE id = ?",
            [datetime.now(), user_id, req.resolution_note, feedback_id],
        )
        return FeedbackResolveResponse(ok=True)
    finally:
        if con:
            con.close()


def _get_session_history(session_id: str, limit: int = MAX_CONTEXT_TURNS) -> list[dict]:
    """获取指定 session 的最近 N 轮对话（用于注入 LLM 上下文）"""
    if not session_id:
        return []
    con = None
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT role, content FROM expert.messages "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            [session_id, limit * 2],  # user+expert 各一条 = 1轮
        ).fetchall()
        # 逆序回来（最旧在前）
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception as e:
        logger.debug(f"获取 session 历史失败: {e}")
        return []
    finally:
        if con:
            con.close()


def _save_message(session_id: str, role: str, content: str, thinking: list | None = None, status: str = "completed") -> str | None:
    """将消息写入 messages 表，返回消息 ID"""
    if not session_id:
        return None
    con = None
    msg_id = str(uuid.uuid4())
    try:
        con = _get_db()
        con.execute(
            "INSERT INTO expert.messages (id, session_id, role, content, thinking, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [msg_id, session_id, role, content,
             json.dumps(thinking or [], ensure_ascii=False), status, datetime.now()],
        )
        con.execute(
            "UPDATE expert.sessions SET updated_at = ? WHERE id = ?",
            [datetime.now(), session_id],
        )
        return msg_id
    except Exception as e:
        logger.warning(f"消息写入失败: {e}")
        return None
    finally:
        if con:
            con.close()


def _update_message(message_id: str, content: str, thinking: list | None = None, status: str = "completed"):
    """更新已有消息的 content、thinking 和 status"""
    if not message_id:
        return
    con = None
    try:
        con = _get_db()
        con.execute(
            "UPDATE expert.messages SET content = ?, thinking = ?, status = ? WHERE id = ?",
            [content, json.dumps(thinking or [], ensure_ascii=False), status, message_id],
        )
    except Exception as e:
        logger.warning(f"消息更新失败: {e}")
    finally:
        if con:
            con.close()


def _save_partial_message(session_id: str, content: str, thinking_items: list | None = None, *, context: str = "stream") -> None:
    """在流式中断时保存 partial 消息，避免已生成内容丢失。"""
    if not session_id or not content.strip():
        return
    _save_message(session_id, "expert", content, thinking_items, status="partial")
    logger.info(f"💾 {context} 中断，已保存 partial 消息 (session={session_id}, len={len(content)})")


def _auto_title(session_id: str, user_message: str):
    """首条消息时自动设置 session 标题（取前 30 字）"""
    con = None
    try:
        con = _get_db()
        count = con.execute(
            "SELECT COUNT(*) FROM expert.messages WHERE session_id = ?", [session_id]
        ).fetchone()[0]
        if count <= 2:  # 刚存入 user + expert 两条
            title = user_message[:30].replace("\n", " ").strip()
            if len(user_message) > 30:
                title += "..."
            con.execute(
                "UPDATE expert.sessions SET title = ? WHERE id = ?",
                [title, session_id],
            )
    except Exception:
        pass
    finally:
        if con:
            con.close()


def _require_admin(user_id: str) -> None:
    """仅允许默认管理员访问反馈管理接口。"""
    if user_id != DEFAULT_ADMIN_USER:
        raise HTTPException(status_code=403, detail="仅管理员可访问")


# ══════════════════════════════════════════════════════════
# 多专家统一入口
# ══════════════════════════════════════════════════════════


@router.get("/profiles")
async def list_expert_profiles():
    """返回所有专家配置信息（前端用于渲染专家选择器）"""
    return get_expert_profiles()


@router.post("/chat/{expert_type}")
async def expert_chat_by_type(expert_type: ExpertType, req: ExpertChatRequest):
    """与指定类型的专家对话（SSE 流式）"""
    if expert_type == "rag":
        return await _rag_chat(req)

    # 短线专家复用 RAG Agent，但使用 short_term 人格
    if expert_type == "short_term":
        return await _rag_chat(req, persona="short_term")

    expert = _engine_experts.get(expert_type)
    if not expert:
        return StreamingResponse(
            _error_stream(f"专家类型 {expert_type} 未初始化"),
            media_type="text/event-stream",
        )

    # 确保有 session
    session_id = req.session_id or ""
    history = _get_session_history(session_id) if session_id else []

    async def event_stream():
        full_reply = ""
        tools_used = []
        thinking_items = []
        try:
            async for event in expert.chat(
                req.message, history=history,
                deep_think=req.deep_think, max_rounds=req.max_rounds,
                enable_trade_plan=req.enable_trade_plan,
            ):
                evt_type = event["event"]
                if evt_type == "reply_token":
                    full_reply += event["data"].get("token", "")
                elif evt_type == "reply_complete":
                    full_reply = event["data"].get("full_text", "")
                elif evt_type == "tool_call":
                    tools_used.append(event["data"].get("action", ""))
                    thinking_items.append({"type": "tool_call", "data": event["data"], "status": "pending"})
                elif evt_type == "tool_result":
                    # 将 tool_result 合并到对应的 tool_call 上（更新 status）
                    result_data = event["data"]
                    matched = False
                    for ti in reversed(thinking_items):
                        if (ti["type"] == "tool_call"
                            and ti.get("status") == "pending"
                            and ti["data"].get("engine") == result_data.get("engine")
                            and ti["data"].get("action") == result_data.get("action")):
                            ti["status"] = "error" if result_data.get("hasError") else "done"
                            ti["result"] = result_data
                            matched = True
                            break
                    if not matched:
                        thinking_items.append({"type": "tool_result", "data": result_data})
                elif evt_type == "graph_recall":
                    thinking_items.append({"type": "graph_recall", "data": event["data"]})
                elif evt_type == "thinking_round":
                    thinking_items.append({"type": "thinking_round", "data": event["data"]})
                elif evt_type == "belief_updated":
                    thinking_items.append({"type": "belief_updated", "data": event["data"]})
                elif evt_type == "reasoning_summary":
                    thinking_items.append({"type": "reasoning_summary", "data": event["data"]})
                elif evt_type == "self_critique":
                    thinking_items.append({"type": "self_critique", "data": event["data"]})
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            _save_partial_message(session_id, full_reply, thinking_items, context=f"{expert_type} expert chat")
            raise
        except Exception as e:
            logger.error(f"{expert_type} expert chat 错误: {e}")
            _save_partial_message(session_id, full_reply, thinking_items, context=f"{expert_type} expert chat")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 存入 session 消息（用户消息已由前端 save-user 接口写入，此处只存 expert 回复）
        if session_id:
            _save_message(session_id, "expert", full_reply, thinking_items, status="completed")
            _auto_title(session_id, req.message)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/clarify/{expert_type}")
async def clarify_expert_question(expert_type: ExpertType, req: ClarifyRequest):
    """深度思考模式的 clarification 阶段（支持多轮澄清）。"""
    if expert_type not in ("rag", "short_term"):
        return {"error": f"专家类型 {expert_type} 不支持 clarification"}

    agent = get_expert_agent()
    session_id = req.session_id or ""
    history = _get_session_history(session_id) if session_id else []
    persona = "short_term" if expert_type == "short_term" else "rag"
    result = await agent.clarify(
        req.message,
        history=history,
        persona=persona,
        previous_selections=req.previous_selections,
    )
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result


@router.post("/chat")
async def expert_chat(req: ExpertChatRequest):
    """与 RAG 专家 Agent 对话（SSE 流式）— 兼容旧接口"""
    return await _rag_chat(req)


async def _rag_chat(req: ExpertChatRequest, persona: str = "rag"):
    """RAG 专家对话"""
    logger.info(f"📋 _rag_chat: deep_think={req.deep_think}, enable_trade_plan={req.enable_trade_plan}, use_clarification={req.use_clarification}")
    agent = get_expert_agent()
    session_id = req.session_id or ""
    history = _get_session_history(session_id) if session_id else []

    async def event_stream():
        full_reply = ""
        belief_changes = []
        tools_used = []
        thinking_items = []
        try:
            async for event in agent.chat(
                req.message, history=history, persona=persona,
                deep_think=req.deep_think, max_rounds=req.max_rounds,
                clarification_selection=req.clarification_selection,
                clarification_chain=req.clarification_chain,
                enable_trade_plan=req.enable_trade_plan,
                images=req.images,
            ):
                evt_type = event["event"]
                if evt_type == "reply_token":
                    full_reply += event["data"].get("token", "")
                elif evt_type == "reply_complete":
                    full_reply = event["data"].get("full_text", "")
                elif evt_type == "tool_call":
                    tools_used.append(event["data"].get("action", ""))
                    thinking_items.append({"type": "tool_call", "data": event["data"], "status": "pending"})
                elif evt_type == "tool_result":
                    # 将 tool_result 合并到对应的 tool_call 上（更新 status）
                    result_data = event["data"]
                    matched = False
                    for ti in reversed(thinking_items):
                        if (ti["type"] == "tool_call"
                            and ti.get("status") == "pending"
                            and ti["data"].get("engine") == result_data.get("engine")
                            and ti["data"].get("action") == result_data.get("action")):
                            ti["status"] = "error" if result_data.get("hasError") else "done"
                            ti["result"] = result_data
                            matched = True
                            break
                    if not matched:
                        thinking_items.append({"type": "tool_result", "data": result_data})
                elif evt_type == "belief_updated":
                    belief_changes.append(event["data"])
                    thinking_items.append({"type": "belief_updated", "data": event["data"]})
                elif evt_type == "graph_recall":
                    thinking_items.append({"type": "graph_recall", "data": event["data"]})
                elif evt_type == "reasoning_summary":
                    thinking_items.append({"type": "reasoning_summary", "data": event["data"]})
                elif evt_type == "self_critique":
                    thinking_items.append({"type": "self_critique", "data": event["data"]})
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            _save_partial_message(session_id, full_reply, thinking_items, context="expert chat")
            raise
        except Exception as e:
            logger.error(f"expert chat 错误: {e}")
            _save_partial_message(session_id, full_reply, thinking_items, context="expert chat")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 存入 session 消息（用户消息已由前端 save-user 接口写入，此处只存 expert 回复）
        if session_id:
            _save_message(session_id, "expert", full_reply, thinking_items, status="completed")
            _auto_title(session_id, req.message)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _error_stream(message: str):
    yield f"event: error\ndata: {json.dumps({'message': message}, ensure_ascii=False)}\n\n"


@router.post("/chat/resume")
async def expert_chat_resume(req: ExpertResumeRequest):
    """续写被中断的 expert 回复（SSE 流式）"""
    con = None
    try:
        con = _get_db()
        row = con.execute(
            "SELECT id, session_id, role, content, thinking, status "
            "FROM expert.messages WHERE id = ? AND session_id = ?",
            [req.message_id, req.session_id],
        ).fetchone()
    except Exception as e:
        logger.error(f"resume 查询消息失败: {e}")
        return StreamingResponse(
            _error_stream(f"查询消息失败: {e}"),
            media_type="text/event-stream",
        )
    finally:
        if con:
            con.close()

    if not row:
        return StreamingResponse(
            _error_stream("消息不存在"),
            media_type="text/event-stream",
        )

    msg_id, session_id, role, partial_content, thinking_json, status = row
    if status not in ("partial", "completed"):
        return StreamingResponse(
            _error_stream(f"消息状态为 {status}，无需续写"),
            media_type="text/event-stream",
        )
    if status == "completed" and not req.check_completed:
        return StreamingResponse(
            _error_stream(f"消息状态为 {status}，无需续写"),
            media_type="text/event-stream",
        )

    thinking_items = json.loads(thinking_json) if thinking_json else []

    # 获取该 partial 消息之前的所有历史
    history = _get_session_history(session_id)

    # 找到对应的用户原始问题（partial 消息前最后一条 user 消息）
    user_message = ""
    for h in reversed(history):
        if h["role"] == "user":
            user_message = h["content"]
            break

    if not user_message:
        return StreamingResponse(
            _error_stream("未找到对应的用户问题"),
            media_type="text/event-stream",
        )

    # 判断 session 的 expert_type 以决定用哪个 persona
    persona = "rag"
    try:
        con2 = _get_db()
        session_row = con2.execute(
            "SELECT expert_type FROM expert.sessions WHERE id = ?", [session_id]
        ).fetchone()
        if session_row and session_row[0] == "short_term":
            persona = "short_term"
        con2.close()
    except Exception:
        pass

    agent = get_expert_agent()
    check_result = await agent.check_resume_completion(
        user_message=user_message,
        partial_content=partial_content,
        history=history,
        persona=persona,
    )
    is_complete = bool(check_result.get("is_complete", False))
    if is_complete:
        _update_message(msg_id, partial_content, thinking_items, status="completed")
        logger.info(
            "✅ resume 完整性检查通过，直接标记 completed "
            f"(msg={msg_id}, confidence={check_result.get('confidence', 0.0)})"
        )

        async def completed_event_stream():
            yield (
                "event: resume_completion_check\n"
                f"data: {json.dumps(check_result, ensure_ascii=False)}\n\n"
            )
            yield (
                "event: resume_complete\n"
                f"data: {json.dumps({'continuation': '', 'skipped_resume': True}, ensure_ascii=False)}\n\n"
            )

        return StreamingResponse(completed_event_stream(), media_type="text/event-stream")

    async def event_stream():
        continuation = ""
        try:
            yield (
                "event: resume_completion_check\n"
                f"data: {json.dumps(check_result, ensure_ascii=False)}\n\n"
            )
            async for event in agent.resume_reply(
                message=user_message,
                partial_content=partial_content,
                history=history,
                persona=persona,
            ):
                evt_type = event["event"]
                if evt_type == "resume_token":
                    continuation += event["data"].get("token", "")
                elif evt_type == "resume_complete":
                    continuation_text = event["data"].get("continuation", "")
                    # 合并: 原有 partial + 续写部分
                    full_content = partial_content + continuation_text
                    _update_message(msg_id, full_content, thinking_items, status="completed")
                    logger.info(f"✅ 续写完成 (msg={msg_id}, partial_len={len(partial_content)}, continuation_len={len(continuation_text)})")
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            if continuation.strip():
                full_content = partial_content + continuation
                _update_message(msg_id, full_content, thinking_items, status="partial")
                logger.info(f"💾 续写中断，已更新 partial 消息 (msg={msg_id}, added_len={len(continuation)})")
            raise
        except Exception as e:
            logger.error(f"resume stream 错误: {e}")
            # 续写也中断了：更新 partial 内容（追加已续写部分）
            if continuation.strip():
                full_content = partial_content + continuation
                _update_message(msg_id, full_content, thinking_items, status="partial")
                logger.info(f"💾 续写中断，已更新 partial 消息 (msg={msg_id}, added_len={len(continuation)})")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/graph")
async def get_graph():
    """返回当前知识图谱（JSON）"""
    agent = get_expert_agent()
    return agent._graph.to_dict()


@router.get("/beliefs")
async def get_beliefs():
    """获取当前信念列表"""
    agent = get_expert_agent()
    return {"beliefs": agent.get_beliefs()}


@router.get("/stances")
async def get_stances():
    """获取当前立场列表"""
    agent = get_expert_agent()
    return {"stances": agent.get_stances()}


@router.get("/history")
async def get_history(limit: int = 20):
    """返回对话历史（兼容旧接口）"""
    con = None
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT id, user_message, expert_reply, belief_changes, tools_used, created_at "
            "FROM expert.conversation_log ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [
            {"id": r[0], "user_message": r[1], "expert_reply": r[2],
             "belief_changes": r[3], "tools_used": r[4], "created_at": str(r[5])}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        return []
    finally:
        if con:
            con.close()


@router.get("/knowledge-graph/stats")
async def get_kg_stats():
    """获取知识图谱统计"""
    agent = get_expert_agent()
    return agent._graph.stats()


# ══════════════════════════════════════════════════════════
# 定时任务调度
# ══════════════════════════════════════════════════════════


def get_task_manager() -> ScheduledTaskManager | None:
    return _task_manager


async def _broadcast_task_complete(task_id: str, task_name: str, full_text: str):
    """任务完成时通过 WebSocket 广播通知"""
    import json as _json
    msg = _json.dumps({
        "type": "task_completed",
        "task_id": task_id,
        "task_name": task_name,
        "summary": full_text[:200] if full_text else "",
    }, ensure_ascii=False)

    dead: list[WebSocket] = []
    for ws in _ws_notify_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_notify_clients.discard(ws)


@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """WebSocket 通知通道 — 推送定时任务完成事件"""
    await websocket.accept()
    _ws_notify_clients.add(websocket)
    logger.info(f"🔔 通知 WebSocket 已连接 (当前 {len(_ws_notify_clients)} 个客户端)")
    try:
        while True:
            # 保持连接活跃（等待客户端 ping 或断连）
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_notify_clients.discard(websocket)
        logger.info(f"🔔 通知 WebSocket 已断开 (剩余 {len(_ws_notify_clients)} 个客户端)")


@router.post("/tasks")
async def create_task(req: ScheduledTaskRequest, user_id: str = Depends(get_current_user)):
    """创建定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}

    session_id = None
    if req.create_session:
        # 自动创建专属 session
        con = None
        try:
            con = _get_db()
            session_id = str(uuid.uuid4())
            now = datetime.now()
            con.execute(
                "INSERT INTO expert.sessions (id, expert_type, title, created_at, updated_at, user_id) VALUES (?,?,?,?,?,?)",
                [session_id, req.expert_type, f"⏰ {req.name}", now, now, user_id],
            )
        except Exception as e:
            logger.error(f"创建任务 session 失败: {e}")
        finally:
            if con:
                con.close()

    task = _task_manager.create_task(
        name=req.name,
        expert_type=req.expert_type,
        persona=req.persona,
        message=req.message,
        cron_expr=req.cron_expr,
        session_id=session_id,
        user_id=user_id,
    )
    return task


@router.get("/tasks")
async def list_tasks(user_id: str = Depends(get_current_user)):
    """列出当前用户的定时任务"""
    if not _task_manager:
        return []
    all_tasks = _task_manager.list_tasks()
    # 按 user_id 过滤（兼容旧数据无 user_id 字段）
    return [t for t in all_tasks if t.get("user_id", "anonymous") == user_id]


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    _task_manager.delete_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    """暂停定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    _task_manager.pause_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """恢复定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    _task_manager.resume_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str):
    """立即执行一次定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    try:
        result = await _task_manager.execute_task(task_id)
        return {"ok": True, "result_length": len(result), "summary": result[:300]}
    except Exception as e:
        return {"error": str(e)}
